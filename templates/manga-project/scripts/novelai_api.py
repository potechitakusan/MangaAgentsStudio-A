"""NovelAIのキー読込・契約照会・１枚生成。Python 3.10以上、追加依存なし。"""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
from http.client import HTTPException
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import secrets
import struct
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile
import zlib


# 認証ヘッダーの送信先を固定する。リダイレクトも追わない。
API_ROOT = "https://image.novelai.net"
MAX_RESPONSE = 64 * 1024 * 1024
KEY_FILES = (".secrets/novelai.env", ".secrets/.env", ".env")
KEY_SETUP_GUIDE = (
    "作品の .secrets/novelai.env に次の１行を記入してください。\n"
    "NOVELAI_API_KEY=実際のトークン\n"
    "左辺の NOVELAI_API_KEY は公開してよい設定名です。秘密にするのは右辺のトークンです。\n"
    "右辺をPersistent API tokenに置き換え、Bearerは付けません。トークンだけの１行にはしません。\n"
    "実値を会話へ貼る必要はありません。設定後は key-status で読込元を確認できます。"
)
PLAIN_PARAMETERS = {
    "width", "height", "steps", "n_samples", "seed", "sampler", "scale",
    "negative_prompt", "noise_schedule", "params_version", "cfg_rescale",
    "qualityToggle", "ucPreset", "sm", "sm_dyn", "dynamic_thresholding",
    "legacy", "legacy_v3_extend", "deliberate_euler_ancestral_bug",
    "prefer_brownian", "skip_cfg_above_sigma", "v4_prompt", "v4_negative_prompt",
    "image_format", "prompt", "tag_hint_qt", "tag_hint_uc_preset",
    "tag_hint_transparent_background", "straight_alpha",
}


class ClientError(Exception):
    """キー・入力本文・HTTP応答本文を含めない利用者向けエラー。"""


def project_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or path.drive or ".." in path.parts:
        raise ClientError("パスは作品ルート内の相対パスで指定してください。")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ClientError("作品外へ出るリンクは使用できません。")
    return resolved


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError):
        raise ClientError("JSONファイルを読み込めません。保存場所と形式を確認してください。") from None
    if not isinstance(value, dict):
        raise ClientError("JSONの最上位はオブジェクトにしてください。")
    return value


def load_key(root: Path) -> tuple[str, str]:
    value = os.environ.get("NOVELAI_API_KEY", "").strip()
    source = "環境変数 NOVELAI_API_KEY"
    diagnostics = [source + (": 値が空" if "NOVELAI_API_KEY" in os.environ else ": 未設定")]

    def invalid(location: str, reason: str) -> ClientError:
        # locationには固定の読込元だけを使い、入力行・秘密値・例外本文を含めない。
        return ClientError(f"[設定不備] {location}: {reason}\n{KEY_SETUP_GUIDE}")

    if not value:
        for relative in KEY_FILES:
            path = project_path(root, relative)
            if not path.exists():
                diagnostics.append(relative + ": ファイルなし")
                continue
            if not path.is_file():
                raise invalid(relative, "形式不正（通常の設定ファイルではありません）")
            try:
                lines = path.read_text(encoding="utf-8-sig").splitlines()
            except UnicodeError:
                raise invalid(relative, "形式不正（UTF-8のテキストとして読めません）") from None
            except OSError:
                raise invalid(relative, "読込失敗（ファイルのアクセス権を確認してください）") from None
            matches = []
            for line in lines:
                match = re.match(r"^\s*(?:export\s+)?NOVELAI_API_KEY\s*=\s*(.*?)\s*$", line)
                if not match and re.match(r"^\s*(?:export\s+)?NOVELAI_API_KEY\b", line):
                    raise invalid(relative, "形式不正（設定名と値を半角の = で区切ってください）")
                if match:
                    candidate = match.group(1)
                    if candidate.startswith(("'", '"')):
                        quote = candidate[0]
                        end = candidate.find(quote, 1)
                        if end < 0 or (candidate[end + 1:].strip() and not candidate[end + 1:].lstrip().startswith("#")):
                            raise invalid(relative, "形式不正（引用符が閉じていないか、後ろに余分な文字があります）")
                        candidate = candidate[1:end]
                    else:
                        candidate = "" if candidate.startswith("#") else re.split(r"\s+#", candidate, maxsplit=1)[0].strip()
                    matches.append(candidate)
            if len(matches) > 1:
                raise invalid(relative, "形式不正（NOVELAI_API_KEYの設定行が重複しています）")
            if not matches:
                diagnostics.append(relative + ": 設定行なし（NOVELAI_API_KEY= の行が必要です）")
            elif not matches[0].strip():
                diagnostics.append(relative + ": 値が空（= の右辺にトークンが必要です）")
            else:
                value, source = matches[0], relative
                break
    if not value:
        raise ClientError("[設定不備] 読み込めるキーがありません。\n"
                          + "\n".join(diagnostics) + "\n" + KEY_SETUP_GUIDE)
    # 値や長さは出力しない。dotenvの変数展開・コマンド実行は行わない。
    if not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", value) or value.lower() in {"your_api_key", "your_token", "replace_me"}:
        raise invalid(source, "形式不正（値に使用できない文字・空白、または置換前の例が含まれています）")
    return value, source


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_request(key: str, endpoint: str, *, payload: bytes | None = None,
                correlation_id: str | None = None) -> tuple[bytes, str]:
    if endpoint not in {"/user/subscription", "/ai/generate-image"}:
        raise ClientError("対応していないAPIです。")
    headers = {"Authorization": "Bearer " + key, "Accept": "application/json",
               "User-Agent": "MangaAgentsStudio-NovelAI/1"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if correlation_id:
        headers["x-correlation-id"] = correlation_id
    request = Request(API_ROOT + endpoint, data=payload, headers=headers)
    retry_note = ("画像生成は要求していません。自動再送はしていません。" if payload is None else
                  "自動再送はしていません。生成結果と消費を確認してから再実行してください。")
    try:
        with build_opener(NoRedirect()).open(request, timeout=180 if payload else 30) as response:
            body = response.read(MAX_RESPONSE + 1)
            content_type = response.headers.get_content_type()
    except HTTPError as error:
        status = error.code
        error.close()
        explanations = {
            401: "[認証失敗] キーを使った要求が認証されませんでした。読込元とトークンの有効性を確認してください。",
            402: "[残高不足] Anlasが不足しています。",
            403: "[アクセス拒否] 接続先が要求を拒否しました。キーの誤りとは断定できません。アクセス権や接続制限を確認してください。",
            429: "[利用制限] 利用制限に達しました。",
        }
        fallback = "[サーバーエラー] 接続先でエラーが発生しました。" if status >= 500 else "[API応答エラー] 要求を完了できませんでした。"
        raise ClientError(f"HTTP {status}: " + explanations.get(status, fallback) + " " + retry_note) from None
    except (URLError, OSError, HTTPException):
        raise ClientError("[通信障害] キーの読込後、API通信が完了しませんでした。"
                          "この結果だけではキーの正誤は判定できません。"
                          "ネットワーク・プロキシ・実行環境の接続制限を確認してください。 " + retry_note) from None
    if len(body) > MAX_RESPONSE:
        raise ClientError("API応答が保存上限を超えました。再生成する前に結果と消費を確認してください。")
    return body, content_type


def subscription(key: str) -> dict:
    body, _ = api_request(key, "/user/subscription")
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        raise ClientError("[API応答不正] 契約照会の応答がJSONではありません。キーの未設定とは別の問題です。") from None
    if not isinstance(data, dict) or type(data.get("active")) is not bool or type(data.get("tier")) is not int:
        raise ClientError("[API応答不正] 契約照会の応答形式を確認できません。キーの未設定とは別の問題です。")
    # メールアドレス・決済情報・未定義の応答項目は表示・保存しない。
    safe = {"active": data["active"], "tier": data["tier"]}
    if type(data.get("expiresAt")) is int:
        safe["expiresAt"] = data["expiresAt"]
    steps = data.get("trainingStepsLeft")
    if isinstance(steps, dict):
        safe["trainingStepsLeft"] = {name: steps[name] for name in
                                     ("fixedTrainingStepsLeft", "purchasedTrainingSteps")
                                     if type(steps.get(name)) is int}
    usage = data.get("usage")
    if isinstance(usage, dict):
        safe["usage"] = {name: usage[name] for name in ("percent", "timeUntilNextPercent")
                         if type(usage.get(name)) is int}
        if type(usage.get("isNegative")) is bool:
            safe["usage"]["isNegative"] = usage["isNegative"]
    return safe


def prepare_request(root: Path, relative: str) -> tuple[dict, bytes]:
    request = read_json(project_path(root, relative))
    if set(request) != {"action", "input", "model", "parameters"} or request.get("action") != "generate":
        raise ClientError("要求はaction=generate、input、model、parametersの４項目にしてください。")
    if not isinstance(request["input"], str) or not request["input"].strip():
        raise ClientError("inputへ生成プロンプトを設定してください。")
    if not isinstance(request["model"], str) or not re.fullmatch(r"nai-diffusion-[a-z0-9.-]+", request["model"]):
        raise ClientError("公式仕様で確認したモデルIDをmodelへ設定してください。")
    params = request["parameters"]
    if not isinstance(params, dict):
        raise ClientError("parametersはオブジェクトにしてください。")
    layout = read_json(root / "config/page-layout.json")
    canvas = layout.get("generationCanvas")
    if not isinstance(canvas, dict):
        raise ClientError("先にconfig/page-layout.jsonのgenerationCanvasへ採用したwidth・heightを設定してください。")
    for dimension in ("width", "height"):
        size = canvas.get(dimension)
        if type(size) is not int or size < 64 or size % 64:
            raise ClientError("生成希望寸法は64以上の64の倍数で指定してください。")
        if dimension in params and (type(params[dimension]) is not int or params[dimension] != size):
            raise ClientError("要求寸法とgenerationCanvasが一致していません。採用寸法をそろえてください。")
        params[dimension] = size
    params.setdefault("n_samples", 1)
    if type(params["n_samples"]) is not int or params["n_samples"] != 1:
        raise ClientError("１回の生成枚数は１枚だけにしてください。")
    params.setdefault("steps", 23 if request["model"].startswith("nai-diffusion-5") else 28)
    if type(params["steps"]) is not int or not 1 <= params["steps"] <= 50:
        raise ClientError("stepsは1〜50の整数にしてください。Opusの既定は28以下です。")
    params.setdefault("image_format", "png")
    if params["image_format"] != "png":
        raise ClientError("保存形式はPNGだけに対応しています。")
    if type(params.get("seed")) is not int or not 0 <= params["seed"] <= 4294967295:
        raise ClientError("seedを0〜4294967295の整数で固定してください。")
    if not isinstance(params.get("sampler"), str) or not params["sampler"].strip():
        raise ClientError("公式仕様で確認したsamplerを設定してください。")
    if type(params.get("scale")) not in (int, float) or not math.isfinite(params["scale"]) or params["scale"] <= 0:
        raise ClientError("scaleを正の有限数で設定してください。")
    if request["model"].startswith(("nai-diffusion-4", "nai-diffusion-5")):
        params.setdefault("v4_prompt", {"caption": {"base_caption": request["input"], "char_captions": []},
                                        "use_coords": False, "use_order": True})
        params.setdefault("v4_negative_prompt", {"caption": {"base_caption": params.get("negative_prompt", ""),
                                                            "char_captions": []}})
    try:
        payload = json.dumps(request, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError):
        raise ClientError("要求にJSONとして送信できない値があります。") from None
    return request, payload


def check_cost(args, request: dict) -> None:
    if not args.cost_note or not args.cost_note.strip():
        raise ClientError("実行には--cost-noteで今回の全設定に対する費用確認の根拠を指定してください。")
    if not (args.confirm_zero_anlas or args.allow_anlas):
        raise ClientError("費用未確認です。0 Anlas確認またはユーザーの明示的な有料利用指示が必要です。")
    if args.confirm_zero_anlas:
        params = request["parameters"]
        if params["steps"] > 28 or params["width"] * params["height"] > 1048576:
            raise ClientError("この要求はキットのOpus無消費候補の寸法・steps範囲を超えています。")
        if set(params) - PLAIN_PARAMETERS:
            raise ClientError("追加機能・未確認パラメーターがあります。無消費扱いで送信できません。")
        if request["model"].startswith("nai-diffusion-5") and not args.confirm_v5_allowance:
            raise ClientError("V5は今回の生成に足りるOpus利用上限の確認も必要です。")


def image_bytes(body: bytes, content_type: str) -> bytes:
    try:
        if content_type in {"application/zip", "application/x-zip-compressed"} or body.startswith(b"PK\x03\x04"):
            # ZIP内のパスは使わず、PNG１枚をメモリ内で取り出す。
            with zipfile.ZipFile(BytesIO(body)) as archive:
                members = [item for item in archive.infolist() if not item.is_dir() and item.filename.lower().endswith(".png")]
                if len(members) != 1 or members[0].file_size > MAX_RESPONSE:
                    raise ClientError("生成応答のPNG枚数またはサイズが想定外です。")
                return archive.read(members[0])
        data = json.loads(body)
        images = data.get("images") if isinstance(data, dict) else None
        if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
            raise ClientError("生成応答のimages形式を確認できません。")
        return base64.b64decode(images[0]["image"], validate=True)
    except (ValueError, TypeError, KeyError, binascii.Error, zipfile.BadZipFile, RuntimeError, NotImplementedError):
        raise ClientError("生成応答からPNGを取り出せません。自動再生成はしていません。") from None


def png_size(data: bytes) -> tuple[int, int]:
    if len(data) < 33 or data[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR":
        raise ClientError("生成結果がPNGではありません。")
    width, height = struct.unpack(">II", data[16:24])
    if not width or not height:
        raise ClientError("生成PNGの寸法が不正です。")
    offset, has_pixels = 8, False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        end = offset + 12 + length
        if end > len(data):
            break
        kind = data[offset + 4:offset + 8]
        expected = struct.unpack(">I", data[end - 4:end])[0]
        if zlib.crc32(data[offset + 4:end - 4]) & 0xFFFFFFFF != expected:
            raise ClientError("生成PNGのCRCが一致しません。自動再生成はしていません。")
        has_pixels = has_pixels or kind == b"IDAT"
        if kind == b"IEND":
            if length == 0 and end == len(data) and has_pixels:
                return width, height
            break
        offset = end
    raise ClientError("生成PNGが途中で切れているか、構造が不正です。")


def write_record(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary.replace(path)


def run(args, root: Path) -> None:
    if args.command in {"key-status", "status"}:
        key, source = load_key(root)
        print("キー読込済み（値は非表示）: " + source)
        if args.command == "status":
            result = subscription(key)
            print("契約照会成功（画像生成なし）")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print("契約照会だけでは生成費用・V5の残枠を確認済みと扱いません。")
        return
    request, payload = prepare_request(root, args.request)
    digest = hashlib.sha256(payload).hexdigest()
    params = request["parameters"]
    print(f"要求: {request['model']} / {params['width']}×{params['height']}px / {params['steps']} steps / １枚")
    print("要求SHA-256: " + digest)
    if not args.execute:
        print("送信なし。実行には--executeと費用確認の指定が必要です。")
        return
    check_cost(args, request)
    key, source = load_key(root)
    # 誤って要求・費用メモへキーを貼った場合も送信・保存しない。
    if key in payload.decode("utf-8") or key in args.cost_note:
        raise ClientError("要求または費用メモへ認証情報を含めないでください。")
    state = subscription(key)
    if args.confirm_zero_anlas and (state["active"] is not True or state["tier"] != 3):
        raise ClientError("有効なOpus契約を確認できないため、無消費扱いの生成を停止しました。")
    if args.confirm_zero_anlas and request["model"].startswith("nai-diffusion-5"):
        usage = state.get("usage", {})
        if usage.get("isNegative") is True or ("percent" in usage and usage["percent"] <= 0):
            raise ClientError("契約照会がV5利用上限の不足を示しています。回復を待ってください。")
    output = project_path(root, args.output)
    if not output.is_relative_to(root / "output") or output.suffix.lower() != ".png":
        raise ClientError("保存先はoutput/内のPNGにしてください。")
    record_path = output.with_suffix(".novelai.json")
    if output.exists() or record_path.exists() or record_path.with_suffix(".tmp").exists():
        raise ClientError("同名の画像または実行記録があります。再送せず、記録を確認してください。")
    output.parent.mkdir(parents=True, exist_ok=True)
    correlation_id = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(6))
    record = {"schemaVersion": 1, "status": "送信準備済み", "startedAt": datetime.now(timezone.utc).isoformat(),
              "correlationId": correlation_id, "requestSha256": digest, "request": request,
              "credentialSource": source, "subscriptionBefore": state,
              "costMode": "zero_anlas_confirmed" if args.confirm_zero_anlas else "paid_authorized",
              "costNote": args.cost_note, "v5AllowanceConfirmed": args.confirm_v5_allowance,
              "actualAnlasCost": None, "output": output.relative_to(root).as_posix()}
    # 同じ保存先への並行実行も送信前に止める。
    with record_path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    try:
        body, content_type = api_request(key, "/ai/generate-image", payload=payload, correlation_id=correlation_id)
        png = image_bytes(body, content_type)
        width, height = png_size(png)
        with output.open("xb") as stream:
            stream.write(png)
        record.update(status="PNG保存済み", actualCanvas={"width": width, "height": height},
                      finishedAt=datetime.now(timezone.utc).isoformat())
        write_record(record_path, record)
    except (ClientError, OSError):
        record["status"] = "処理未完了・再送前に結果と消費の確認が必要"
        try:
            write_record(record_path, record)
        except OSError:
            pass
        raise
    print("保存: " + output.relative_to(root).as_posix())
    print(f"生成実寸: {width}×{height}px。ページ設定に従って枠・最終PNGへ反映してください。")
    print("Anlasの実消費は未確認です。実行記録のactualAnlasCostはnullのまま保持しました。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, epilog=KEY_SETUP_GUIDE,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("key-status", help="キーの読込元だけを確認する（通信なし）",
                        epilog=KEY_SETUP_GUIDE, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands.add_parser("status", help="契約を照会する（生成なし）",
                        epilog=KEY_SETUP_GUIDE, formatter_class=argparse.RawDescriptionHelpFormatter)
    generate = commands.add_parser("generate", help="１枚生成。既定は送信しない要求確認")
    generate.add_argument("--request", required=True, help="作品内の生成要求JSON")
    generate.add_argument("--output", default="output/novelai/test-001.png")
    generate.add_argument("--execute", action="store_true", help="人が依頼した生成を１回送信する")
    costs = generate.add_mutually_exclusive_group()
    costs.add_argument("--confirm-zero-anlas", action="store_true", help="今回の全設定で0 Anlasを確認済み")
    costs.add_argument("--allow-anlas", action="store_true", help="今回の設定でのAnlas消費をユーザーが明示許可済み")
    generate.add_argument("--confirm-v5-allowance", action="store_true", help="今回のV5生成に足りる利用上限を確認済み")
    generate.add_argument("--cost-note", help="確認方法・日時・許可範囲。認証情報は書かない")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if not (root / "project.json").is_file():
            raise ClientError("新規作品を作成して開き直し、作品側のスクリプトを使ってください。")
        run(args, root)
    except ClientError as error:
        print("エラー: " + str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, UnicodeError):
        print("エラー: ファイルまたは設定の処理に失敗しました。キーや応答本文は表示しません。実行記録を確認してください。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
