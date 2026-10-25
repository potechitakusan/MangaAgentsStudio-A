"""PixAIのモデルの一覧（config/pixai-models.json）を表示し、一覧にないモデルをモデルページのURLから登録する。

  python -X utf8 scripts/pixai_models.py list                                   # 一覧（通信なし）
  python -X utf8 scripts/pixai_models.py info --url <モデルページのURL>          # バージョンID・種類・利用条件を表示（登録しない）
  python -X utf8 scripts/pixai_models.py add <名前> --url <モデルページのURL>     # 作品の一覧へ登録する
  python -X utf8 scripts/pixai_models.py lora --url <LoRAのページのURL>           # LoRAの元モデル・利用条件を作品に記録する

LoRAの記録（config/pixai-loras.json）は、１回確かめたら取り直さない（--refresh で取り直す）。
pixai_api.py は送信前の確認で、この記録だけを使って LoRA と生成モデルの組み合わせを点検する（通信しない）。

URLは https://pixai.art/model/<モデルID> か、版のタブを押した https://pixai.art/model/<モデルID>/<バージョンID>。
モデルIDの数字だけでもよい。版を指定しなければ、ページに表示される最新の版を使う。
公開のモデルページを１回だけ取得する（キーを送らない・ログインしない・画像生成しない・クレジットを使わない）。
ページに埋め込まれたデータはPixAIの公式APIではない。形式が変わって読めない場合は、利用者にモデルページで版のタブを押した
URLを写してもらい、pixai_compose.py の --model-version-id と --model-type で指定する。
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pixai_api as api  # noqa: E402

PAGE_ROOT = "https://pixai.art"
MAX_PAGE = 8 * 1024 * 1024
MODEL_URL = re.compile(r"(?:https://pixai\.art(?:/[a-z]{2}(?:-[A-Za-z]{2,4})?)?/model/)?([0-9]{6,30})(?:-[^/?#]*)?(?:/([0-9]{6,30}))?/?(?:[?#].*)?")
NAME = re.compile(r"[a-z0-9][a-z0-9.-]{0,40}")


class ModelError(Exception):
    pass


def parse_url(value: str) -> tuple[str, str | None]:
    match = MODEL_URL.fullmatch(value.strip())
    if not match:
        raise ModelError("URLは https://pixai.art/model/<モデルID>[/<バージョンID>] か、モデルIDの数字にしてください。")
    return match.group(1), match.group(2)


def fetch_page(model_id: str, version_id: str | None) -> str:
    url = f"{PAGE_ROOT}/model/{model_id}" + (f"/{version_id}" if version_id else "")
    request = Request(url, headers={"User-Agent": "MangaAgentsStudio-PixAI/1", "Accept": "text/html"})
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read(MAX_PAGE + 1)
    except HTTPError as error:
        raise ModelError(f"モデルページを取得できませんでした（HTTP {error.code}）。URLとモデルの公開状態を確認してください。") from None
    except (URLError, OSError):
        raise ModelError("モデルページへ接続できませんでした。ネットワークと実行環境の接続制限を確認してください。") from None
    if len(body) > MAX_PAGE:
        raise ModelError("モデルページが想定より大きいため読みません。")
    return body.decode("utf-8", errors="replace")


def page_data(html: str) -> dict:
    """React Router の turbo-stream（番号で参照し合う配列）を復元する。"""
    match = re.search(r'streamController\.enqueue\((".*?")\);', html, re.S)
    if not match:
        raise ModelError("ページの形式が変わった可能性があります（埋め込みデータがない）。"
                         "利用者にモデルページで版のタブを押したURLを写してもらってください。")
    flat = json.loads(json.loads(match.group(1)))
    memo: dict[int, object] = {}

    def hydrate(index):
        if not isinstance(index, int) or index < 0:
            return None
        if index in memo:
            return memo[index]
        value = flat[index]
        if isinstance(value, dict):
            out: dict = {}
            memo[index] = out
            for key, item in value.items():
                name = flat[int(key[1:])] if key.startswith("_") else key
                out[name] = hydrate(item) if isinstance(item, int) else item
            return out
        if isinstance(value, list):
            out_list: list = []
            memo[index] = out_list
            if value and isinstance(value[0], str) and value[0] in ("D", "P", "S", "Y", "R", "E"):
                return value  # 日付等の特殊な値は使わない
            out_list.extend(hydrate(item) if isinstance(item, int) else item for item in value)
            return out_list
        return value

    root = hydrate(0)
    for data in (root or {}).get("loaderData", {}).values():
        if isinstance(data, dict) and isinstance(data.get("generationModel"), dict):
            return data
    raise ModelError("ページにモデルの情報が見つかりません。URLがモデルページか確認してください。")


def model_info(html: str, version_id: str | None) -> dict:
    data = page_data(html)
    model = data["generationModel"]
    version = data.get("generationModelVersion") if version_id else model.get("latestAvailableVersion")
    if not isinstance(version, dict) or (version_id and version.get("id") != version_id):
        raise ModelError("指定の版がページにありません。版のタブを押したURLを使ってください。")
    extra = model.get("extra") if isinstance(model.get("extra"), dict) else {}
    vextra = version.get("extra") if isinstance(version.get("extra"), dict) else {}
    compat = vextra.get("compatibility") if isinstance(vextra.get("compatibility"), dict) else {}
    permissions = extra.get("permissions") if isinstance(extra.get("permissions"), dict) else {}
    return {"title": model.get("title"), "modelId": model.get("id"), "id": version.get("id"), "versionName": version.get("name"),
            "pixaiType": model.get("type") or "", "status": version.get("status"), "permittedUse": model.get("permittedUse"),
            "permissions": permissions, "isNsfw": model.get("isNsfw"), "negativePrompt": compat.get("negativePrompt", True),
            "loraBaseModelType": version.get("loraBaseModelType"), "loraBaseModelId": version.get("loraBaseModelId"), "triggerWords": vextra.get("triggerWords") or extra.get("triggerWords") or ""}


def catalog_entry(info: dict) -> dict:
    """ページの情報から一覧の項目を作る。mode・style は公式文書の「Tsubaki.2・Tsubaki.3 系だけ」から種類で決める。"""
    kind = info["pixaiType"]
    if "LORA" in kind:
        raise ModelError(f"これはLoRA（{kind}）です。バージョンID {info['id']} を .env.pixai の PIXAI_LORA_… に書いてください。")
    if kind == "SDXL_MODEL":
        entry = {"type": "sdxl", "mode": False, "style": False}
    elif kind.startswith("MMDIT26"):  # Tsubaki.2（MMDIT26A）・Tsubaki.3（MMDIT26B）系
        entry = {"type": "dit", "mode": True, "style": True}
    elif "DIT" in kind:
        entry = {"type": "dit", "mode": False, "style": False}
    else:
        raise ModelError(f"画像生成のベースモデルとして扱えない種類です（{kind or '不明'}）。")
    commercial = info["permittedUse"] == "COMMERCIAL" or bool(info["permissions"].get("commercialUses"))
    return {"label": f"{info['title']} {info['versionName']}".strip(), "modelId": info["modelId"], "id": info["id"],
            "versionName": info["versionName"], "pixaiType": kind, **entry, "negativePrompt": bool(info["negativePrompt"]),
            "commercialUse": commercial, "permissions": info["permissions"], "api": "未検証", "checked_on": date.today().isoformat(),
            "strengths_ja": "モデルページから登録（pixai_models.py add）"}


def show(info: dict) -> None:
    perms = info["permissions"]
    print(f"モデル: {info['title']}（モデルID {info['modelId']}、種類 {info['pixaiType']}）")
    print(f"版: {info['versionName']}（バージョンID {info['id']}、状態 {info['status']}）")
    print("利用条件: " + ("商用可" if info["permittedUse"] == "COMMERCIAL" or perms.get("commercialUses") else "商用不可")
          + "・オンライン共有" + ("可" if perms.get("shareImagesOnline") else "不明／不可")
          + ("・作者のクレジット表記が必要" if perms.get("shouldCreditAuthor") else "")
          + ("・成人向け" if info["isNsfw"] else ""))
    if "LORA" in info["pixaiType"]:
        print(f"LoRAの元モデルの種類: {info['loraBaseModelType'] or '不明'}。トリガー語: {info['triggerWords'] or 'なし'}")


def lora_record(info: dict) -> dict:
    if "LORA" not in info["pixaiType"]:
        raise ModelError(f"これはLoRAではありません（{info['pixaiType'] or '種類不明'}）。モデルは add で登録してください。")
    perms = info["permissions"]
    return {"title": f"{info['title']} {info['versionName']}".strip(), "modelId": info["modelId"], "versionName": info["versionName"],
            "pixaiType": info["pixaiType"], "baseModelType": info["loraBaseModelType"], "baseModelId": info["loraBaseModelId"],
            "commercialUse": info["permittedUse"] == "COMMERCIAL" or bool(perms.get("commercialUses")), "permissions": perms,
            "triggerWords": info["triggerWords"], "checked_on": date.today().isoformat(), "source": "モデルページ（pixai_models.py lora）"}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def lora(root: Path, url: str, refresh: bool, fetch=None) -> tuple[str, dict, bool]:
    """（バージョンID、記録、取り直したか）。記録済みなら通信しない。"""
    path = root / api.LORAS_FILE
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema_version": 1, "loras": {}}
    records = data.setdefault("loras", {})
    model_id, version_id = parse_url(url)
    known = version_id if version_id in records else \
        (next((v for v, r in records.items() if r.get("modelId") == model_id), None) if not version_id else None)
    if known and not refresh:
        return known, records[known], False
    info = model_info((fetch or fetch_page)(model_id, version_id), version_id)
    records[info["id"]] = lora_record(info)
    save_json(path, data)
    return info["id"], records[info["id"]], True


def read_catalog(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema_version": 1, "models": {}}


def add(root: Path, name: str, info: dict, force: bool) -> dict:
    if not NAME.fullmatch(name):
        raise ModelError("名前は英小文字・数字・.・- にしてください（例 my-model2）。")
    path = root / api.MODELS_FILE
    catalog = read_catalog(path)
    models = catalog.setdefault("models", {})
    if name in models and not force:
        raise ModelError(f"{name} は登録済みです。置き換えるなら --force を付けてください。")
    same = [n for n, m in models.items() if m.get("id") == info["id"] and n != name]
    if same:
        raise ModelError(f"このバージョンIDは {same[0]} として登録済みです。")
    entry = catalog_entry(info)
    models[name] = entry
    save_json(path, catalog)
    return entry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PixAIのモデルの一覧の表示と登録")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="一覧を表示する（通信なし）")
    info_cmd = sub.add_parser("info", help="モデルページからバージョンID・種類・利用条件を表示する（登録しない）")
    info_cmd.add_argument("--url", required=True)
    add_cmd = sub.add_parser("add", help="モデルページから作品の一覧へ登録する")
    add_cmd.add_argument("name", help="--model に使う名前（英小文字・数字・.・-）")
    add_cmd.add_argument("--url", required=True)
    add_cmd.add_argument("--force", action="store_true", help="同じ名前の登録を置き換える")
    lora_cmd = sub.add_parser("lora", help="LoRAの元モデル・利用条件を作品に記録する（記録済みなら通信しない）")
    lora_cmd.add_argument("--url", required=True)
    lora_cmd.add_argument("--refresh", action="store_true", help="記録済みでもページを取り直す")
    opts = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        if opts.command == "list":
            for name, model in read_catalog(root / api.MODELS_FILE).get("models", {}).items():
                use = "商用可" if model.get("commercialUse") else "商用不可"
                print(f"{name}: {model['label']}（{model['type'].upper()}、modelVersionId {model['id']}、{use}）"
                      f" {model.get('strengths_ja', '')} / API: {model.get('api', '未記入')}")
            return 0
        if opts.command == "lora":
            if not (root / "project.json").is_file():
                raise ModelError("作品プロジェクトの scripts/ から実行してください。")
            version_id, record, fetched = lora(root, opts.url, opts.refresh)
            print(("記録しました" if fetched else "記録済み（ページは取り直していない。--refresh で取り直す）") + f"：{api.LORAS_FILE}")
            print(f"LoRA: {record['title']}（バージョンID {version_id}、確認日 {record['checked_on']}）")
            print(f"元モデル: 種類 {record['baseModelType'] or '不明'}" + (f"、モデルID {record['baseModelId']}" if record.get("baseModelId") else ""))
            print("利用条件: " + ("商用可" if record["commercialUse"] else "商用不可（公開・販売の条件を利用者が確認する）"))
            print(f"トリガー語: {record['triggerWords'] or 'なし'}")
            print(f".env.pixai の例: PIXAI_LORA_<名前>=\"{version_id}\"")
            return 0
        model_id, version_id = parse_url(opts.url)
        info = model_info(fetch_page(model_id, version_id), version_id)
        show(info)
        if opts.command == "add":
            if not (root / "project.json").is_file():
                raise ModelError("作品プロジェクトの scripts/ から実行してください。")
            entry = add(root, opts.name, info, opts.force)
            print(f"{api.MODELS_FILE} に {opts.name} を登録しました（API: 未検証）。--model {opts.name} で使えます。")
            if not entry["commercialUse"]:
                print("注意: 商用利用が許可されていません。公開・販売の条件をモデルページで利用者が確認してください。")
            if entry["mode"]:
                print("注意: mode の受理は未確認です。既定では mode を送りません（サーバーの既定）。")
        return 0
    except ModelError as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
