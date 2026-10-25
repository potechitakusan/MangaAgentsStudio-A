"""PixAIのキー読込・接続確認・１タスク生成（送信 → 完了待ち → 画像保存）。Python 3.10以上、追加依存なし。

PNG以外の応答（WebP・JPEG）をPNGへ変換するときだけ Pillow を使う（作品の組版の既存要件）。

  python -X utf8 scripts/pixai_api.py key-status                    # キーの読込元だけ（通信なし）
  python -X utf8 scripts/pixai_api.py status                        # 接続・認証の確認（画像生成なし）
  python -X utf8 scripts/pixai_api.py generate --request <要求JSON>  # 既定は送信しない確認
  python -X utf8 scripts/pixai_api.py fetch --record <実行記録>       # 完了待ちが途切れたタスクを taskId で取得し直す
  python -X utf8 scripts/pixai_api.py upload --file <画像> --execute # 参照・i2i用の画像をアップロードして mediaId を得る

公式仕様（docs/knowledge/pixai-api.md に出典・確認日）
  POST /v2/image/create   現行の生成API。modelVersionId・prompt・aspectRatio・size・mode・style・loras（最大5）等
  POST /v1/task           旧形式。parameters の中に prompts・modelId・width・height・lora・upscale・enableADetailer 等
  GET  /v1/task/{taskId}  状態（waiting・running・completed・failed・cancelled）と outputs.mediaIds・mediaUrls
  GET  /v1/media/{id}     メディアの情報（urls の PUBLIC 等）
  POST /v1/media/upload   画像の本体をそのまま送り、mediaId を得る
ポーリングは1.5秒に1回以下（公式）。このスクリプトは3秒から始めて間隔を広げる。生成画像は無期限には保存されないため、完了後すぐ保存する。
クレジットの残高・消費を照会するAPIは公式文書にない。送信には利用者の明示の許可（--confirm-credits）と確認内容（--cost-note）が必要。
"""

from __future__ import annotations

import argparse
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
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zlib


# 認証ヘッダーの送信先を固定する。認証付きの要求ではリダイレクトを追わない。
API_ROOT = "https://api.pixai.art"
MAX_RESPONSE = 64 * 1024 * 1024
KEY_NAME = "PIXAI_API_KEY"
KEY_FILES = (".secrets/pixai.env", ".secrets/.env", ".env")
KEY_SETUP_GUIDE = (
    "作品の .env（または .secrets/pixai.env）に次の１行を記入してください。\n"
    "PIXAI_API_KEY=実際のキー\n"
    "左辺の PIXAI_API_KEY は公開してよい設定名です。秘密にするのは右辺のキーです。\n"
    "キーは https://pixai.art/profile/edit/api で作ります。Bearerは付けません。キーだけの１行にはしません。\n"
    "実値を会話へ貼る必要はありません。設定後は key-status で読込元を確認できます。"
)
UPLOADS = "output/pixai/uploads.json"

# モデルの一覧（名前 → modelVersionId・種類・送れる項目）。出典・確認日はファイル内に書く。
# 作品のこのファイルへモデルを足すのは scripts/pixai_models.py add。
MODELS_FILE = "config/pixai-models.json"


def load_models(path: Path) -> dict:
    if not path.is_file():
        return {}
    models = json.loads(path.read_text(encoding="utf-8")).get("models") or {}
    for name, model in models.items():
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,40}", name) or not re.fullmatch(r"[0-9]{6,30}", str(model.get("id", ""))) \
                or model.get("type") not in {"dit", "sdxl"}:
            raise SystemExit(f"{MODELS_FILE} の {name} が不正です（名前は英小文字・数字、id は数字、type は dit か sdxl）。")
    return models


MODELS = load_models(Path(__file__).resolve().parent.parent / MODELS_FILE)
MODEL_TYPES = {m["id"]: m["type"] for m in MODELS.values()}
MODELS_BY_ID = {m["id"]: m for m in MODELS.values()}
# 作品で確かめたLoRAの元モデル・利用条件の記録（scripts/pixai_models.py lora が書く。１回確かめたら取り直さない）。
LORAS_FILE = "config/pixai-loras.json"


def lora_notes(root: Path, model_id: str, lora_ids: list[str]) -> list[str]:
    """LoRAと生成モデルの組み合わせを、作品の記録だけで点検する（通信しない）。"""
    path = root / LORAS_FILE
    records = (json.loads(path.read_text(encoding="utf-8")).get("loras") or {}) if path.is_file() else {}
    model = MODELS_BY_ID.get(model_id, {})
    notes = []
    for lora_id in lora_ids:
        record = records.get(lora_id)
        if record is None:
            notes.append(f"LoRA {lora_id} の元モデルは未確認（scripts/pixai_models.py lora --url <LoRAのページ> で記録すると点検する）")
            continue
        label = record.get("title") or lora_id
        base_type, base_id = record.get("baseModelType"), record.get("baseModelId")
        if base_id and model.get("modelId") and base_id != model["modelId"]:
            notes.append(f"LoRA {label} は別のモデル（モデルID {base_id}）用。{model.get('label', model_id)} では効かないか崩れる可能性がある")
        elif base_type and model.get("pixaiType") and base_type != model["pixaiType"]:
            notes.append(f"LoRA {label} の元モデルの種類 {base_type} が、生成モデル {model.get('label', model_id)}（{model['pixaiType']}）と違う。"
                         "効かないか崩れる可能性がある")
        elif not model.get("pixaiType"):
            notes.append(f"生成モデルの種類が一覧にないため、LoRA {label}（{base_type or '種類不明'}）との組み合わせは点検していない")
        if record.get("commercialUse") is False:
            notes.append(f"LoRA {label} は商用利用が許可されていない（公開・販売の条件を利用者が確認する）")
    return notes
SAMPLERS = ("Euler a", "Euler", "LMS", "Heun", "DPM2 Karras", "DPM2 a Karras", "DDIM", "DPM++ 2M Karras",
            "DPM++ 2S a Karras", "DPM++ SDE Karras", "DPM++ 2M SDE Karras", "Restart")
# 出典: platform.pixai.art/en/docs/references/supported-resolutions（2026-10-25確認）。
RESOLUTIONS = {
    "1:1": ((1024, 1024), (1536, 1536)), "2:3": ((848, 1280), (1024, 1536)), "3:2": ((1280, 848), (1536, 1024)),
    "3:4": ((864, 1152), (1152, 1536)), "4:3": ((1152, 864), (1536, 1152)), "3:5": ((768, 1280), (912, 1536)),
    "5:3": ((1280, 768), (1536, 912)), "9:16": ((720, 1280), (864, 1536)), "16:9": ((1280, 720), (1536, 864)),
    "1:3": ((512, 1536), (512, 1536)), "3:1": ((1536, 512), (1536, 512)),
}
SIZES = ("1k", "1.5k")
MODES = ("lite", "standard", "pro", "ultra")
# 出典: v2 createImage の style.key（2026-10-25確認）。Tsubaki.2・Tsubaki.3 だけで有効、他のモデルでは無視される。
STYLE_PRESETS = {
    "anime-watercolor-impasto": "Watercolor Glow", "art-crayon": "Art Crayon", "bold-line-soft-color": "Glint & Gloom",
    "chibi": "Chibi", "classic-japanese": "Classic Anime", "clean-flat-illustration": "Clean Flat-Illustration",
    "colored-pencil-grain": "Chromatic Pencil", "cool-warm-oil-contrast": "Seasonal Glow", "desaturated-cool": "Cool Softlight",
    "flat-anime-pastel": "Pastel Flat", "glossy-glass-anime": "Glassy Anime", "grey-blocks-lineless": "Grey Wash",
    "hard-line-monochrome-accent": "Sharp Ink", "high-contrast-retro-vivid": "Neon Vivid", "holographic": "Hyper Pop",
    "korean-style": "Polished Manhwa", "lineart-watercolor-airy": "Luminous Wash",
    "low-saturation-expressive-eyes": "Muted & Transparent", "lucid-dreamy": "Lucid Dreamy",
    "luminous-retro-impasto": "Luminous Impasto", "minimal-flat-color": "Minimal Flat", "modern-oil-glamour": "Modern Glam Anime",
    "moe-pastel": "Moe Pastel", "oil-watercolor-blend": "Water-Infused Oil", "painterly-doodle": "Tender Brushstroke",
    "paper-watercolor": "Soft Aqueous", "pencil-sketch": "Pencil Sketch", "poster-graffiti": "Neon Poster",
    "retro-comic-fusion": "Retro Fusion", "retro-oil-glamour": "Retro Glam Anime", "retro-tv-anime": "90s Retro-Cell",
    "semi-realistic": "Semi-Real", "stable-vaporwave": "Neon Vaporwave", "tinted-sketch": "Tinted Sketch",
    "vintage-collage": "Vintage Collage",
}
V2_KEYS = {"modelVersionId", "prompt", "negativePrompt", "aspectRatio", "size", "mode", "style", "loras", "seed",
           "batchSize", "sampling", "promptHelper"}
# v1 の公式文書（createGenerationTask、2026-10-25確認）に載っている項目。
V1_DOCUMENTED = {"prompts", "modelId", "width", "height", "lora", "batchSize", "inferenceProfile", "modelStyle",
                 "enableTile", "upscale", "upscaleSampler", "enableADetailer", "promptHelper"}
# 公式JavaScriptクライアント（github.com/pixai-art/pixai-client-js の parameters.types.ts）の型にあり、現行の公式文書にない項目。
# 送るには --allow-unverified が必要。i2i（mediaId・strength）・ControlNet・IP-Adapter（参照画像）はここに入る。
V1_UNVERIFIED = {"negativePrompts", "seed", "samplingSteps", "samplingMethod", "cfgScale", "clipSkip", "mediaId", "mediaUrl",
                 "strength", "maskMediaId", "maskMediaUrl", "controlNets", "ipAdapter", "latentCouple", "vaeModelId",
                 "upscaleDenoisingSteps", "upscaleDenoisingStrength", "upscaler", "enlarge", "enlargeModel"}
CONTROLNET_TYPES = ("dwpose", "openpose_full", "canny", "depth", "hed", "mlsd", "openpose", "seg", "normal", "scribble")
# 作品内の画像を指す、このキット独自の項目。送信時にアップロードして mediaId へ置き換える（PixAIへは送らない名前）。
LOCAL_FILE_KEYS = {"mediaFile": "mediaId", "maskMediaFile": "maskMediaId"}
IMAGE_TYPES = {b"\x89PNG\r\n\x1a\n": ("image/png", ".png"), b"\xff\xd8\xff": ("image/jpeg", ".jpg"),
               b"RIFF": ("image/webp", ".webp"), b"GIF8": ("image/gif", ".gif")}
TERMINAL = {"completed", "failed", "cancelled"}


class ClientError(Exception):
    """キー・入力本文を含めない利用者向けエラー。"""


class RejectedError(ClientError):
    """タスクを作らずに拒否された（HTTP 4xx）。再送しても消費の重複にはならないが、原因を直してから送る。"""


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


def write_record(path: Path, data: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    # Windowsでは、ウイルス対策・検索のインデックス等が一瞬ファイルを開いていると置き換えが拒否される（2026-10-25に送信直前で発生）。
    for attempt in range(5):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- キー

def load_key(root: Path) -> tuple[str, str]:
    value = os.environ.get(KEY_NAME, "").strip()
    source = "環境変数 " + KEY_NAME
    diagnostics = [source + (": 値が空" if KEY_NAME in os.environ else ": 未設定")]

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
                match = re.match(r"^\s*(?:export\s+)?PIXAI_API_KEY\s*=\s*(.*?)\s*$", line)
                if not match and re.match(r"^\s*(?:export\s+)?PIXAI_API_KEY\b", line):
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
                raise invalid(relative, "形式不正（PIXAI_API_KEYの設定行が重複しています）")
            if not matches:
                diagnostics.append(relative + ": 設定行なし（PIXAI_API_KEY= の行が必要です）")
            elif not matches[0].strip():
                diagnostics.append(relative + ": 値が空（= の右辺にキーが必要です）")
            else:
                value, source = matches[0], relative
                break
    if not value:
        raise ClientError("[設定不備] 読み込めるキーがありません。\n" + "\n".join(diagnostics) + "\n" + KEY_SETUP_GUIDE)
    # 値や長さは出力しない。dotenvの変数展開・コマンド実行は行わない。
    if not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", value) or value.lower() in {"your_api_key", "your_key", "replace_me"}:
        raise invalid(source, "形式不正（値に使用できない文字・空白、または置換前の例が含まれています）")
    return value, source


# ---------------------------------------------------------------- 通信

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


ENDPOINT = re.compile(r"/v2/image/create|/v1/task|/v1/task/[0-9]{1,30}|/v1/media/[0-9]{1,30}|/v1/media/upload")


def error_detail(body: bytes, key: str) -> str:
    """応答のmessage・codeだけを短く示す（入力エラーの原因を直すため）。キーは含めない。"""
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return ""
    items = data.get("errors") if isinstance(data, dict) and isinstance(data.get("errors"), list) else [data]
    parts = []
    for item in items[:3]:
        if isinstance(item, dict):
            text = " ".join(str(item[k]) for k in ("code", "message") if isinstance(item.get(k), (str, int)))
            parts.append(text.replace(key, "<KEY>")[:300])
    return ("（応答: " + " / ".join(p for p in parts if p) + "）") if any(parts) else ""


def api_request(key: str, method: str, endpoint: str, *, payload: bytes | None = None,
                content_type: str = "application/json", timeout: float = 60) -> tuple[int, bytes]:
    if not ENDPOINT.fullmatch(endpoint) or method not in {"GET", "POST"}:
        raise ClientError("対応していないAPIです。")
    # PixAIのAPIはContent-Typeのない要求をCSRF対策で拒否することがあるため、GETにも application/json を付ける。
    headers = {"Authorization": "Bearer " + key, "Accept": "application/json", "User-Agent": "MangaAgentsStudio-PixAI/1",
               "Content-Type": content_type}
    request = Request(API_ROOT + endpoint, data=payload, headers=headers, method=method)
    creating = endpoint in {"/v2/image/create", "/v1/task"}
    retry_note = ("自動再送はしていません。タスクができていないか、実行記録とPixAIの生成履歴・クレジットを確認してから再実行してください。"
                  if creating else "画像生成は要求していません。")
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE + 1)
            status = response.status
    except HTTPError as error:
        status = error.code
        detail = error_detail(error.read(4096), key)
        error.close()
        explanations = {
            400: "[入力エラー] 要求の内容が受け付けられませんでした。",
            401: "[認証失敗] キーを使った要求が認証されませんでした。読込元とキーの有効性を確認してください。",
            402: "[クレジット不足] クレジットが不足しています。",
            403: "[アクセス拒否] 接続先が要求を拒否しました。キーの権限や利用条件を確認してください。",
            404: "[見つからない] 指定のタスク・メディアがありません。",
            422: "[入力エラー] 要求の値が受け付けられませんでした。",
            429: "[利用制限] 同時に待機できるタスク数（公式は10件）か利用制限に達しました。",
        }
        fallback = "[サーバーエラー] 接続先でエラーが発生しました。" if status >= 500 else "[API応答エラー] 要求を完了できませんでした。"
        message = f"HTTP {status}: " + explanations.get(status, fallback) + detail
        if "inferenceProfile" in detail:
            message += " このモデルでは送った mode が使えません。別の mode（pro・ultra 等）が必要な可能性があります。"
        if creating and 400 <= status < 500:
            raise RejectedError(message + " タスクは作られていません。原因を直してから送ってください。") from None
        raise ClientError(message + " " + retry_note) from None
    except (URLError, OSError, HTTPException):
        raise ClientError("[通信障害] API通信が完了しませんでした。この結果だけではキーの正誤は判定できません。"
                          "ネットワーク・プロキシ・実行環境の接続制限を確認してください。 " + retry_note) from None
    if len(body) > MAX_RESPONSE:
        raise ClientError("API応答が保存上限を超えました。")
    return status, body


def api_json(key: str, method: str, endpoint: str, **kwargs) -> dict:
    _, body = api_request(key, method, endpoint, **kwargs)
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        raise ClientError("[API応答不正] 応答がJSONではありません。") from None
    if not isinstance(data, dict):
        raise ClientError("[API応答不正] 応答の形式を確認できません。")
    return data


def auth_check(key: str) -> str:
    """存在しないタスクIDを照会し、404（認証は通った）か401（キーが無効）かを見る。画像生成・クレジット消費はしない。"""
    try:
        api_request(key, "GET", "/v1/task/0", timeout=30)
    except ClientError as error:
        if str(error).startswith("HTTP 404"):
            return "認証成功（存在しないタスクの照会に404。画像生成なし）"
        raise
    return "認証成功（画像生成なし）"


def download(url: str) -> bytes:
    """公開URLから画像を取得する。認証ヘッダーは付けない（他のホストへキーを送らない）。"""
    if urlparse(url).scheme != "https":
        raise ClientError("画像のURLがhttpsではありません。")
    request = Request(url, headers={"User-Agent": "MangaAgentsStudio-PixAI/1"})
    try:
        with build_opener().open(request, timeout=120) as response:
            if urlparse(response.geturl()).scheme != "https":
                raise ClientError("画像の取得先がhttpsではありません。")
            body = response.read(MAX_RESPONSE + 1)
    except HTTPError as error:
        error.close()
        raise ClientError(f"HTTP {error.code}: 画像を取得できませんでした（生成画像は無期限には保存されません）。") from None
    except (URLError, OSError, HTTPException):
        raise ClientError("[通信障害] 画像を取得できませんでした。taskIdで取得し直せます（fetch）。") from None
    if len(body) > MAX_RESPONSE:
        raise ClientError("画像が保存上限を超えました。")
    return body


# ---------------------------------------------------------------- 画像

def image_kind(data: bytes) -> tuple[str, str] | None:
    for magic, kind in IMAGE_TYPES.items():
        if data.startswith(magic) and (magic != b"RIFF" or data[8:12] == b"WEBP"):
            return kind
    return None


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
            raise ClientError("生成PNGのCRCが一致しません。")
        has_pixels = has_pixels or kind == b"IDAT"
        if kind == b"IEND":
            if length == 0 and end == len(data) and has_pixels:
                return width, height
            break
        offset = end
    raise ClientError("生成PNGが途中で切れているか、構造が不正です。")


def as_png(data: bytes) -> tuple[bytes, str]:
    """PNGはそのまま、WebP・JPEGはPillowでPNGへ変換する。元の形式も返す。"""
    kind = image_kind(data)
    if kind is None:
        raise ClientError("生成結果が画像ではありません。")
    if kind[0] == "image/png":
        return data, kind[0]
    try:
        from PIL import Image
    except ImportError:
        raise ClientError("PNG以外の画像をPNGへ変換するには Pillow が必要です（requirements-composition.txt）。") from None
    with Image.open(BytesIO(data)) as image:
        out = BytesIO()
        image.convert("RGBA" if "A" in image.getbands() else "RGB").save(out, format="PNG")
    return out.getvalue(), kind[0]


# ---------------------------------------------------------------- 要求の検証

def default_mode(model_id: str) -> str | None:
    """組み立て時に補う mode。一覧で決まっていなければ送らない（サーバーの既定）。"""
    return MODELS_BY_ID.get(model_id, {}).get("default_mode")


def supports(model_id: str, kind: str | None, feature: str) -> bool:
    """mode・style・negativePrompt・controlnet を送れるか。一覧になければ種類から判断する（mode・style はDiTだけ）。"""
    model = MODELS_BY_ID.get(model_id, {})
    if feature in model:
        return bool(model[feature])
    return kind == "dit" if feature in ("mode", "style") else True


def check_mode(model_id: str, mode: str, kind: str | None, notes: list[str]) -> None:
    """既知のモデルで拒否を確認済みの mode は送信前に止め、未確認の mode は注意を残す。"""
    model = MODELS_BY_ID.get(model_id)
    if model is None:
        if kind == "dit":
            notes.append(f"既知でないDiTのモデルに mode {mode} を付けた。使える mode は未確認（拒否は4xxでタスクは作られない）")
        return
    if mode in model.get("modes_rejected", ()):
        raise ClientError(f"{model['label']} は mode {mode} を拒否します（確認済み）。"
                          + "・".join(model.get("modes_accepted", ())) + " を使ってください。")
    if mode not in model.get("modes_accepted", ()):
        notes.append(f"{model['label']} で mode {mode} が受理されるかは未確認（拒否は4xxでタスクは作られない）")


def model_type(model_id: str, request: dict) -> str | None:
    """既知のモデルIDの種類（dit・sdxl）。要求の model_type（送信しない注記）でも指定できる。"""
    hint = request.get("model_type")
    if hint is not None and hint not in {"dit", "sdxl"}:
        raise ClientError("model_type は dit か sdxl にしてください（送信しない注記）。")
    return MODEL_TYPES.get(model_id) or hint


def layout_aspect(root: Path) -> str | None:
    """config/page-layout.json の generationCanvas に最も近い縦横比。"""
    layout = root / "config/page-layout.json"
    canvas = read_json(layout).get("generationCanvas") if layout.is_file() else None
    if not isinstance(canvas, dict) or not all(type(canvas.get(k)) is int and canvas[k] > 0 for k in ("width", "height")):
        return None
    return closest_aspect(canvas["width"], canvas["height"])


def closest_aspect(width: int, height: int) -> str:
    target = math.log(width / height)
    return min(RESOLUTIONS, key=lambda r: abs(math.log(RESOLUTIONS[r][0][0] / RESOLUTIONS[r][0][1]) - target))


def output_size(body: dict) -> tuple[int, int]:
    return RESOLUTIONS[body["aspectRatio"]][SIZES.index(body["size"])]


def check_id(value, label: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{6,30}", value):
        raise ClientError(f"{label} はPixAIのバージョンID（数字の文字列。モデルページのURLの最後の部分）にしてください。")


def check_seed(value) -> None:
    if type(value) is not int or not 0 <= value <= 4294967295:
        raise ClientError("seedは0〜4294967295の整数にしてください（省略するとランダム）。")


def prepare_v2(root: Path, request: dict) -> list[str]:
    body = request["body"]
    if not isinstance(body, dict):
        raise ClientError("body はオブジェクトにしてください。")
    unknown = set(body) - V2_KEYS
    if "modelId" in unknown:
        raise ClientError("v2 は modelId ではなく modelVersionId を使います（modelId は公式に非推奨）。")
    if "callbackUrl" in unknown:
        raise ClientError("callbackUrl は使いません。完了はこのスクリプトが照会して確認します。")
    if unknown:
        raise ClientError("v2 の公式文書にない項目があります: " + ", ".join(sorted(unknown)))
    check_id(body.get("modelVersionId"), "modelVersionId")
    if not isinstance(body.get("prompt"), str) or not body["prompt"].strip():
        raise ClientError("body.prompt へ生成プロンプトを設定してください。")
    if not isinstance(body.get("negativePrompt", ""), str):
        raise ClientError("negativePrompt は文字列にしてください。")
    if "aspectRatio" not in body:
        aspect = layout_aspect(root)
        if aspect is None:
            raise ClientError("要求に aspectRatio を書くか、config/page-layout.json の generationCanvas を設定してください。")
        body["aspectRatio"] = aspect
    if body["aspectRatio"] not in RESOLUTIONS:
        raise ClientError("aspectRatio は " + "・".join(RESOLUTIONS) + " のいずれかにしてください。")
    body.setdefault("size", "1k")
    if body["size"] not in SIZES:
        raise ClientError("size は 1k か 1.5k にしてください。")
    kind = model_type(body["modelVersionId"], request)
    notes = []
    if "mode" in body:
        if body["mode"] not in MODES:
            raise ClientError("mode は " + "・".join(MODES) + " のいずれかにしてください。")
        if kind == "sdxl" or not supports(body["modelVersionId"], kind, "mode"):
            raise ClientError("mode は Tsubaki.2・Tsubaki.3 系だけで使えます。他のモデルでは公式に400で拒否されます。")
        check_mode(body["modelVersionId"], body["mode"], kind, notes)
    if "style" in body:
        style = body["style"]
        if not isinstance(style, dict) or style.get("type") not in {"preset", "custom"}:
            raise ClientError('style は {"type": "preset", "key": …} か {"type": "custom", "custom": …} にしてください。')
        if style["type"] == "preset" and (set(style) != {"type", "key"} or style["key"] not in STYLE_PRESETS):
            raise ClientError("style.key は公式のプリセット名にしてください（pixai_compose.py --list-styles で一覧）。")
        if style["type"] == "custom" and (set(style) != {"type", "custom"} or not isinstance(style["custom"], str) or not style["custom"].strip()):
            raise ClientError("style.custom に画風の文を書いてください。")
        if kind == "sdxl" or not supports(body["modelVersionId"], kind, "style"):
            notes.append("style は Tsubaki.2・Tsubaki.3 系だけで有効。このモデルでは公式に無視される")
    if body.get("negativePrompt") and not supports(body["modelVersionId"], kind, "negativePrompt"):
        notes.append("このモデルのページでは除外（negativePrompt）に非対応と表示されている。効かない可能性がある")
    loras = body.get("loras", [])
    if not isinstance(loras, list) or len(loras) > 5:
        raise ClientError("loras は最大5件の配列にしてください。")
    for index, item in enumerate(loras, 1):
        if not isinstance(item, dict) or set(item) - {"modelId", "weight", "triggerWords"}:
            raise ClientError(f"loras の{index}件目は modelId・weight・triggerWords だけにしてください。")
        check_id(item.get("modelId"), f"loras の{index}件目の modelId")
        weight = item.get("weight", 1)
        if type(weight) not in (int, float) or not math.isfinite(weight) or not 0 <= weight <= 1:
            raise ClientError(f"loras の{index}件目の weight は0〜1にしてください。")
        if not isinstance(item.get("triggerWords", ""), str):
            raise ClientError(f"loras の{index}件目の triggerWords は文字列にしてください。")
    body.setdefault("batchSize", 1)
    if body["batchSize"] not in (1, 4) or type(body["batchSize"]) is not int:
        raise ClientError("batchSize は1か4にしてください（公式の値）。")
    if "sampling" in body:
        sampling = body["sampling"]
        if not isinstance(sampling, dict) or set(sampling) - {"method", "steps", "cfgScale"}:
            raise ClientError("sampling は method・steps・cfgScale だけにしてください。")
        if "method" in sampling and sampling["method"] not in SAMPLERS:
            raise ClientError("sampling.method は公式の一覧の名前にしてください: " + ", ".join(SAMPLERS))
        if "steps" in sampling and (type(sampling["steps"]) is not int or not 1 <= sampling["steps"] <= 100):
            raise ClientError("sampling.steps は1〜100の整数にしてください。")
        if "cfgScale" in sampling and (type(sampling["cfgScale"]) not in (int, float) or not math.isfinite(sampling["cfgScale"])
                                       or sampling["cfgScale"] <= 0):
            raise ClientError("sampling.cfgScale は正の数にしてください。")
        if kind == "dit":
            notes.append("sampling はSDXL・SD v1だけで有効（公式）。Tsubaki系では効かない可能性がある")
    # 公式の既定は enable（送信前にプロンプトを書き換える）。字コンテとの照合を保つため、このキットの既定は disable。
    body.setdefault("promptHelper", "disable")
    if body["promptHelper"] not in {"enable", "disable"}:
        raise ClientError("promptHelper は enable か disable にしてください。")
    body.setdefault("seed", secrets.randbelow(4294967296))
    check_seed(body["seed"])
    notes += lora_notes(root, body["modelVersionId"], [str(item.get("modelId")) for item in loras])
    if kind is None:
        notes.append(f"modelVersionId が {MODELS_FILE} の一覧にない。mode・sampling の可否は点検していない（scripts/pixai_models.py add で登録できる）")
    return notes


def file_reference(root: Path, value, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ClientError(f"{label} は作品内の画像の相対パスにしてください。")
    path = project_path(root, value)
    if not path.is_file() or image_kind(path.read_bytes()[:16]) is None:
        raise ClientError(f"{label} の画像がありません（PNG・JPEG・WebP）: {value}")
    return value


def local_files(root: Path, params: dict) -> list[tuple[str, str]]:
    """v1 parameters の中の作品内画像（キット独自の項目）を（場所、相対パス）で返す。"""
    found = []
    for key in LOCAL_FILE_KEYS:
        if key in params:
            found.append((key, file_reference(root, params[key], key)))
    for index, item in enumerate(params.get("controlNets") or []):
        if isinstance(item, dict) and "mediaFile" in item:
            found.append((f"controlNets[{index}].mediaFile", file_reference(root, item["mediaFile"], f"controlNets の{index + 1}件目")))
    adapter = params.get("ipAdapter")
    if isinstance(adapter, dict):
        for index, value in enumerate(adapter.get("referenceFiles") or []):
            found.append((f"ipAdapter.referenceFiles[{index}]", file_reference(root, value, f"ipAdapter の参照画像{index + 1}")))
    return found


def prepare_v1(root: Path, request: dict) -> tuple[list[str], list[str]]:
    params = request["parameters"]
    if not isinstance(params, dict):
        raise ClientError("parameters はオブジェクトにしてください。")
    used_local = {k for k in params if k in LOCAL_FILE_KEYS}
    unknown = set(params) - V1_DOCUMENTED - V1_UNVERIFIED - set(LOCAL_FILE_KEYS)
    if unknown:
        raise ClientError("v1 で扱わない項目があります: " + ", ".join(sorted(unknown)))
    for key, target in LOCAL_FILE_KEYS.items():
        if key in params and target in params:
            raise ClientError(f"{key} と {target} は同時に指定できません。")
    unverified = sorted((set(params) & V1_UNVERIFIED) | {LOCAL_FILE_KEYS[k] for k in used_local})
    notes = []
    check_id(params.get("modelId"), "modelId")
    if not isinstance(params.get("prompts"), str) or not params["prompts"].strip() or len(params["prompts"]) > 4096:
        raise ClientError("parameters.prompts へ4096字以内の生成プロンプトを設定してください。")
    for dimension in ("width", "height"):
        size = params.get(dimension)
        if type(size) is not int or not 512 <= size <= 1280:
            raise ClientError("v1 の width・height は512〜1280の整数で両方指定してください（公式）。")
    lora = params.get("lora", {})
    if not isinstance(lora, dict) or len(lora) > 3:
        raise ClientError("v1 の lora は最大3件のオブジェクト（{バージョンID: 重み}）にしてください（公式のmaxProperties）。")
    notes += lora_notes(root, params["modelId"], list(lora))
    kind = model_type(params["modelId"], request)
    if params.get("controlNets") and not supports(params["modelId"], kind, "controlnet"):
        # Tsubaki.2 は 403「This model cannot be used with ControlNets.」（2026-10-25）。他はモデルページの表示による。
        raise ClientError("このモデルは ControlNet を使えません（Tsubaki.2 は403で拒否、初代Tsubaki系・Hinata v2 はモデルページで非対応）。"
                          "SDXLのモデル（haruka2 等）を使ってください。")
    # 2026-10-25の確認（Haruka v2、元画像は普通の絵）：canny・depth は構図を写した。openpose は効かず、scribble は failed。
    for item in params.get("controlNets") or []:
        if isinstance(item, dict) and item.get("type") in ("openpose", "openpose_full", "dwpose"):
            notes.append("ControlNet の openpose は、普通の絵を渡しても効かなかった（骨格画像は未確認）。構図を写すなら canny・depth")
        elif isinstance(item, dict) and item.get("type") == "scribble":
            notes.append("ControlNet の scribble は、タスクが failed で終わった例がある（画像なし）。canny を使う")
    if any(k in params for k in ("maskMediaId", "maskMediaUrl", "maskMediaFile")) and not supports(params["modelId"], kind, "inpaint"):
        # Tsubaki.2 は 400「This feature is not yet supported for this model」（2026-10-25）。
        raise ClientError("このモデルはインペイントを使えません（Tsubaki.2 は400で拒否）。tsubaki3 か SDXLのモデルで描き直してください。")
    if params.get("latentCouple") and kind == "dit":
        notes.append("latentCouple は Tsubaki.2 で受理されたが効かなかった（2026-10-25）。SDXLのモデルで使う")
    for lora_id, weight in lora.items():
        check_id(lora_id, "lora のバージョンID")
        if type(weight) not in (int, float) or not math.isfinite(weight) or not 0 <= weight <= 1:
            raise ClientError("lora の重みは0〜1にしてください。")
    params.setdefault("batchSize", 1)
    if type(params["batchSize"]) is not int or not 1 <= params["batchSize"] <= 4:
        raise ClientError("v1 の batchSize は1〜4の整数にしてください。")
    if "inferenceProfile" in params:
        if params["inferenceProfile"] not in MODES:
            raise ClientError("inferenceProfile は " + "・".join(MODES) + " のいずれかにしてください。")
        kind = model_type(params["modelId"], request)
        if kind == "sdxl" or not supports(params["modelId"], kind, "mode"):
            raise ClientError("inferenceProfile（mode）は Tsubaki.2・Tsubaki.3 系だけで使えます。")
        check_mode(params["modelId"], params["inferenceProfile"], kind, notes)
    if "modelStyle" in params:
        style = params["modelStyle"]
        valid = isinstance(style, dict) and ((style.get("type") == "key" and set(style) == {"type", "keyId"} and isinstance(style["keyId"], str))
                                              or (style.get("type") == "custom" and set(style) == {"type", "custom"} and isinstance(style["custom"], str))
                                              or (style.get("type") == "styleKeyRef" and set(style) == {"type", "refId"} and isinstance(style["refId"], str)))
        if not valid:
            raise ClientError('modelStyle は {"type": "key", "keyId": …}・{"type": "custom", "custom": …}・{"type": "styleKeyRef", "refId": …} のいずれかにしてください。')
    if "upscale" in params and (type(params["upscale"]) not in (int, float) or not 1 <= params["upscale"] <= 2):
        raise ClientError("upscale は1〜2にしてください（1は無効。公式は長辺2048px以内に抑える）。")
    for flag in ("enableTile", "enableADetailer"):
        if flag in params and type(params[flag]) is not bool:
            raise ClientError(f"{flag} は true か false にしてください。")
    helper = params.setdefault("promptHelper", {"enable": False})
    if not isinstance(helper, dict) or set(helper) - {"enable"} or type(helper.get("enable", False)) is not bool:
        raise ClientError('promptHelper は {"enable": false} の形にしてください。')
    if "seed" in params:
        check_seed(params["seed"])
    if "strength" in params and (type(params["strength"]) not in (int, float) or not 0 < params["strength"] <= 1):
        raise ClientError("strength は0より大きく1以下にしてください。")
    for index, item in enumerate(params.get("controlNets") or []):
        if not isinstance(item, dict) or item.get("type") not in CONTROLNET_TYPES:
            raise ClientError(f"controlNets の{index + 1}件目の type は " + "・".join(CONTROLNET_TYPES) + " のいずれかにしてください。")
        if sum(k in item for k in ("mediaFile", "mediaId", "mediaUrl")) != 1:
            raise ClientError(f"controlNets の{index + 1}件目は mediaFile・mediaId・mediaUrl のどれか１つで画像を指定してください。")
    if "controlNets" in params and not isinstance(params["controlNets"], list):
        raise ClientError("controlNets は配列にしてください。")
    adapter = params.get("ipAdapter")
    if adapter is not None:
        if not isinstance(adapter, dict) or set(adapter) - {"enabled", "referenceImages", "referenceFiles"}:
            raise ClientError("ipAdapter は enabled・referenceImages（mediaId の配列）・referenceFiles（作品内の画像）だけにしてください。")
        if not (adapter.get("referenceImages") or adapter.get("referenceFiles")):
            raise ClientError("ipAdapter には参照画像を１枚以上指定してください。")
    local_files(root, params)
    if any(k in params for k in ("mediaId", "mediaUrl", "mediaFile")) and "strength" not in params:
        notes.append("i2iの strength が未指定。変化量はサーバーの既定になる")
    if params.get("enableTile") and not (params.get("upscale", 1) > 1 and any(k in params for k in ("mediaUrl", "mediaId", "mediaFile"))):
        notes.append("enableTile は元画像（mediaUrl）があり upscale > 1 のときだけ有効（公式）")
    return notes, unverified


def prepare_request(root: Path, relative: str) -> tuple[dict, list[str], list[str]]:
    return prepare_request_data(root, read_json(project_path(root, relative)))


def prepare_request_data(root: Path, request: dict) -> tuple[dict, list[str], list[str]]:
    """要求JSONを検証し、既定値を補う。戻り値は（要求、注意、未確認の項目）。送信用の本文は send_payload で作る。"""
    api = request.get("api")
    if api == "v2":
        if set(request) - {"api", "body", "model_type"} or "body" not in request:
            raise ClientError('v2 の要求は {"api": "v2", "body": {…}} の形にしてください（model_type は送信しない注記）。')
        return request, prepare_v2(root, request), []
    if api == "v1":
        if set(request) - {"api", "parameters", "model_type"} or "parameters" not in request:
            raise ClientError('v1 の要求は {"api": "v1", "parameters": {…}} の形にしてください。')
        notes, unverified = prepare_v1(root, request)
        return request, notes, unverified
    raise ClientError('要求JSONの api は "v2"（標準）か "v1"（i2i・参照画像・Hires等）にしてください。')


def endpoint_of(request: dict) -> str:
    return "/v2/image/create" if request["api"] == "v2" else "/v1/task"


def batch_size(request: dict) -> int:
    return (request["body"] if request["api"] == "v2" else request["parameters"]).get("batchSize", 1)


def summary(request: dict) -> str:
    if request["api"] == "v2":
        body = request["body"]
        width, height = output_size(body)
        model = next((m["label"] for m in MODELS.values() if m["id"] == body["modelVersionId"]), body["modelVersionId"])
        extra = [f"mode {body['mode']}" if "mode" in body else None,
                 f"style {body['style'].get('key', 'custom')}" if "style" in body else None,
                 f"LoRA {len(body.get('loras', []))}件" if body.get("loras") else None]
        return (f"v2 / {model} / {body['aspectRatio']} {body['size']}（{width}×{height}px） / {body['batchSize']}枚 / seed {body['seed']}"
                + "".join(" / " + e for e in extra if e))
    params = request["parameters"]
    model = next((m["label"] for m in MODELS.values() if m["id"] == params["modelId"]), params["modelId"])
    extra = [f"upscale {params['upscale']}" if params.get("upscale", 1) > 1 else None, "ADetailer" if params.get("enableADetailer") else None,
             "i2i" if any(k in params for k in ("mediaId", "mediaUrl", "mediaFile")) else None,
             f"ControlNet {len(params['controlNets'])}件" if params.get("controlNets") else None,
             "IP-Adapter" if params.get("ipAdapter") else None, f"LoRA {len(params.get('lora', {}))}件" if params.get("lora") else None]
    return (f"v1 / {model} / {params['width']}×{params['height']}px / {params['batchSize']}枚"
            + (f" / seed {params['seed']}" if "seed" in params else "") + "".join(" / " + e for e in extra if e))


# ---------------------------------------------------------------- アップロード（参照・i2i用の画像）

def read_uploads(root: Path) -> dict:
    path = root / UPLOADS
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def upload(root: Path, key: str, relative: str, reuse: bool = True) -> str:
    """作品内の画像を POST /v1/media/upload で送り、mediaId を返す。同じ内容（SHA-256）の画像は記録の mediaId を使い回す。"""
    path = project_path(root, relative)
    data = path.read_bytes()
    kind = image_kind(data[:16])
    if kind is None or kind[0] == "image/gif":
        raise ClientError(f"アップロードできる画像は PNG・JPEG・WebP です: {relative}")
    digest = hashlib.sha256(data).hexdigest()
    uploads = read_uploads(root)
    if reuse and isinstance(uploads.get(digest), dict) and re.fullmatch(r"[0-9]{1,30}", str(uploads[digest].get("mediaId", ""))):
        return uploads[digest]["mediaId"]
    result = api_json(key, "POST", "/v1/media/upload", payload=data, content_type=kind[0], timeout=180)
    media_id = str(result.get("id", ""))
    if not re.fullmatch(r"[0-9]{1,30}", media_id):
        raise ClientError("[API応答不正] アップロードの応答に mediaId がありません。")
    uploads[digest] = {"mediaId": media_id, "file": relative, "uploadedAt": now()}
    (root / UPLOADS).parent.mkdir(parents=True, exist_ok=True)
    write_record(root / UPLOADS, uploads)
    return media_id


def send_payload(root: Path, key: str | None, request: dict) -> tuple[dict, dict]:
    """送信する本文と、置き換えた作品内画像の対応（パス → mediaId）。key が None なら置き換えずに対応だけ返す。"""
    if request["api"] == "v2":
        return dict(request["body"]), {}
    params = json.loads(json.dumps(request["parameters"]))
    replaced = {}

    def media(relative: str) -> str:
        if relative not in replaced:
            replaced[relative] = upload(root, key, relative) if key else "（送信時にアップロード）"
        return replaced[relative]

    for local, target in LOCAL_FILE_KEYS.items():
        if local in params:
            params[target] = media(params.pop(local))
    for item in params.get("controlNets") or []:
        if "mediaFile" in item:
            item["mediaId"] = media(item.pop("mediaFile"))
    adapter = params.get("ipAdapter")
    if isinstance(adapter, dict):
        files = adapter.pop("referenceFiles", [])
        adapter["referenceImages"] = list(adapter.get("referenceImages") or []) + [media(f) for f in files]
        adapter.setdefault("enabled", True)
    return {"parameters": params}, replaced


# ---------------------------------------------------------------- 費用確認・生成

def check_cost(args, request: dict, unverified: list[str]) -> None:
    if not args.cost_note or not args.cost_note.strip():
        raise ClientError("実行には--cost-noteで今回の設定に対する費用確認の根拠（クレジット・会員プラン・許可の範囲）を指定してください。")
    if not args.confirm_credits:
        raise ClientError("費用未確認です。PixAIのクレジット消費をユーザーが明示許可した場合だけ --confirm-credits を付けてください。"
                          "残高・消費を照会するAPIは公式文書にないため、スクリプトは無料を判定できません。")
    if unverified and not args.allow_unverified:
        raise ClientError("現行の公式文書にない項目があります: " + ", ".join(unverified)
                          + "。公式クライアントの型にある項目で、効果・費用は未確認です。試す場合だけ --allow-unverified を付けてください。")


def candidate_paths(first: Path, count: int) -> list[Path]:
    match = re.fullmatch(r"(.*?)(\d+)", first.stem)
    if count == 1:
        return [first]
    if not match:
        return [first.with_name(f"{first.stem}-{i + 1}.png") for i in range(count)]
    prefix, number = match.group(1), match.group(2)
    return [first.with_name(f"{prefix}{int(number) + i:0{len(number)}d}.png") for i in range(count)]


def record_path_for(output: Path) -> Path:
    return output.with_name(output.stem + ".pixai.json")


def wait_task(key: str, task_id: str, timeout: float, log=print) -> dict:
    """GET /v1/task/{id} を間隔を広げながら照会する。読み取りの通信障害は３回まで照会し直す（生成の再送はしない）。"""
    deadline = time.monotonic() + timeout
    interval, failures, last = 3.0, 0, None
    while True:
        time.sleep(interval)
        try:
            task = api_json(key, "GET", f"/v1/task/{task_id}", timeout=30)
            failures = 0
        except ClientError:
            failures += 1
            if failures >= 3:
                raise
            task = None
        if task is not None:
            status = task.get("status")
            if status != last:
                log(f"  タスク {task_id}: {status}")
                last = status
            if status in TERMINAL:
                return task
        if time.monotonic() >= deadline:
            raise TimeoutError
        interval = min(interval * 1.3, 10.0)


def media_url(key: str, media_id: str) -> str | None:
    data = api_json(key, "GET", f"/v1/media/{media_id}", timeout=30)
    for item in data.get("urls") or []:
        if isinstance(item, dict) and item.get("variant") == "PUBLIC" and isinstance(item.get("url"), str):
            return item["url"]
    return None


def save_outputs(root: Path, key: str, task: dict, outputs: list[Path], record: dict) -> list[Path]:
    """完了したタスクの画像を順に保存する。保存できなかった枠は記録に残し、他の画像は保存する。"""
    found = task.get("outputs") or {}
    ids = found.get("mediaIds") or []
    urls = found.get("mediaUrls") or []
    saved, problems = [], []
    for index, output in enumerate(outputs):
        url = urls[index] if index < len(urls) and isinstance(urls[index], str) else None
        media_id = ids[index] if index < len(ids) and isinstance(ids[index], str) else None
        if output.exists():
            saved.append(output)
            continue
        try:
            if url is None and media_id:
                url = media_url(key, media_id)
            if url is None:
                raise ClientError("画像のURLがありません（mediaUrls が null）。")
            png, original = as_png(download(url))
            png_size(png)
            with output.open("xb") as stream:
                stream.write(png)
            record.setdefault("outputs", []).append({"path": output.relative_to(root).as_posix(), "mediaId": media_id,
                                                     "sha256": hashlib.sha256(png).hexdigest(), "originalType": original})
            saved.append(output)
        except ClientError as error:
            problems.append(f"{output.name}: {error}")
    record["missingOutputs"] = problems
    if len(ids) and len(ids) < len(outputs):
        record["missingOutputs"].append(f"タスクの画像は{len(ids)}枚（要求は{len(outputs)}枚）")
    return saved


def finish(root: Path, key: str, task: dict, outputs: list[Path], record: dict, record_path: Path) -> list[Path]:
    status = task.get("status")
    record["task"] = {k: task.get(k) for k in ("id", "status", "createdAt", "startedAt", "endAt", "mediaSafetyLevel", "textSafetyLevel")
                      if task.get(k) is not None}
    if status != "completed":
        record.update(status=f"タスク終了（{status}）・画像なし", finishedAt=now())
        write_record(record_path, record)
        output = outputs[0]
        folder = reject_to_failed(root, output, record_path, f"PixAIがタスクを {status} で終えた（画像なし）")
        raise ClientError(f"タスクが {status} で終わりました。画像はありません。記録は {folder.relative_to(root).as_posix()} へ移しました。"
                          "クレジットの消費はPixAI側で確認してください。")
    saved = save_outputs(root, key, task, outputs, record)
    if not saved:
        record.update(status="完了・画像の保存に失敗（taskIdで取得し直せる）", finishedAt=now())
        write_record(record_path, record)
        raise ClientError("タスクは完了しましたが画像を保存できませんでした: " + " / ".join(record["missingOutputs"])
                          + "。fetch で取得し直してください（画像は無期限には保存されません）。")
    record.update(status="PNG保存済み" if not record["missingOutputs"] else "一部のPNG保存済み", finishedAt=now())
    write_record(record_path, record)
    if record["missingOutputs"]:
        raise ClientError(f"{len(saved)}枚は保存しましたが、一部の画像を取得できませんでした。fetch で残りを取得してください（生成は再送しません）。")
    return saved


def execute_generation(root: Path, request: dict, output_relative: str, args, unverified: list[str] | None = None,
                       log=print) -> list[Path]:
    """費用確認の後に１回だけタスクを作り、完了を待って画像と実行記録を保存する。タスクの作成は再送しない。"""
    unverified = unverified or []
    check_cost(args, request, unverified)
    key, source = load_key(root)
    if key in json.dumps(request, ensure_ascii=False) or key in args.cost_note:
        raise ClientError("要求または費用メモへ認証情報を含めないでください。")
    output = project_path(root, output_relative)
    if not output.is_relative_to(root / "output") or output.suffix.lower() != ".png":
        raise ClientError("保存先はoutput/内のPNGにしてください。")
    outputs = candidate_paths(output, batch_size(request))
    record_path = record_path_for(output)
    body_path = output.with_name(output.stem + ".request-body.json")
    readable_path = output.with_name(output.stem + ".request.json")
    if any(p.exists() for p in [*outputs, record_path, body_path, readable_path]):
        raise ClientError("同名の画像または実行記録があります。再送せず、記録を確認してください。")
    output.parent.mkdir(parents=True, exist_ok=True)
    record = {"schemaVersion": 1, "status": "送信準備済み", "startedAt": now(), "api": request["api"],
              "endpoint": endpoint_of(request), "request": request, "credentialSource": source,
              "costMode": "credits_authorized", "costNote": args.cost_note, "unverifiedParameters": unverified,
              "reservedOutputs": [p.relative_to(root).as_posix() for p in outputs], "output": output.relative_to(root).as_posix(),
              "taskId": None, "actualCreditCost": None}
    with readable_path.open("x", encoding="utf-8") as stream:
        json.dump(request, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    # 同じ保存先への並行実行も送信前に止める。
    with record_path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    try:
        body, uploaded = send_payload(root, key, request)
    except (ClientError, OSError) as error:
        record.update(status="アップロード失敗（タスク未作成）", error=str(error)[:500], finishedAt=now())
        write_record(record_path, record)
        reject_to_failed(root, output, record_path, "参照・i2i用の画像をアップロードできなかった（タスクは作っていない）")
        raise
    if uploaded:
        record["uploadedFiles"] = uploaded
        log("  アップロード: " + ", ".join(f"{p} → {m}" for p, m in uploaded.items()))
    try:
        payload = json.dumps(body, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
        record["requestSha256"] = hashlib.sha256(payload).hexdigest()
        record["sentRequestFiles"] = {"body": body_path.relative_to(root).as_posix(), "readable": readable_path.relative_to(root).as_posix()}
        with body_path.open("xb") as stream:
            stream.write(payload)
        record["status"] = "送信中"
        write_record(record_path, record)
        task = api_json(key, "POST", endpoint_of(request), payload=payload, timeout=120)
    except RejectedError:
        record.update(status="作成拒否（タスク未作成）", finishedAt=now())
        write_record(record_path, record)
        reject_to_failed(root, output, record_path, "PixAIがタスクを作らずに拒否した（HTTP 4xx）")
        raise
    except (ClientError, OSError, ValueError, TypeError):
        record["status"] = "処理未完了・送信の結果が不明（再送前にPixAI側の生成とクレジットを確認）"
        try:
            write_record(record_path, record)
        except OSError:
            pass
        raise
    task_id = str(task.get("id", ""))
    if not re.fullmatch(r"[0-9]{1,30}", task_id):
        record["status"] = "処理未完了・応答にtaskIdがない（PixAI側の生成とクレジットを確認）"
        write_record(record_path, record)
        raise ClientError("[API応答不正] タスクの作成応答に id がありません。再送前にPixAI側を確認してください。")
    record.update(taskId=task_id, status="完了待ち", createdTask={k: task.get(k) for k in ("id", "status", "createdAt")})
    write_record(record_path, record)
    log(f"  タスク作成: {task_id}（完了を待っています。ポーリングは3秒から10秒間隔）")
    try:
        task = wait_task(key, task_id, getattr(args, "timeout", 900), log)
    except (TimeoutError, ClientError) as error:
        record["status"] = "完了待ちの途中で終了（taskIdで取得し直せる）"
        write_record(record_path, record)
        reason = "待ち時間の上限に達しました" if isinstance(error, TimeoutError) else str(error)
        raise ClientError(f"{reason}。タスク {task_id} は作成済みです。再送せず、fetch で取得し直してください。") from None
    return finish(root, key, task, outputs, record, record_path)


def reject_to_failed(root: Path, output: Path, record_path: Path, note: str) -> Path:
    """画像のない送信の記録を failed/ へ移し、候補の番号を空ける（削除しない）。"""
    folder = output.parent / "failed" / f"{datetime.now():%Y%m%d-%H%M%S}-{output.stem}-{secrets.token_hex(3)}"
    folder.mkdir(parents=True)
    for path in output.parent.glob(output.stem + ".*"):
        if path.is_file() and path.name != output.name:
            path.replace(folder / path.name)
    write_record(folder / "moved.json", {"action": "rejected", "files": sorted(p.name for p in folder.iterdir()),
                                         "moved_at": datetime.now().isoformat(timespec="seconds"), "note": note})
    return folder


def fetch(root: Path, record_relative: str, log=print) -> list[Path]:
    """実行記録の taskId でタスクを照会し、完了していれば未保存の画像を保存する。生成は再送しない。"""
    record_path = project_path(root, record_relative)
    if not record_path.name.endswith(".pixai.json") or not record_path.is_file():
        raise ClientError("取得し直すには候補フォルダの rNNN.pixai.json を指定してください。")
    record = read_json(record_path)
    task_id = str(record.get("taskId") or "")
    if not re.fullmatch(r"[0-9]{1,30}", task_id):
        raise ClientError("この記録には taskId がありません（作成の応答を受け取れていない）。PixAI側の生成とクレジットを確認し、"
                          "画像がなければ move-unknown で failed/ へ移してください。")
    outputs = [project_path(root, p) for p in record.get("reservedOutputs") or [record["output"]]]
    key, _ = load_key(root)
    task = api_json(key, "GET", f"/v1/task/{task_id}", timeout=30)
    log(f"  タスク {task_id}: {task.get('status')}")
    if task.get("status") not in TERMINAL:
        raise ClientError(f"タスクはまだ {task.get('status')} です。しばらく待ってから fetch してください。")
    record["refetchedAt"] = now()
    return finish(root, key, task, outputs, record, record_path)


def run(args, root: Path) -> None:
    if args.command in {"key-status", "status"}:
        key, source = load_key(root)
        print("キー読込済み（値は非表示）: " + source)
        if args.command == "status":
            print(auth_check(key))
            print("クレジットの残高・消費を照会するAPIは公式文書にありません。PixAIの画面で確認してください。")
        return
    if args.command == "fetch":
        for path in fetch(root, args.record):
            print("保存: " + path.relative_to(root).as_posix())
        return
    if args.command == "upload":
        if not args.execute:
            file_reference(root, args.file, "--file")
            print("送信なし。アップロードには --execute が必要です（画像をPixAIへ送ります）。")
            return
        key, _ = load_key(root)
        print("mediaId: " + upload(root, key, args.file, not args.no_reuse))
        return
    request, notes, unverified = prepare_request(root, args.request)
    print("要求: " + summary(request))
    for note in notes:
        print("  [注意] " + note)
    if unverified:
        print("  [未確認の項目] " + ", ".join(unverified) + "（送信には --allow-unverified）")
    if not args.execute:
        print("送信なし。実行には--executeと費用確認の指定が必要です。")
        return
    for path in execute_generation(root, request, args.output, args, unverified):
        print("保存: " + path.relative_to(root).as_posix())
    print("クレジットの実消費は未確認です。実行記録のactualCreditCostはnullのまま保持しました。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, epilog=KEY_SETUP_GUIDE, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("key-status", help="キーの読込元だけを確認する（通信なし）", epilog=KEY_SETUP_GUIDE,
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    commands.add_parser("status", help="接続・認証を確認する（画像生成なし）", epilog=KEY_SETUP_GUIDE,
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    generate = commands.add_parser("generate", help="１タスク生成。既定は送信しない要求確認")
    generate.add_argument("--request", required=True, help="作品内の生成要求JSON")
    generate.add_argument("--output", default="output/pixai/test-001.png")
    generate.add_argument("--execute", action="store_true", help="人が依頼した生成を１回送信する")
    generate.add_argument("--confirm-credits", action="store_true", help="今回の設定でのクレジット消費をユーザーが明示許可済み")
    generate.add_argument("--allow-unverified", action="store_true", help="現行の公式文書にない項目（i2i・参照画像等）を試すことをユーザーが了承済み")
    generate.add_argument("--cost-note", help="確認方法・日時・許可範囲。認証情報は書かない")
    generate.add_argument("--timeout", type=float, default=900, help="完了を待つ上限（秒）")
    again = commands.add_parser("fetch", help="実行記録の taskId で結果を取得し直す（生成は再送しない）")
    again.add_argument("--record", required=True, help="候補フォルダの rNNN.pixai.json")
    send = commands.add_parser("upload", help="作品内の画像をアップロードして mediaId を表示する")
    send.add_argument("--file", required=True)
    send.add_argument("--execute", action="store_true")
    send.add_argument("--no-reuse", action="store_true", help="同じ画像の記録があってもアップロードし直す")
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
