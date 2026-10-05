"""NovelAI（V5・V4.5）の要求JSONを、絵柄・背景・人物別の引数から組み立てる。

組み立てた要求は input/novelai/requests/<ID>.json へ保存し、送信は novelai_batch.py の generate
（検証・費用確認・実行記録・再送しない扱い）にそのまま任せる。このスクリプト自体は通信しない。
保存した要求JSONは手で編集してよい。引数で組み立てずに、JSONを直接書いて generate しても同じ。

NovelAI APIで生成する要求の標準の組み立て手段。モデルはV5（既定は nai-diffusion-5-curated）、V4.5はユーザーが指定した場合だけ使う。
i2i・参照などの追加機能が必要な場合は、このスクリプトを元に改造して使う（要求JSONの形式を保ち、送信は
novelai_batch.py generate / novelai_api.py generate を通す。追加機能の仕様・費用は docs/knowledge/novelai-api.md で先に確認する）。

プロンプトの順序（公式: 人数 → 人物 → その他、品質タグは末尾）
  ベース  人数タグ（人物から自動） → --scene → --background → --style → 品質タグ（自動）
  人物    人物の種類（girl/boy/other。数字なし） → 見た目 → ポーズ・行動
  除外    Undesired Contentプリセット（自動） → --negative
入力した文は書き換えず、そのまま連結する（空白・読点も保つ）。

モデルごとの画面の既定（品質タグ・除外プリセット・Guidance・送るパラメーター）は MODELS にある。
品質タグは入力に同じタグがあれば付けず、１個だけにする（--allow-duplicate-quality で画面と同じ重複を残す）。

上書き（優先順は 引数 > 環境変数/.env/.secrets > 既定。読む変数は下の4つだけで、APIキーの行は読まない）
  NOVELAI_QUALITY_TAGS      品質タグの全文（空で付けない）。引数 --quality-tags
  NOVELAI_UC_PRESET         除外プリセット名（heavy・light・human・none）。引数 --uc-preset
  NOVELAI_UC_PRESET_TEXT    除外プリセットの全文（空で付けない）。引数 --uc-preset-text
  NOVELAI_CHECK_IDENTITY    1 にすると generate の識別特徴の点検（characters.json）を行う。既定は行わない

人物は --char1-appearance のように番号で指定する（モデルの上限まで）:
  --charN-type girl|boy|other   --charN-appearance 見た目   --charN-action ポーズ・行動
  --charN-pos x,y（0〜1。配置ピン。既定は全員に指定した場合だけ有効。--coords on/off で切替）   --charN-negative 人物別の除外
配列で渡す場合は --chars-json（上の項目名を持つオブジェクトの配列）。
絵柄・背景・人物の文は .env の NOVELAI_STYLE_/NOVELAI_BACKGROUND_/NOVELAI_CHAR_ の値をそのまま渡す。
このスクリプトはそれらの .env を読まず、${変数名} も展開しない。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import novelai_api as api  # noqa: E402
import novelai_batch as batch  # noqa: E402

DEFAULT_MODEL = "nai-diffusion-5-curated"
# 出典: docs.novelai.net/en/image/undesiredcontent/ と、画面PNGのuc（V5 Curated: 2026-10-05、V4.5 Curated: 同日）。
V5_UC = {
    "heavy": "lowres, artistic error, film grain, scan artifacts, worst quality, bad quality, jpeg artifacts, "
             "very displeasing, chromatic aberration, dithering, halftone, screentone, multiple views, logo, "
             "too many watermarks, negative space, blank page",
    "light": "lowres, bad hands, bad anatomy, artistic error, sepia, white haze, worst quality, very displeasing, "
             "jpeg artifacts, 0::ai-generated::",
    "human": "lowres, artistic error, film grain, scan artifacts, worst quality, bad quality, jpeg artifacts, "
             "very displeasing, chromatic aberration, dithering, halftone, screentone, multiple views, logo, "
             "too many watermarks, negative space, blank page, @_@, mismatched pupils, glowing eyes, bad anatomy",
    "none": "",
}
# V5 Fullの画面PNGでは、Heavyの先頭に nsfw, が付いていたが、ユーザー指示（2026-10-05）でスクリプトは nsfw を足さない。
# 画面と完全に同じにしたい場合は --uc-preset-text に nsfw を含む全文を渡す。light・humanは未確認。
V5_FULL_UC = {"heavy": V5_UC["heavy"], "none": ""}
# 公式文書はV4.5のHeavyをV5と同じとするが、V4.5画面のPNGは下の文だった。画面を正とし、light・humanは確認できていないため置かない。
V45_UC = {
    "heavy": "blurry, lowres, upscaled, artistic error, film grain, scan artifacts, worst quality, bad quality, "
             "jpeg artifacts, very displeasing, chromatic aberration, halftone, multiple views, logo, "
             "too many watermarks, negative space, blank page",
    "none": "",
}
# 画面PNGに記録されていた共通のパラメーター。省略するとAPIの既定が画面と違う値になる（deliberate_euler_ancestral_bug / prefer_brownian）。
COMMON_PARAMETERS = {
    "cfg_rescale": 0.0, "legacy_v3_extend": False, "controlnet_strength": 1.0, "dynamic_thresholding": False,
    "sm": False, "sm_dyn": False, "deliberate_euler_ancestral_bug": False, "prefer_brownian": True,
    "n_samples": 1, "image_format": "png",
}
MODELS = {
    "nai-diffusion-5-curated": {
        "label": "V5 Curated", "steps": 23, "quality": "very aesthetic, masterpiece, no text", "uc": V5_UC, "scale": 7.0,
        "max_characters": 22, "grid": None, "extra": {"straight_alpha": True},
        "status": "画面PNGと同Seed・同入力で、このスクリプトの要求が画素まで完全一致（2026-10-05、--coords off で2人目の座標を画面に合わせた場合）"},
    "nai-diffusion-5-full": {
        "label": "V5 Full", "steps": 23, "quality": "very aesthetic, masterpiece, no text", "uc": V5_FULL_UC, "scale": 7.0,
        "max_characters": 22, "grid": None, "extra": {"straight_alpha": True},
        "status": "画面PNG（Source V5 0ADF9AB7）と同Seed・同入力で画素まで完全一致（2026-10-05、画面の除外にある先頭の nsfw を含めた場合。スクリプトの既定は nsfw なし）"},
    "nai-diffusion-4-5-curated": {
        "label": "V4.5 Curated", "steps": 28, "quality": "very aesthetic, masterpiece, no text, -0.8::feet::, rating:general",
        "uc": V45_UC, "scale": 5.0, "max_characters": 6, "grid": 5, "extra": {},
        "status": "画面PNG（Source V4.5 C02D4F98）と同Seed・同入力で、このスクリプトの要求が画素まで完全一致（2026-10-05）"},
}
CHAR_FIELDS = ("type", "appearance", "action", "pos", "negative")
CHAR_OPTION = re.compile(r"--char(\d{1,2})-(type|appearance|action|pos|negative)(?:=(.*))?", re.S)
TYPES = ("girl", "boy", "other")
WEIGHTED = re.compile(r"^\s*-?\d+(?:\.\d+)?::")


class ComposeError(api.ClientError):
    pass


# ---------------------------------------------------------------- タグの照合（入力は書き換えず、重複の判定にだけ使う）

def tag_key(tag: str) -> str:
    """重み・括弧・空白の違いを除いたタグの比較用の形。"""
    key = tag.strip().lower()
    key = re.sub(r"^[\s{}\[\]]+|[\s{}\[\]]+$", "", key)
    key = re.sub(r"^-?\d+(?:\.\d+)?::", "", key)
    key = re.sub(r"::$", "", key)
    return re.sub(r"[\s_]+", " ", key).strip()


def canon(tag: str) -> str:
    return re.sub(r"\s+", " ", tag.strip().lower())


def split_tags(text: str) -> list[str]:
    return [t.strip() for t in text.split(",") if t.strip()]


def join_text(*parts: str) -> str:
    """入力の文はそのまま（末尾の空白だけ除く）、空でないものを「, 」でつなぐ。"""
    return ", ".join(p.strip() for p in parts if p and p.strip())


def merge_quality(quality: str, given: list[str], allow_duplicate: bool) -> tuple[str, list[str], list[str]]:
    """入力に同じタグがあれば付けない。付けるタグ・付けなかったタグを返す。重み付きの語（-0.8::feet::）は重みごとの一致だけを重複とする。"""
    tokens = [t for text in given for t in split_tags(text)]
    keys, canons = {tag_key(t) for t in tokens}, {canon(t) for t in tokens}
    added, skipped = [], []
    for tag in split_tags(quality):
        present = canon(tag) in canons if WEIGHTED.match(tag) else tag_key(tag) in keys
        if present and not allow_duplicate:
            skipped.append(tag)
        else:
            added.append(tag)
            if not WEIGHTED.match(tag):
                keys.add(tag_key(tag))
            canons.add(canon(tag))  # 上書き指定の中の重複も１個にする
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


def parse_pos(value, label: str) -> tuple[float, float]:
    try:
        x, y = ([float(v) for v in re.split(r"[,\s]+", value.strip())] if isinstance(value, str) else [float(v) for v in value])
    except (ValueError, TypeError):
        raise ComposeError(f"{label} は x,y の形（例 0.3,0.5）で指定してください。") from None
    if not (0 <= x <= 1 and 0 <= y <= 1):
        raise ComposeError(f"{label} の x・y は0〜1にしてください（左上が原点）。")
    return round(x, 4), round(y, 4)


def snap(value: float, grid: int) -> float:
    """V4.5の自由配置は5×5のマス。マスの中心へ寄せる。"""
    return (min(int(value * grid), grid - 1) + 0.5) / grid


def build_characters(raw: list[dict], profile: dict) -> tuple[list[dict], list[str]]:
    notes = []
    if len(raw) > profile["max_characters"]:
        raise ComposeError(f"{profile['label']}の人物は最大{profile['max_characters']}人です。")
    characters = []
    for index, item in enumerate(raw, 1):
        unknown = set(item) - set(CHAR_FIELDS)
        if unknown:
            raise ComposeError(f"人物{index}に未対応の項目: {', '.join(sorted(unknown))}")
        kind = str(item.get("type", "girl")).strip().lower()
        kind = re.sub(r"^1(?=(girl|boy|other)$)", "", kind)  # 人物別には数字を付けない（公式）
        if kind not in TYPES:
            raise ComposeError(f"人物{index}の type は {'・'.join(TYPES)} のいずれかにしてください。")
        for field in ("appearance", "action", "negative"):
            if "${" in str(item.get(field, "")):
                raise ComposeError(f"人物{index}の{field}に ${{…}} があります。このスクリプトは変数を展開しません。値を渡してください。")
        pos = item.get("pos")
        pos = parse_pos(pos, f"人物{index}の pos") if pos not in (None, "") else None
        if pos is not None and profile["grid"]:
            snapped = (snap(pos[0], profile["grid"]), snap(pos[1], profile["grid"]))
            if snapped != pos:
                notes.append(f"人物{index}の配置を{profile['label']}の{profile['grid']}×{profile['grid']}マスの中心 {snapped} へ寄せた")
            pos = snapped
        characters.append({"type": kind, "appearance": str(item.get("appearance", "")).strip(),
                           "action": str(item.get("action", "")).strip(), "negative": str(item.get("negative", "")).strip(), "pos": pos})
        if not characters[-1]["appearance"]:
            raise ComposeError(f"人物{index}の見た目（--char{index}-appearance）を指定してください。")
    return characters, notes


def count_tags(characters: list[dict]) -> str:
    if not characters:
        return "no humans"
    parts = []
    for kind in TYPES:
        n = sum(c["type"] == kind for c in characters)
        if n:
            parts.append(f"{n}{kind}" + ("s" if n > 1 else ""))
    return ", ".join(parts)


def order_notes(characters: list[dict], grid: int | None) -> list[str]:
    """公式の既定順（上から下・左から右）と、人物の並びが合っているかの注意。"""
    if not characters or any(c["pos"] is None for c in characters):
        return []
    cells = [(min(int(c["pos"][1] * 5), 4), min(int(c["pos"][0] * 5), 4)) for c in characters]
    if cells != sorted(cells):
        return ["人物の並びが配置ピンの順（上から下・左から右）と違う。公式は入力順と位置を矛盾させないよう勧めている"]
    return []


# ---------------------------------------------------------------- 設定の解決

def resolve_uc(root: Path, opts, profile: dict) -> tuple[str, str]:
    """除外プリセットの本文と出所。引数の全文 > 引数の名前 > 環境変数の全文 > 環境変数の名前 > heavy。"""
    def named(name: str, source: str):
        if name not in profile["uc"]:
            raise ComposeError(f"{profile['label']}の除外プリセットは {'・'.join(profile['uc'])} だけです（{source}）。"
                               "他の文は --uc-preset-text で全文を指定してください。")
        return profile["uc"][name], f"{source}={name}"
    if opts.uc_preset_text is not None:
        return opts.uc_preset_text, "引数 --uc-preset-text"
    if opts.uc_preset:
        return named(opts.uc_preset, "引数 --uc-preset")
    text = batch.read_setting(root, "NOVELAI_UC_PRESET_TEXT")
    if text is not None:
        return text, "NOVELAI_UC_PRESET_TEXT"
    name = batch.read_setting(root, "NOVELAI_UC_PRESET")
    if name:
        return named(name.strip().lower(), "NOVELAI_UC_PRESET")
    return profile["uc"]["heavy"], "既定（画面のheavy）"


def resolve_size(root: Path, opts) -> str:
    """生成寸法を opts へ設定し、出所を返す。引数 > page-layout.json の generationCanvas > 画面の既定（832×1216）。"""
    if (opts.width is None) != (opts.height is None):
        raise ComposeError("--width と --height は両方指定してください。")
    if opts.width is not None:
        source = "引数"
    else:
        layout = root / "config/page-layout.json"
        canvas = api.read_json(layout).get("generationCanvas") if layout.is_file() else None
        if isinstance(canvas, dict):
            opts.width, opts.height, source = canvas.get("width"), canvas.get("height"), "config/page-layout.json の generationCanvas"
        else:
            opts.width, opts.height, source = 832, 1216, "既定（画面の既定。generationCanvas は未設定）"
    for size in (opts.width, opts.height):
        if type(size) is not int or size < 64 or size % 64:
            raise ComposeError("生成寸法は64以上の64の倍数にしてください。")
    return source


def resolve_quality(root: Path, opts, profile: dict) -> tuple[str, str]:
    if opts.no_quality_tags:
        return "", "付けない（--no-quality-tags）"
    if opts.quality_tags is not None:
        return opts.quality_tags, "引数 --quality-tags"
    env = batch.read_setting(root, "NOVELAI_QUALITY_TAGS")
    if env is not None:
        return env, "NOVELAI_QUALITY_TAGS"
    return profile["quality"], f"既定（{profile['label']}の画面の品質タグ）"


# ---------------------------------------------------------------- 要求の組み立て

def compose(opts: argparse.Namespace, raw_chars: list[dict], quality: str, uc_preset: str) -> tuple[dict, dict]:
    if opts.model not in MODELS:
        raise ComposeError("対応モデル: " + "・".join(MODELS))
    profile = MODELS[opts.model]
    characters, notes = build_characters(raw_chars, profile)
    for name in ("scene", "background", "style", "negative"):
        if "${" in getattr(opts, name):
            raise ComposeError(f"--{name} に ${{…}} があります。このスクリプトは変数を展開しません。値を渡してください。")
    counts = opts.count_tags if opts.count_tags is not None else count_tags(characters)
    caption_texts = [join_text(c["type"], c["appearance"], c["action"]) for c in characters]
    given = [counts, opts.scene, opts.background, opts.style] + caption_texts
    quality_text, added, skipped = merge_quality(quality, given, opts.allow_duplicate_quality)
    base = join_text(counts, opts.scene, opts.background, opts.style, quality_text)

    negative = join_text(uc_preset, opts.negative)  # 除外は重複を整理しない（画面と同じ）

    given_pos = [c["pos"] is not None for c in characters]
    if opts.coords == "on" and characters and not all(given_pos):
        raise ComposeError("配置ピン（--coords on）は全員に --charN-pos を指定してください。")
    if opts.coords == "auto" and any(given_pos) and not all(given_pos):
        raise ComposeError("配置ピンは全員に指定するか、全員に指定しないかのどちらかにしてください（座標だけ送って自動配置にするなら --coords off）。")
    pinned = bool(characters) and (opts.coords == "on" or (opts.coords == "auto" and all(given_pos)))
    # 配置ピンを使わない（use_coords=false）場合も centers は送られ、画面ではその値が絵に影響した（2026-10-05の実生成）。
    centers = [[{"x": c["pos"][0], "y": c["pos"][1]}] if c["pos"] is not None else [{"x": 0.5, "y": 0.5}] for c in characters]
    v4_prompt = {"caption": {"base_caption": base, "char_captions": [
        {"char_caption": text, "centers": centers[i]} for i, text in enumerate(caption_texts)]},
        "use_coords": pinned, "use_order": True, "legacy_uc": False}
    v4_negative = {"caption": {"base_caption": negative, "char_captions": [
        {"char_caption": c["negative"], "centers": centers[i]} for i, c in enumerate(characters)]},
        "use_coords": pinned, "use_order": False, "legacy_uc": False}

    params = dict(COMMON_PARAMETERS, **profile["extra"])
    params.update(width=opts.width, height=opts.height,
                  steps=opts.steps if opts.steps is not None else profile["steps"],
                  scale=opts.scale if opts.scale is not None else profile["scale"], cfg_rescale=opts.cfg_rescale,
                  sampler=opts.sampler, noise_schedule=opts.noise_schedule,
                  seed=opts.seed if opts.seed is not None else secrets.randbelow(4294967296),
                  negative_prompt=negative, v4_prompt=v4_prompt, v4_negative_prompt=v4_negative)
    request = {"action": "generate", "input": base, "model": opts.model, "parameters": params}
    info = {"quality_added": added, "quality_skipped": skipped, "notes": notes + (order_notes(characters, profile["grid"]) if pinned else []),
            "characters": caption_texts, "pinned": pinned, "profile": profile}
    return request, info


def parse_args(argv: list[str]):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    parser.add_argument("--id", required=True, help="要求ID。p01-03 の形式（input/novelai/requests/<ID>.json）")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(MODELS))
    parser.add_argument("--style", default="", help="絵柄（画風）。NOVELAI_STYLE_… の値")
    parser.add_argument("--background", default="", help="背景・場所・時間・光。NOVELAI_BACKGROUND_… の値")
    parser.add_argument("--scene", default="", help="構図・画角・全体の状況（upper body, eye level など）")
    parser.add_argument("--count-tags", help="人数タグを手で指定する（既定は人物から自動。人物なしは no humans）")
    parser.add_argument("--negative", default="", help="追加の除外語（プリセットの後ろに付く）")
    parser.add_argument("--uc-preset", help="除外プリセット名（V5 Curated: heavy・light・human・none、V5 Full・V4.5: heavy・none）")
    parser.add_argument("--uc-preset-text", help="除外プリセットの全文を直接指定する（空文字で付けない）")
    parser.add_argument("--coords", choices=("auto", "on", "off"), default="auto",
                        help="配置ピン。auto=全員に --charN-pos があれば使う。off=使わず（自動配置）、指定した座標だけ centers に入れる（画面と同じ絵を再現する場合）")
    parser.add_argument("--chars-json", help="人物の配列JSON（作品内の相対パス）。--charN-… とは併用しない")
    quality = parser.add_mutually_exclusive_group()
    quality.add_argument("--quality-tags", help="品質タグを上書きする（空文字で付けない）")
    quality.add_argument("--no-quality-tags", action="store_true", help="品質タグを付けない")
    parser.add_argument("--allow-duplicate-quality", action="store_true", help="入力と重複する品質タグも付ける（画面と同じ文を再現する場合）")
    parser.add_argument("--width", type=int, help="生成寸法（64の倍数）。省略時は config/page-layout.json の generationCanvas、未設定なら画面の既定832×1216")
    parser.add_argument("--height", type=int)
    parser.add_argument("--steps", type=int, help="省略時はV5が23、V4.5が28（novelai_api.py と同じ）。画面と同じ絵を再現するときは画面の値を渡す")
    parser.add_argument("--scale", type=float, help="Prompt Guidance。省略時はモデルごとの画面の値（V5 7.0、V4.5 5.0）")
    parser.add_argument("--cfg-rescale", type=float, default=0.0)
    parser.add_argument("--sampler", default="k_euler_ancestral")
    parser.add_argument("--noise-schedule", default="karras")
    parser.add_argument("--seed", type=int, help="省略時は乱数")
    parser.add_argument("--cast-from", help="登場人物の登録（characters.json の cast）を既存の要求IDから写す（識別特徴の点検を使う場合）")
    parser.add_argument("--force", action="store_true", help="同名の要求JSONを上書きする")
    parser.add_argument("--dry-run", action="store_true", help="保存せず、組み立てた内容だけ表示する")
    parser.add_argument("--no-check", action="store_true", help="保存後の送信なし確認（警告点検）を省く")
    parser.add_argument("--execute", action="store_true", help="確認後に novelai_batch.py generate で送信する")
    parser.add_argument("--accept-warnings", action="store_true")
    costs = parser.add_mutually_exclusive_group()
    costs.add_argument("--confirm-zero-anlas", action="store_true")
    costs.add_argument("--allow-anlas", action="store_true")
    parser.add_argument("--confirm-v5-allowance", action="store_true")
    parser.add_argument("--cost-note")
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parents[1]
    try:
        argv, numbered = extract_character_options(argv)
        opts = parse_args(argv).parse_args(argv)
        if not (root / "project.json").is_file():
            raise ComposeError("作品プロジェクトの scripts/ から実行してください。")
        if not batch.REQUEST_ID.fullmatch(opts.id):
            raise ComposeError("要求IDは英数字・-・_ だけにしてください（例 p01-03）。")
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
        profile = MODELS[opts.model]
        quality, quality_source = resolve_quality(root, opts, profile)
        uc_preset, uc_source = resolve_uc(root, opts, profile)
        size_source = resolve_size(root, opts)
        request, info = compose(opts, raw, quality, uc_preset)
        path = root / batch.REQUESTS_DIR / f"{opts.id}.json"
        p = request["parameters"]
        print(f"モデル: {profile['label']}（{opts.model}）。設定の根拠: {profile['status']}")
        print(f"品質タグ: 出所={quality_source} / 追加={', '.join(info['quality_added']) or 'なし'}"
              f" / 入力と重複のため不追加={', '.join(info['quality_skipped']) or 'なし'}")
        print(f"除外プリセット: 出所={uc_source}")
        print("ベース: " + request["input"])
        for i, text in enumerate(info["characters"], 1):
            centers = p["v4_prompt"]["caption"]["char_captions"][i - 1]["centers"][0]
            print(f"人物{i}: {text} @ ({centers['x']}, {centers['y']})" + ("" if info["pinned"] else "（配置ピンなしでも送る値）"))
        print("除外: " + p["negative_prompt"])
        print(f"寸法の出所: {size_source}")
        print(f"設定: {p['width']}×{p['height']}px / {p['steps']} steps / scale {p['scale']} / seed {p['seed']}"
              f" / 配置ピン {'あり' if info['pinned'] else 'なし（AI’s Choice）'}")
        if p["width"] * p["height"] > 1048576:
            info["notes"].append("1,048,576画素を超える。Opusの無消費候補の範囲外")
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
            for flag in ("accept_warnings", "confirm_zero_anlas", "allow_anlas", "confirm_v5_allowance"):
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
