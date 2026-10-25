"""PixAIの要求JSONを、絵柄・背景・人物・LoRA・画風プリセットの引数から組み立てる。

組み立てた要求は input/pixai/requests/<ID>.json へ保存し、送信は pixai_batch.py の generate
（検証・費用確認・実行記録・再送しない扱い）にそのまま任せる。このスクリプト自体は通信しない。
保存した要求JSONは手で編集してよい。引数で組み立てずに、JSONを直接書いて generate しても同じ。

要求の形
  標準は v2（POST /v2/image/create）: {"api": "v2", "body": {modelVersionId, prompt, negativePrompt, aspectRatio, size,
    mode, style, loras, seed, batchSize, sampling, promptHelper}}
  次の機能を使うと v1（POST /v1/task）で組み立てる: {"api": "v1", "parameters": {prompts, modelId, width, height, lora, …}}
    公式文書にある機能   --upscale（Hires Fix）、--adetailer（顔の修正）
    公式クライアントの型だけにある機能（現行の公式文書では未確認。送信に --allow-unverified が必要）
                         --i2i 画像（--strength。--mask でインペイント）、--controlnet 種類:画像[:重み]、--reference 画像（IP-Adapter。キャラ・画風の参照）
  v1 では作品内の画像を mediaFile 等で書き、送信時にアップロードして mediaId へ置き換える。

モデル（--model。既定は .env.pixai の PIXAI_MODEL、なければ tsubaki2）
  名前は config/pixai-models.json の一覧（PixAIの公式モデル。--list-models で表示）。主なもの:
  tsubaki2  Tsubaki.2（DiT）。mode（lite・standard・pro・ultra）と画風プリセット（--style-preset）が使える
  tsubaki3  Tsubaki.3（DiT）。mode は pro で受理・standard は拒否を確認（既定 pro）。lite・ultra は未確認
  haruka2   Haruka v2（SDXL）。--sampler・--steps・--cfg-scale が使える
  hoshino2  Hoshino v2（SDXL）
  一覧にないモデルは scripts/pixai_models.py add でモデルページのURLから登録するか、
  --model-version-id とモデルの種類（--model-type dit|sdxl）で指定する。

プロンプトの順序（Danbooru系タグの慣例：人数 → 人物 → 構図 → 背景 → 絵柄 → 品質）
  プロンプト  人数タグ（人物から自動） → --layout → 人物（２人以上なら種類・見た目・ポーズ。１人なら見た目・ポーズ） → --scene → --background → --style → 品質タグ
  除外        PIXAI_NEGATIVE_PROMPT（既定の除外。未設定なら text, speech bubble, panel border, watermark） → --negative
PixAIには人物別の入力・配置ピンがない。複数人物の姿勢と位置関係（left・right・facing each other 等）は --layout に書くと外見より前に入る。
入力した文は書き換えず、そのまま連結する。品質タグは入力に同じタグがあれば付けない。
promptHelper（送信前のプロンプトの自動書き換え）は、字コンテとの照合を保つため既定で disable にする。

上書き（優先順は 引数 > 環境変数/.env.pixai > 既定。読む変数は下の5つだけで、APIキーの行は読まない）
  PIXAI_MODEL            config/pixai-models.json のモデル名（tsubaki2 等）またはバージョンID。引数 --model / --model-version-id
  PIXAI_QUALITY_TAGS     品質タグの全文（空で付けない）。既定は公式の例文にある masterpiece, best quality。引数 --quality-tags
  PIXAI_NEGATIVE_PROMPT  既定の除外の全文（空で付けない）。未設定なら DEFAULT_NEGATIVE。引数 --negative-base
  PIXAI_PROMPT_HELPER    enable か disable。引数 --prompt-helper
  PIXAI_CHECK_IDENTITY   1 にすると generate の識別特徴の点検（input/pixai/characters.json）を行う
絵柄・背景・人物の文は .env.pixai の PIXAI_STYLE_/PIXAI_BACKGROUND_/PIXAI_CHAR_ の値をそのまま渡す。
このスクリプトはそれらの変数を読まず、${変数名} も展開しない（--lora の ${PIXAI_LORA_…} だけはそのまま要求へ書く）。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pixai_api as api  # noqa: E402
import pixai_batch as batch  # noqa: E402

DEFAULT_MODEL = "tsubaki2"
# 文字・枠をPixAIに描かせない（pixai-composed-production.md の「セリフ・文字・吹き出しはPixAIへ渡さない」）。
DEFAULT_NEGATIVE = "text, speech bubble, panel border, watermark"
# 出典: 公式の最初のAPI呼び出しの例文（1girl, green hair, masterpiece, best quality, …）。効果の比較は未検証。
DEFAULT_QUALITY = "masterpiece, best quality"
CHAR_FIELDS = ("type", "appearance", "action")
CHAR_OPTION = re.compile(r"--char(\d{1,2})-(type|appearance|action)(?:=(.*))?", re.S)
TYPES = ("girl", "boy", "other")
LORA_ID = re.compile(r"[0-9]{6,30}|\$\{PIXAI_LORA_[A-Z0-9_]+\}")


class ComposeError(api.ClientError):
    pass


# ---------------------------------------------------------------- タグの照合（入力は書き換えず、重複の判定にだけ使う）

def tag_key(tag: str) -> str:
    """丸括弧の強調・重み・空白の違いを除いたタグの比較用の形。"""
    key = tag.strip().lower()
    key = re.sub(r"^\(+|\)+$", "", key)
    key = re.sub(r":\s*-?\d+(?:\.\d+)?$", "", key)
    return re.sub(r"[\s_]+", " ", key).strip()


def split_tags(text: str) -> list[str]:
    return [t.strip() for t in text.split(",") if t.strip()]


def join_text(*parts: str) -> str:
    """入力の文はそのまま（末尾の空白だけ除く）、空でないものを「, 」でつなぐ。"""
    return ", ".join(p.strip() for p in parts if p and p.strip())


def merge_quality(quality: str, given: list[str]) -> tuple[str, list[str], list[str]]:
    tokens = [t for text in given for t in split_tags(text)]
    keys = {tag_key(t) for t in tokens}
    added, skipped = [], []
    for tag in split_tags(quality):
        if tag_key(tag) in keys:
            skipped.append(tag)
        else:
            added.append(tag)
            keys.add(tag_key(tag))
    return ", ".join(added), added, skipped


# ---------------------------------------------------------------- 人物

def extract_character_options(argv: list[str]) -> tuple[list[str], dict[int, dict]]:
    """--charN-… を取り出す。残りの引数は通常のargparseへ渡す。"""
    rest, chars, i = [], {}, 0
    while i < len(argv):
        match = CHAR_OPTION.fullmatch(argv[i])
        if not match:
            rest.append(argv[i])
            i += 1
            continue
        number, field, inline = int(match.group(1)), match.group(2), match.group(3)
        if inline is None:
            if i + 1 >= len(argv):
                raise ComposeError(f"{argv[i]} の値がありません。")
            value, i = argv[i + 1], i + 2
        else:
            value, i = inline, i + 1
        if field in chars.setdefault(number, {}):
            raise ComposeError(f"--char{number}-{field} が重複しています。")
        chars[number][field] = value
    return rest, chars


def build_characters(raw: list[dict]) -> list[dict]:
    characters = []
    for index, item in enumerate(raw, 1):
        unknown = set(item) - set(CHAR_FIELDS)
        if unknown:
            raise ComposeError(f"人物{index}に未対応の項目: {', '.join(sorted(unknown))}（PixAIには人物別の配置ピン・除外がない）")
        kind = re.sub(r"^\d+(?=(girl|boy|other)$)", "", str(item.get("type", "girl")).strip().lower())
        if kind not in TYPES:
            raise ComposeError(f"人物{index}の type は {'・'.join(TYPES)} のいずれかにしてください。")
        for field in ("appearance", "action"):
            if "${" in str(item.get(field, "")):
                raise ComposeError(f"人物{index}の{field}に ${{…}} があります。このスクリプトは変数を展開しません。値を渡してください。")
        character = {"type": kind, "appearance": str(item.get("appearance", "")).strip(), "action": str(item.get("action", "")).strip()}
        if not character["appearance"]:
            raise ComposeError(f"人物{index}の見た目（--char{index}-appearance）を指定してください。")
        characters.append(character)
    return characters


def count_tags(characters: list[dict]) -> str:
    if not characters:
        return "no humans"
    parts = []
    for kind in TYPES:
        n = sum(c["type"] == kind for c in characters)
        if n:
            parts.append(f"{n}{kind}" + ("s" if n > 1 else ""))
    if len(characters) == 1:
        parts.append("solo")
    return ", ".join(parts)


# ---------------------------------------------------------------- 設定の解決

def resolve_model(root: Path, opts) -> tuple[str, str, str, str]:
    """（バージョンID、表示名、種類、出所）。"""
    if opts.model_version_id:
        if opts.model:
            raise ComposeError("--model と --model-version-id は同時に指定できません。")
        api.check_id(opts.model_version_id, "--model-version-id")
        kind = api.MODEL_TYPES.get(opts.model_version_id) or opts.model_type
        if kind is None:
            raise ComposeError("既知でないモデルは --model-type dit か sdxl も指定してください（mode・sampling の可否の判断に使う）。")
        return opts.model_version_id, opts.model_version_id, kind, "引数 --model-version-id"
    name, source = opts.model, "引数 --model"
    if not name:
        name, source = batch.read_setting(root, "PIXAI_MODEL"), "PIXAI_MODEL"
    if not name:
        name, source = DEFAULT_MODEL, "既定"
    name = name.strip()
    if name in api.MODELS:
        model = api.MODELS[name]
        return model["id"], model["label"], model["type"], source
    if re.fullmatch(r"[0-9]{6,30}", name):
        kind = api.MODEL_TYPES.get(name) or opts.model_type
        if kind is None:
            raise ComposeError(f"{source} のモデルIDは既知でないため、--model-type dit か sdxl も指定してください。")
        return name, name, kind, source
    raise ComposeError(f"モデルは {'・'.join(api.MODELS)} かバージョンIDにしてください（{source}）。"
                       "一覧にないモデルは scripts/pixai_models.py add で登録できます。")


def resolve_aspect(root: Path, opts) -> tuple[str, str]:
    if opts.aspect_ratio:
        if opts.aspect_ratio not in api.RESOLUTIONS:
            raise ComposeError("--aspect-ratio は " + "・".join(api.RESOLUTIONS) + " のいずれかにしてください。")
        return opts.aspect_ratio, "引数"
    aspect = api.layout_aspect(root)
    if aspect:
        return aspect, "config/page-layout.json の generationCanvas に最も近い比"
    return "2:3", "既定（generationCanvas は未設定）"


def resolve_text(root: Path, given: str | None, name: str, default: str) -> tuple[str, str]:
    if given is not None:
        return given, "引数"
    value = batch.read_setting(root, name)
    if value is not None:
        return value, name
    return default, "既定"


def parse_lora(value: str, index: int) -> dict:
    """ID[:重み[:トリガー語]]。IDは数字か ${PIXAI_LORA_…}。"""
    parts = value.split(":", 2)
    lora_id = parts[0].strip()
    if not LORA_ID.fullmatch(lora_id):
        raise ComposeError(f"--lora の{index}件目のIDは、LoRAのバージョンID（数字）か ${{PIXAI_LORA_…}} にしてください。")
    item = {"modelId": lora_id}
    if len(parts) > 1 and parts[1].strip():
        try:
            weight = float(parts[1])
        except ValueError:
            raise ComposeError(f"--lora の{index}件目の重みは0〜1の数にしてください。") from None
        if not 0 <= weight <= 1:
            raise ComposeError(f"--lora の{index}件目の重みは0〜1にしてください。")
        item["weight"] = weight
    if len(parts) > 2 and parts[2].strip():
        item["triggerWords"] = parts[2].strip()
    return item


def parse_controlnet(value: str, index: int) -> dict:
    parts = value.split(":", 2)
    if len(parts) < 2 or parts[0] not in api.CONTROLNET_TYPES:
        raise ComposeError(f"--controlnet の{index}件目は 種類:画像[:重み]（種類は {'・'.join(api.CONTROLNET_TYPES)}）にしてください。")
    item = {"type": parts[0], "mediaFile": parts[1]}
    if len(parts) > 2:
        try:
            item["weight"] = float(parts[2])
        except ValueError:
            raise ComposeError(f"--controlnet の{index}件目の重みは数にしてください。") from None
    return item


# ---------------------------------------------------------------- 要求の組み立て

def compose(root: Path, opts: argparse.Namespace, raw_chars: list[dict]) -> tuple[dict, dict]:
    characters = build_characters(raw_chars)
    for name in ("layout", "scene", "background", "style", "negative"):
        if "${" in (getattr(opts, name) or ""):
            raise ComposeError(f"--{name} に ${{…}} があります。このスクリプトは変数を展開しません。値を渡してください。")
    model_id, label, kind, model_source = resolve_model(root, opts)
    quality, quality_source = ("", "付けない（--no-quality-tags）") if opts.no_quality_tags else \
        resolve_text(root, opts.quality_tags, "PIXAI_QUALITY_TAGS", DEFAULT_QUALITY)
    negative_base, negative_source = resolve_text(root, opts.negative_base, "PIXAI_NEGATIVE_PROMPT", DEFAULT_NEGATIVE)
    helper, helper_source = resolve_text(root, opts.prompt_helper, "PIXAI_PROMPT_HELPER", "disable")
    helper = helper.strip().lower()
    if helper not in ("enable", "disable"):
        raise ComposeError("promptHelper は enable か disable にしてください。")
    counts = opts.count_tags if opts.count_tags is not None else count_tags(characters)
    # 人物別の入力がないため、２人以上のときだけ各人物の文の先頭に種類（girl・boy）を置き、誰の見た目かを示す。
    texts = [join_text(c["type"] if len(characters) > 1 else "", c["appearance"], c["action"]) for c in characters]
    given = [counts, opts.layout, *texts, opts.scene, opts.background, opts.style]
    quality_text, added, skipped = merge_quality(quality, given)
    loras = [parse_lora(v, i) for i, v in enumerate(opts.lora or [], 1)]
    notes = []
    v1 = bool(opts.upscale or opts.adetailer or opts.i2i or opts.mask or opts.controlnet or opts.reference or opts.api == "v1")
    # 複雑なコマ（２人以上・インペイント）と作り直し（候補があるID）は、１タスク4枚から選ぶのを基本にする。
    # Tsubaki.3 pro 1k で1枚4,000・4枚7,000クレジット（利用者がPixAIの利用履歴で確認、2026-10-25）。
    if opts.batch_size is not None:
        batch_size, batch_source = opts.batch_size, "引数"
    elif len(characters) >= 2 or opts.mask:
        batch_size, batch_source = 4, "既定（２人以上かインペイント）"
    elif opts.id and batch.candidates(root, opts.id):
        batch_size, batch_source = 4, "既定（作り直し）"
    else:
        batch_size, batch_source = 1, "既定"
    if v1 and any("triggerWords" in item for item in loras):
        # v1 の lora は {ID: 重み} だけで、トリガー語の項目がない。
        notes.append("v1 にはLoRAのトリガー語の項目がないため、トリガー語をプロンプトの人物の後ろへ足した")
    trigger = join_text(*[item.get("triggerWords", "") for item in loras]) if v1 else ""
    prompt = join_text(counts, opts.layout, *texts, trigger, opts.scene, opts.background, opts.style, quality_text)
    negative = join_text(negative_base, opts.negative)
    aspect, aspect_source = resolve_aspect(root, opts)
    seed = opts.seed if opts.seed is not None else secrets.randbelow(4294967296)
    if opts.style_preset and opts.style_custom:
        raise ComposeError("--style-preset と --style-custom は同時に指定できません。")
    if opts.style_preset and opts.style_preset not in api.STYLE_PRESETS:
        raise ComposeError("--style-preset は公式のプリセット名にしてください（--list-styles で一覧）。")
    if (opts.mode and not api.supports(model_id, kind, "mode")) or \
            ((opts.style_preset or opts.style_custom) and not api.supports(model_id, kind, "style")):
        raise ComposeError("mode・画風プリセットは Tsubaki.2・Tsubaki.3 系だけで使えます（他のモデルでは mode が拒否され、style は無視される）。")
    if kind == "dit" and (opts.sampler or opts.steps or opts.cfg_scale):
        notes.append("sampling（--sampler・--steps・--cfg-scale）はSDXL・SD v1だけで有効（公式）。Tsubaki系では効かない可能性がある")
    sampling = {k: v for k, v in (("method", opts.sampler), ("steps", opts.steps), ("cfgScale", opts.cfg_scale)) if v is not None}
    if not v1:
        if len(loras) > 5:
            raise ComposeError("v2 のLoRAは最大5件です（公式）。")
        body = {"modelVersionId": model_id, "prompt": prompt, "aspectRatio": aspect, "size": opts.size,
                "seed": seed, "batchSize": batch_size, "promptHelper": helper}
        if negative_source == "既定" and not opts.negative and not api.supports(model_id, kind, "negativePrompt"):
            notes.append("このモデルは除外に非対応とモデルページに表示されているため、既定の除外を付けない")
        elif negative:
            body["negativePrompt"] = negative
        mode = opts.mode or (api.default_mode(model_id) if api.supports(model_id, kind, "mode") else None)
        if mode:
            body["mode"] = mode
        if opts.style_preset:
            body["style"] = {"type": "preset", "key": opts.style_preset}
        elif opts.style_custom:
            body["style"] = {"type": "custom", "custom": opts.style_custom}
        if loras:
            body["loras"] = loras
        if sampling:
            body["sampling"] = sampling
        request = {"api": "v2", "body": body}
    else:
        if len(loras) > 3:
            raise ComposeError("v1 のLoRAは最大3件です（公式のmaxProperties）。")
        if opts.size != "1k":
            raise ComposeError("v1 は width・height（512〜1280）で寸法を決めるため、--size 1.5k は使えません。")
        width, height = api.RESOLUTIONS[aspect][0]
        if opts.i2i:
            # i2i・インペイントは元画像と同じ寸法で描き直す（マスクも同じ寸法）。
            from PIL import Image
            with Image.open(api.project_path(root, opts.i2i)) as source:
                width, height = source.size
            if opts.mask:
                with Image.open(api.project_path(root, opts.mask)) as mask:
                    if mask.size != (width, height):
                        raise ComposeError(f"マスクの寸法 {mask.size[0]}×{mask.size[1]} が元画像 {width}×{height} と違います。")
            if not (512 <= width <= 1280 and 512 <= height <= 1280):
                raise ComposeError(f"元画像の寸法 {width}×{height} が v1 の範囲（512〜1280px）の外です。")
        if max(width, height) > 1280:
            raise ComposeError(f"縦横比 {aspect} は v1 の上限（1280px）を超えます。別の縦横比を選んでください。")
        params = {"prompts": prompt, "modelId": model_id, "width": width, "height": height, "batchSize": batch_size,
                  "promptHelper": {"enable": helper == "enable"}}
        if opts.seed is not None:
            params["seed"] = seed  # v1 の seed は現行の公式文書にない（公式クライアントの型にはある）
        if negative_source == "既定" and not opts.negative:
            # 未確認の項目なので、キットの既定の除外だけでは v1 に付けない。
            notes.append("v1 では既定の除外を付けない（negativePrompts は現行の公式文書にない項目）。使うなら --negative-base を指定する")
        elif negative:
            params["negativePrompts"] = negative
            notes.append("v1 の negativePrompts は現行の公式文書にない項目（送信に --allow-unverified が必要）")
        mode = opts.mode or (api.default_mode(model_id) if api.supports(model_id, kind, "mode") else None)
        if mode:
            params["inferenceProfile"] = mode
        if opts.style_preset:
            params["modelStyle"] = {"type": "key", "keyId": opts.style_preset}
        elif opts.style_custom:
            params["modelStyle"] = {"type": "custom", "custom": opts.style_custom}
        if loras:
            params["lora"] = {item["modelId"]: item.get("weight", 1.0) for item in loras}
        if sampling:
            params.update({"samplingMethod": sampling["method"]} if "method" in sampling else {})
            params.update({"samplingSteps": sampling["steps"]} if "steps" in sampling else {})
            params.update({"cfgScale": sampling["cfgScale"]} if "cfgScale" in sampling else {})
        if opts.upscale:
            params["upscale"] = opts.upscale
        if opts.adetailer:
            params["enableADetailer"] = True
        if opts.i2i:
            params["mediaFile"] = opts.i2i
            if opts.strength is not None:
                params["strength"] = opts.strength
            if opts.mask:
                # 白＝描き直す、黒＝元のまま（2026-10-25、作品と配布テストで確認）。マスクは元画像と同じ寸法にする。
                params["maskMediaFile"] = opts.mask
        elif opts.strength is not None or opts.mask:
            raise ComposeError("--strength・--mask は --i2i と一緒に指定してください。")
        if opts.controlnet:
            params["controlNets"] = [parse_controlnet(v, i) for i, v in enumerate(opts.controlnet, 1)]
        if opts.reference:
            params["ipAdapter"] = {"enabled": True, "referenceFiles": list(opts.reference)}
        request = {"api": "v1", "parameters": params}
    if kind and not api.MODEL_TYPES.get(model_id):
        request["model_type"] = kind
    info = {"batch_source": batch_source, "label": label, "kind": kind, "model_source": model_source, "quality_source": quality_source, "quality_added": added,
            "quality_skipped": skipped, "negative_source": negative_source, "helper_source": helper_source, "aspect_source": aspect_source,
            "notes": notes, "characters": texts}
    return request, info


def parse_args(argv: list[str]):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    parser.add_argument("--id", help="要求ID。p01-03 の形式（input/pixai/requests/<ID>.json）")
    parser.add_argument("--list-styles", action="store_true", help="画風プリセット（Tsubaki系）の一覧を表示して終わる")
    parser.add_argument("--list-models", action="store_true", help="config/pixai-models.json のモデルの一覧を表示して終わる")
    parser.add_argument("--api", choices=("v2", "v1"), help="既定は v2。v1 専用の機能を指定すると v1")
    parser.add_argument("--model", help="config/pixai-models.json の名前（tsubaki2・tsubaki3・haruka2 等）またはバージョンID（既定は PIXAI_MODEL、なければ tsubaki2）")
    parser.add_argument("--model-version-id", help="既知でないモデルのバージョンID（https://pixai.art/model/<id>/<バージョンID>）")
    parser.add_argument("--model-type", choices=("dit", "sdxl"), help="既知でないモデルの種類")
    parser.add_argument("--style", default="", help="絵柄（画風）の文。PIXAI_STYLE_… の値")
    parser.add_argument("--background", default="", help="背景・場所・時間・光。PIXAI_BACKGROUND_… の値")
    parser.add_argument("--layout", default="", help="複数人物の姿勢と位置関係。人数タグの直後、外見より前に入る"
                        "（girl on the right, boy on the left, facing each other など）")
    parser.add_argument("--scene", default="", help="構図・画角・全体の状況・人物の位置関係（upper body, from below, side by side など）")
    parser.add_argument("--count-tags", help="人数タグを手で指定する（既定は人物から自動。１人なら solo も付く。人物なしは no humans）")
    parser.add_argument("--negative", default="", help="追加の除外語（既定の除外の後ろに付く）")
    parser.add_argument("--negative-base", help="既定の除外の全文（PIXAI_NEGATIVE_PROMPT を上書き。空文字で付けない）。"
                        "どちらもなければ " + DEFAULT_NEGATIVE)
    quality = parser.add_mutually_exclusive_group()
    quality.add_argument("--quality-tags", help="品質タグを上書きする（空文字で付けない）")
    quality.add_argument("--no-quality-tags", action="store_true", help="品質タグを付けない")
    parser.add_argument("--style-preset", help="画風プリセット（Tsubaki系のみ。--list-styles で一覧）")
    parser.add_argument("--style-custom", help="画風の文をプロンプトの前に差し込む（Tsubaki系のみ。上級者向け）")
    parser.add_argument("--mode", choices=api.MODES, help="Tsubaki.2・Tsubaki.3 系の推論の段階（既定はモデルの一覧の default_mode。Tsubaki.2 は standard、Tsubaki.3 は pro）")
    parser.add_argument("--lora", action="append", help="LoRA。ID[:重み[:トリガー語]]（IDは数字か ${PIXAI_LORA_…}）。v2は最大5件、v1は最大3件")
    parser.add_argument("--aspect-ratio", help="縦横比（" + "・".join(api.RESOLUTIONS) + "）。既定は generationCanvas に最も近い比")
    parser.add_argument("--size", choices=api.SIZES, default="1k", help="解像度の段階（v2のみ。1.5kは長辺1536px）")
    parser.add_argument("--batch-size", type=int, choices=(1, 4),
                        help="１タスクの枚数（公式の値は1か4）。既定は、２人以上・インペイント・作り直し（候補があるID）なら4、それ以外は1")
    parser.add_argument("--sampler", choices=api.SAMPLERS, help="SDXLのサンプラー")
    parser.add_argument("--steps", type=int, help="SDXLのsteps（1〜100）")
    parser.add_argument("--cfg-scale", type=float, help="SDXLのCFG")
    parser.add_argument("--seed", type=int, help="省略時は乱数（v1 は省略時に seed を送らない）")
    parser.add_argument("--prompt-helper", choices=("enable", "disable"), help="送信前のプロンプトの自動書き換え（既定 disable）")
    parser.add_argument("--upscale", type=float, help="v1: Hires Fix の倍率（1より大きく2以下）")
    parser.add_argument("--adetailer", action="store_true", help="v1: 生成後の顔の修正（ADetailer）")
    parser.add_argument("--i2i", help="v1・未確認: 元にする作品内の画像（i2i）")
    parser.add_argument("--strength", type=float, help="v1・未確認: i2iの変化量（0より大きく1以下）")
    parser.add_argument("--mask", help="v1: インペイントのマスク（作品内の画像。元画像と同じ寸法、白＝描き直す。--i2i と一緒に使う）")
    parser.add_argument("--controlnet", action="append", help="v1・未確認: 種類:作品内の画像[:重み]（openpose・canny・depth 等）")
    parser.add_argument("--reference", action="append", help="v1・未確認: IP-Adapterの参照画像（作品内の画像。キャラクター・画風の参照）")
    parser.add_argument("--chars-json", help="人物の配列JSON（作品内の相対パス）。--charN-… とは併用しない")
    parser.add_argument("--cast-from", help="登場人物の登録（characters.json の cast）を既存の要求IDから写す（識別特徴の点検を使う場合）")
    parser.add_argument("--force", action="store_true", help="同名の要求JSONを上書きする")
    parser.add_argument("--dry-run", action="store_true", help="保存せず、組み立てた内容だけ表示する")
    parser.add_argument("--no-check", action="store_true", help="保存後の送信なし確認（警告点検）を省く")
    parser.add_argument("--execute", action="store_true", help="確認後に pixai_batch.py generate で送信する")
    parser.add_argument("--accept-warnings", action="store_true")
    parser.add_argument("--confirm-credits", action="store_true")
    parser.add_argument("--allow-unverified", action="store_true")
    parser.add_argument("--cost-note")
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parents[1]
    try:
        argv, numbered = extract_character_options(argv)
        opts = parse_args(argv).parse_args(argv)
        if opts.list_styles:
            for key, label in sorted(api.STYLE_PRESETS.items()):
                print(f"{key}: {label}")
            return 0
        if opts.list_models:
            for name, model in api.MODELS.items():
                print(f"{name}: {model['label']}（{model['type'].upper()}、modelVersionId {model['id']}）"
                      f" {model.get('strengths_ja', '')} / API: {model.get('api', '未記入')}")
            return 0
        if not (root / "project.json").is_file():
            raise ComposeError("作品プロジェクトの scripts/ から実行してください。")
        if not opts.id or not batch.REQUEST_ID.fullmatch(opts.id):
            raise ComposeError("--id に要求IDを英数字・-・_ で指定してください（例 p01-03）。")
        if opts.chars_json:
            if numbered:
                raise ComposeError("--chars-json と --charN-… は併用できません。")
            data = json.loads(api.project_path(root, opts.chars_json).read_text(encoding="utf-8-sig"))
            if not isinstance(data, list) or not all(isinstance(c, dict) for c in data):
                raise ComposeError("--chars-json は人物オブジェクトの配列にしてください。")
            raw = data
        else:
            if sorted(numbered) != list(range(1, len(numbered) + 1)):
                raise ComposeError("人物の番号は1から連続させてください（--char1-…, --char2-…）。")
            raw = [numbered[n] for n in sorted(numbered)]
        request, info = compose(root, opts, raw)
        path = root / batch.REQUESTS_DIR / f"{opts.id}.json"
        print(f"モデル: {info['label']}（{info['kind'].upper()}。出所={info['model_source']}） / 要求の形: {request['api']}")
        print(f"品質タグ: 出所={info['quality_source']} / 追加={', '.join(info['quality_added']) or 'なし'}"
              f" / 入力と重複のため不追加={', '.join(info['quality_skipped']) or 'なし'}")
        print(f"既定の除外: 出所={info['negative_source']} / promptHelper: 出所={info['helper_source']} / 縦横比の出所: {info['aspect_source']}")
        print(f"１タスクの枚数: 出所={info['batch_source']}（4枚は1枚の約1.75倍のクレジット。1枚にするなら --batch-size 1）")
        if request["api"] == "v2":
            body = request["body"]
            print("プロンプト: " + body["prompt"])
            print("除外: " + body.get("negativePrompt", "（なし。サーバーの既定）"))
            width, height = api.RESOLUTIONS[body["aspectRatio"]][api.SIZES.index(body["size"])]
            print(f"設定: {body['aspectRatio']} {body['size']}（{width}×{height}px） / {body['batchSize']}枚 / seed {body['seed']}"
                  + (f" / mode {body['mode']}" if "mode" in body else "") + (f" / style {json.dumps(body['style'], ensure_ascii=False)}" if "style" in body else "")
                  + (f" / LoRA {json.dumps(body['loras'], ensure_ascii=False)}" if "loras" in body else ""))
        else:
            params = request["parameters"]
            print("プロンプト: " + params["prompts"])
            print("除外: " + params.get("negativePrompts", "（なし。サーバーの既定）"))
            shown = {k: v for k, v in params.items() if k not in ("prompts", "negativePrompts")}
            print("設定: " + json.dumps(shown, ensure_ascii=False))
        for note in info["notes"]:
            print(f"  [注意] {note}")
        if opts.dry_run:
            print("保存なし（--dry-run）。")
            return 0
        if path.exists() and not opts.force:
            raise ComposeError(f"{batch.rel(root, path)} があります。上書きは --force、別IDにするなら --id を変えてください。")
        batch.write_json(path, request)
        print("保存: " + batch.rel(root, path) + "（手で編集してよい）")
        if opts.cast_from:
            cast_path = root / batch.CHARACTERS
            data = api.read_json(cast_path)
            if opts.cast_from not in data.get("cast", {}):
                raise ComposeError(f"{batch.CHARACTERS} の cast に {opts.cast_from} がありません。")
            data["cast"][opts.id] = dict(data["cast"][opts.cast_from])
            batch.write_json(cast_path, data)
            print(f"登場人物の登録を {opts.cast_from} から写しました。")
        if opts.no_check and not opts.execute:
            return 0
        forward = ["generate", "--ids", opts.id, "--seed", "request"]
        if opts.execute:
            forward.append("--execute")
            for flag in ("accept_warnings", "confirm_credits", "allow_unverified"):
                if getattr(opts, flag):
                    forward.append("--" + flag.replace("_", "-"))
            if opts.cost_note:
                forward += ["--cost-note", opts.cost_note]
        return batch.main(forward)
    except api.ClientError as error:
        print("エラー: " + str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"エラー: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
