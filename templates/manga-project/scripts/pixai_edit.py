"""生成済みのコマを元に、インペイント（一部だけ描き直す）・i2i（全体を描き直す）の要求JSONを作る。通信しない。

元の要求（input/pixai/requests/<ID>.json）のプロンプト・除外・モデル・画風プリセット・mode・LoRA・seed を引き継ぎ、
直したい内容（--add）をプロンプトの先頭に足す。元画像は採用画像（既定。なければ最新の候補）か --candidate の番号。
差し替え案のID（p04-01b 等）で保存するので、元の要求と候補は変えない。送信は pixai_batch.py generate に任せる。

  # 頭の上に猫耳を足す（マスクも作る。白＝描き直す）
  python -X utf8 scripts/pixai_edit.py inpaint p04-01 --add "girl with cat ears on top of head" --ellipse 300,40,260,180
  # 全体を雪の場面へ寄せる（strength 0.6 は構図を保った小さな変更、0.9 は構図を保った大きな変更の例）
  python -X utf8 scripts/pixai_edit.py i2i p04-01 --add "snowy park, winter, snow" --strength 0.6

インペイントに非対応のモデル（Tsubaki.2 等、config/pixai-models.json の inpaint: false）の画像は、--model を省くと
tsubaki3 で描き直す。１タスク4枚が既定（描き足しは4枚中2枚程度で当たった。--batch-size 1 で1枚）。
確認結果・注意は docs/knowledge/pixai-composed-production.md の「インペイント」と docs/knowledge/pixai-api.md。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pixai_api as api  # noqa: E402
import pixai_batch as batch  # noqa: E402
import pixai_mask as mask_tool  # noqa: E402

INPAINT_FALLBACK = "tsubaki3"


class EditError(api.ClientError):
    pass


def source_image(root: Path, request_id: str, candidate: int | None) -> Path:
    if candidate is not None:
        path = api.project_path(root, f"{batch.CANDIDATES_DIR}/{request_id}/r{candidate:03d}.png")
        if not path.is_file():
            raise EditError(f"{request_id} の候補 r{candidate:03d}.png がありません。")
        return path
    adopted = batch.load_adopted(root)["adopted"].get(request_id, {}).get("path")
    if adopted:
        return api.project_path(root, adopted)
    found = batch.candidates(root, request_id)
    if not found:
        raise EditError(f"{request_id} の画像がありません。先に生成するか --candidate を指定してください。")
    return api.project_path(root, found[-1].relative_to(root).as_posix())


def original_settings(request: dict) -> dict:
    """v2・v1 の要求から、引き継ぐ設定を取り出す（${変数} は展開しない。送信時に展開される）。"""
    if request.get("api") == "v2":
        body = request.get("body") or {}
        style = body.get("style") or {}
        return {"prompt": body.get("prompt", ""), "negative": body.get("negativePrompt", ""), "model": body.get("modelVersionId"),
                "style": style.get("key") if style.get("type") == "preset" else None, "mode": body.get("mode"), "seed": body.get("seed"),
                "loras": {str(i["modelId"]): i.get("weight", 1) for i in body.get("loras") or []},
                "triggers": [i["triggerWords"] for i in body.get("loras") or [] if i.get("triggerWords")]}
    params = request.get("parameters") or {}
    style = params.get("modelStyle") or {}
    return {"prompt": params.get("prompts", ""), "negative": params.get("negativePrompts", ""), "model": params.get("modelId"),
            "style": style.get("keyId") if style.get("type") == "key" else None, "mode": params.get("inferenceProfile"),
            "seed": params.get("seed"), "loras": dict(params.get("lora") or {}), "triggers": []}


def join_tags(*parts: str) -> str:
    """「, 」区切りでつなぎ、同じ語は１回にする（入力の順を保つ）。"""
    seen, out = set(), []
    for part in parts:
        for tag in (t.strip() for t in part.split(",")):
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                out.append(tag)
    return ", ".join(out)


def next_id(root: Path, request_id: str) -> str:
    base = request_id.rstrip("bcdefghijklmnopqrstuvwxyz") if request_id[-1:].isalpha() and request_id[-2:-1].isdigit() else request_id
    for letter in "bcdefghijklmnopqrstuvwxyz":
        candidate = base + letter
        if not (root / batch.REQUESTS_DIR / f"{candidate}.json").exists():
            return candidate
    raise EditError("差し替え案のIDが足りません。--id で指定してください。")


def build(root: Path, opts) -> tuple[str, dict, list[str]]:
    if not batch.REQUEST_ID.fullmatch(opts.request_id):
        raise EditError("元の要求IDは英数字・-・_ で指定してください。")
    new_id = opts.id or next_id(root, opts.request_id)
    if not batch.REQUEST_ID.fullmatch(new_id):
        raise EditError("保存する要求IDは英数字・-・_ で64文字以内にしてください。")
    out = api.project_path(root, f"{batch.REQUESTS_DIR}/{new_id}.json")
    if out.exists() and not opts.force:
        raise EditError(f"{batch.REQUESTS_DIR}/{new_id}.json が既にあります。上書きするなら --force を付けてください。")
    path = api.project_path(root, f"{batch.REQUESTS_DIR}/{opts.request_id}.json")
    if not path.is_file():
        raise EditError(f"{batch.REQUESTS_DIR}/{opts.request_id}.json がありません。")
    old = original_settings(api.read_json(path))
    source = source_image(root, opts.request_id, opts.candidate)
    with Image.open(source) as image:
        width, height = image.size
    if not (512 <= width <= 1280 and 512 <= height <= 1280):
        raise EditError(f"元画像の寸法 {width}×{height} が v1 の範囲（512〜1280px）の外です（1.5k の画像は直せない）。")
    notes = []
    if opts.model:
        if opts.model not in api.MODELS:
            raise EditError(f"--model は {api.MODELS_FILE} の名前にしてください。")
        model_id = api.MODELS[opts.model]["id"]
    else:
        model_id = old["model"]
    kind = api.MODEL_TYPES.get(model_id)
    if opts.command == "inpaint" and not api.supports(model_id, kind, "inpaint"):
        if opts.model:
            raise EditError("このモデルはインペイントを使えません。--model tsubaki3 等にしてください。")
        model_id = api.MODELS[INPAINT_FALLBACK]["id"]
        kind = api.MODEL_TYPES.get(model_id)
        notes.append(f"元のモデルはインペイント非対応のため {api.MODELS[INPAINT_FALLBACK]['label']} で描き直す（背景・小物ならなじみやすい）")
    triggers = old["triggers"]
    prompt = ", ".join(p for p in [opts.add.strip(), old["prompt"].strip(), *triggers] if p)
    negative = join_tags(old["negative"], opts.negative)
    params = {"prompts": prompt, "modelId": model_id, "width": width, "height": height, "batchSize": opts.batch_size,
              "promptHelper": {"enable": False}, "mediaFile": source.relative_to(root).as_posix(), "strength": opts.strength}
    if negative:
        params["negativePrompts"] = negative
    if isinstance(old["seed"], int):
        params["seed"] = old["seed"]
    if api.supports(model_id, kind, "mode"):
        mode = old["mode"] if old["mode"] and old["model"] == model_id else api.default_mode(model_id)
        if mode:
            params["inferenceProfile"] = mode
    if old["style"] and not opts.no_style and api.supports(model_id, kind, "style"):
        params["modelStyle"] = {"type": "key", "keyId": old["style"]}
    if old["loras"]:
        if len(old["loras"]) > 3:
            raise EditError("v1 のLoRAは最大3件です。元の要求のLoRAを減らしてください。")
        params["lora"] = old["loras"]
        if old["model"] != model_id:
            notes.append("モデルが変わったため、LoRAが合わない可能性がある（送信前の確認で元モデルを点検する）")
    # マスクを保存する前に、変数を展開したコピーで要求を検証する。
    # 保存する要求は変数参照を保ち、以後の編集も反映できるようにする。
    api.prepare_request_data(root, batch.expand({"api": "v1", "parameters": params}, batch.read_variables(root), set()))
    if opts.command == "inpaint":
        if not opts.ellipse and not opts.rect:
            raise EditError("--ellipse か --rect でマスクの範囲を指定してください（左,上,幅,高さ）。")
        mask_path = api.project_path(root, f"input/pixai/masks/{new_id}.png")
        preview_path = api.project_path(root, f"input/pixai/masks/{new_id}.preview.png")
        if not opts.force and (mask_path.exists() or preview_path.exists()):
            raise EditError("同名のマスクまたは確認画像が既にあります。別の --id を使うか --force を付けてください。")
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            image.load()
            mask = mask_tool.make_mask(image.size, opts.ellipse, opts.rect, opts.blur)
            mask.save(mask_path)
            mask_tool.preview(image, mask).save(preview_path)
        params["maskMediaFile"] = mask_path.relative_to(root).as_posix()
        share = sum(mask.histogram()[128:]) / (width * height)
        if share > 0.2:
            notes.append(f"マスクが画面の{share:.0%}と大きい。範囲内の顔・表情・小物も描き変わる（顔にはかけない）")
    return new_id, {"api": "v1", "parameters": params}, notes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成済みのコマから、インペイント・i2i の要求JSONを作る（通信しない）")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, strength, text in (("inpaint", 0.75, "マスクの範囲だけを描き直す"), ("i2i", 0.6, "画像全体を描き直す")):
        cmd = sub.add_parser(name, help=text)
        cmd.add_argument("request_id", help="元のコマの要求ID（例 p04-01）")
        cmd.add_argument("--add", required=True, help="直したい内容。主語付きで書く（例 girl wearing a red beret）。プロンプトの先頭に入る")
        cmd.add_argument("--negative", default="", help="除外に足す語（例 halo）")
        cmd.add_argument("--strength", type=float, default=strength, help=f"変化量（既定 {strength}）")
        cmd.add_argument("--candidate", type=int, help="元画像の候補番号（既定は採用画像、なければ最新の候補）")
        cmd.add_argument("--model", help=f"{api.MODELS_FILE} の名前（既定は元の要求のモデル）")
        cmd.add_argument("--batch-size", type=int, choices=(1, 4), default=4, help="１タスクの枚数（既定4。4枚から選ぶ）")
        cmd.add_argument("--id", help="保存する要求ID（既定は p04-01b のように空いている差し替え案）")
        cmd.add_argument("--no-style", action="store_true", help="元の画風プリセットを引き継がない（プリセットが直したい物の原因のとき）")
        cmd.add_argument("--force", action="store_true", help="同名の要求JSONを上書きする")
        if name == "inpaint":
            cmd.add_argument("--ellipse", type=mask_tool.box, action="append", default=[], help="マスクの楕円 左,上,幅,高さ（px）")
            cmd.add_argument("--rect", type=mask_tool.box, action="append", default=[], help="マスクの長方形 左,上,幅,高さ（px）")
            cmd.add_argument("--blur", type=int, default=10, help="マスクの境界のぼかし（px）")
    opts = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        if not (root / "project.json").is_file():
            raise EditError("作品プロジェクトの scripts/ から実行してください。")
        if not 0 < opts.strength <= 1:
            raise EditError("--strength は0より大きく1以下にしてください。")
        new_id, request, notes = build(root, opts)
        out = api.project_path(root, f"{batch.REQUESTS_DIR}/{new_id}.json")
        if out.exists() and not opts.force:
            raise EditError(f"{batch.REQUESTS_DIR}/{new_id}.json が既にあります。上書きするなら --force を付けてください。")
        api.prepare_request_data(root, batch.expand(request, batch.read_variables(root), set()))  # 展開したコピーで確かめる
        out.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        params = request["parameters"]
        print(f"保存: {batch.REQUESTS_DIR}/{new_id}.json（{opts.command}、元画像 {params['mediaFile']}、strength {params['strength']}、"
              f"{params['batchSize']}枚）")
        if "maskMediaFile" in params:
            print(f"マスク: {params['maskMediaFile']}（確認用の重ね画像 {params['maskMediaFile'][:-4]}.preview.png を送信前に開く）")
        for note in notes:
            print(f"  [注意] {note}")
        print(f"送信なしの確認: python -X utf8 scripts/pixai_batch.py generate --ids {new_id}")
        print("送信（公式文書にない項目のため --allow-unverified が必要）: … generate --ids "
              f"{new_id} --execute --allow-unverified --confirm-credits --cost-note '…'")
        print(f"採用: 描き直した範囲を元の解像度で元画像と並べて確かめ、python -X utf8 scripts/pixai_batch.py adopt {opts.request_id} "
              f"--file {batch.CANDIDATES_DIR}/{new_id}/rNNN.png")
        return 0
    except (api.ClientError, OSError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
