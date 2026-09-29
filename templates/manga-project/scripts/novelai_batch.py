"""NovelAIのコマ別要求JSONを一括で試し、人が候補を選び、同じ配置でページPNG・PSDを組み直す。

人が繰り返し実行して採用画像を選べるように、要求・候補・採用・ページ構成をすべてファイルに残す。

  list      要求・候補数・採用状況の一覧（通信なし）
  vars      .env等のキャラ別プロンプト変数（NOVELAI_CHAR_*）の一覧（通信なし）
  env-set   キャラ別プロンプト変数を .env へ書き込む（他の行は変えない）
  templatize 要求JSON内の変数値と同じ文を ${変数名} に置き換える
  generate  ページ単位・全ページ・指定IDの要求を１枚ずつ順に生成する（既定は送信しない確認）
  adopt     候補から採用画像を選ぶ
  build     採用画像・コマ内の配置・組版指定からページPNG（指定時はPSD）を作り直す

生成は novelai_api.py と同じ検証・費用確認・実行記録を使い、失敗時は止まって自動再送しない。
APIキーの値は表示・保存しない。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import novelai_api as api  # noqa: E402

REQUESTS_DIR = "input/novelai/requests"
ADOPTED = "input/novelai/adopted.json"
CANDIDATES_DIR = "output/novelai/candidates"
PAGES_DIR = "input/pages"
BUILD_DIR = "output/build"
VAR_FILES = (".env", ".secrets/novelai.env", ".secrets/.env")
VAR_NAME = re.compile(r"NOVELAI_CHAR_[A-Z0-9_]+")
PLACEHOLDER = re.compile(r"\$\{([^}]*)\}")
REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
PAGE_OF = re.compile(r"p(\d{1,3})-")


class BatchError(api.ClientError):
    pass


# ---------------------------------------------------------------- 送信前のプロンプト点検（語の検出。良否の判定ではない）

NEGATION = re.compile(r"\b(?:not|without|neither|never|don't|doesn't|isn't|no(?!\s+humans\b)\s+[a-z]+)\b", re.I)
INTENT = re.compile(r"\b(?:as if|about to|trying to|going to|seems? to|appears? to|wants? to|awkward(?:ly)?|feeling)\b", re.I)
PERSON = re.compile(r"\b(?:\d\s*(?:girl|boy|other)s?|solo)\b", re.I)
# 数値の年齢（25 years old 等）は見た目に効かず、man・woman は 1girl・1boy と別の２人目として描かれることがある
# （2026-09-29のユーザー指示）。teenage・high school student・adult 等の語は対象にしない。
EXTRA_PERSON = re.compile(r"(?:\b\d+\s*(?:years?[\s-]*old|yo|y/o)\b|\bage[ds]?\s*\d+\b|\d+\s*歳|\b(?:men|women|man|woman)\b)", re.I)
BODY_PART = re.compile(r"\b(?:shoes?|feet|foot|legs?|hands?|fingers?|arms?|lower body)\b", re.I)
COUNT = re.compile(r"\b(\d)\s*(girl|boy|other)s?\b", re.I)
CAMERA = re.compile(r"\b(from above|from below|from behind|from side|from the side|high angle|low angle|dutch angle)\b", re.I)


def positive_texts(request: dict) -> list[str]:
    texts = [request.get("input") or ""]
    caption = ((request.get("parameters") or {}).get("v4_prompt") or {}).get("caption") or {}
    texts.append(caption.get("base_caption") or "")
    texts += [c.get("char_caption", "") for c in caption.get("char_captions") or [] if isinstance(c, dict)]
    return [t for t in texts if isinstance(t, str) and t]


def lint_prompt(request: dict) -> list[str]:
    """字コンテの意図が画像に出にくい書き方を警告する。"""
    text = " , ".join(positive_texts(request))
    warnings = []
    found = sorted({m.group(0).lower() for m in NEGATION.finditer(text)})
    if found:
        warnings.append("肯定側に否定語: " + ", ".join(found) + "。その語に反応して逆に出ることがある。negative_promptへ移すか、人物なしは no humans")
    found = sorted({m.group(0).lower() for m in INTENT.finditer(text)})
    if found:
        warnings.append("意図の表現: " + ", ".join(found) + "。顔・手・体の見える形で書く")
    found = sorted({m.group(0).lower() for m in EXTRA_PERSON.finditer(text)})
    if found:
        warnings.append("数値の年齢・man/woman: " + ", ".join(found) + "。数値の年齢は見た目に効きにくく、man・woman は 1girl・1boy とは別の人物が増えることがある。"
                        "人物は 1girl・1boy・solo と外見の語で書く")
    no_humans = re.search(r"\bno humans\b", text, re.I)
    if BODY_PART.search(text) and not PERSON.search(text) and not no_humans:
        warnings.append("体の部分があるのに人物の指定がない。1boy, lower body, standing のように誰の体かを書く")
    if no_humans and PERSON.search(text):
        warnings.append("no humans と人物の指定が同時にある")
    # 外見の定型文に同じ 1girl が重なっても二重に数えないよう、種類ごとの最大数を合計する。
    kinds: dict[str, int] = {}
    for number, kind in COUNT.findall(request.get("input") or ""):
        kinds[kind.lower()] = max(kinds.get(kind.lower(), 0), int(number))
    people = sum(kinds.values())
    captions = (((request.get("parameters") or {}).get("v4_prompt") or {}).get("caption") or {}).get("char_captions")
    if people >= 2 and not captions:
        warnings.append(f"{people}人を１つの文に詰めている。１人ずつのコマに分けるか、姿勢と位置関係を外見より前に書く")
    return warnings


CHARACTERS = "input/novelai/characters.json"


def load_characters(root: Path) -> dict | None:
    """人物ごとの識別特徴と、要求ごとの登場人物。ファイルがなければ点検しない。"""
    path = root / CHARACTERS
    if not path.is_file():
        return None
    data = api.read_json(path)
    if not isinstance(data.get("characters"), dict) or not isinstance(data.get("cast", {}), dict):
        raise BatchError(f"{CHARACTERS} は characters と cast のオブジェクトにしてください。")
    return data


def lint_identity(request_id: str, request: dict, characters: dict | None) -> list[str]:
    """登場人物の識別特徴（髪色・眼鏡の形・服の重ね順など）が要求ごとに書かれているかを見る。"""
    if characters is None:
        return []
    text = " , ".join(positive_texts(request)).lower()
    cast = characters.get("cast", {}).get(request_id)
    if cast is None:
        if PERSON.search(text) or BODY_PART.search(text):
            return [f"登場人物が {CHARACTERS} の cast にない。人物名と見える特徴を登録する（人物なしなら no humans）"]
        return []
    warnings = []
    for name, expected in cast.items():
        features = (characters["characters"].get(name) or {}).get("features")
        if not isinstance(features, dict):
            warnings.append(f"cast の人物 {name} が characters にない")
            continue
        keys = list(features) if expected == "all" else expected
        if not isinstance(keys, list) or any(k not in features for k in keys):
            warnings.append(f"cast の {name} の特徴名が characters と合わない（\"all\" か特徴名の配列）")
            continue
        missing = [k for k in keys if str(features[k]).lower() not in text]
        if missing:
            warnings.append(f"{name} の識別特徴が抜けている: " + ", ".join(f"{k}（{features[k]}）" for k in missing)
                            + "。定型文のとおりに書くか、見えない特徴なら cast で対象から外す")
    return warnings


def camera_of(request: dict) -> str | None:
    match = CAMERA.search(" , ".join(positive_texts(request)))
    return match.group(1).lower() if match else None


# ---------------------------------------------------------------- 共通

def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def request_files(root: Path) -> dict[str, Path]:
    folder = root / REQUESTS_DIR
    files = {}
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        if not REQUEST_ID.fullmatch(path.stem):
            raise BatchError(f"要求ファイル名に使えない文字があります: {path.name}")
        files[path.stem] = path
    return files


def page_of(request_id: str) -> int | None:
    match = PAGE_OF.match(request_id)
    return int(match.group(1)) if match else None


def select_ids(root: Path, pages: list[int] | None, ids: list[str] | None, all_pages: bool) -> list[str]:
    files = request_files(root)
    if ids:
        missing = [i for i in ids if i not in files]
        if missing:
            raise BatchError("要求JSONがありません: " + ", ".join(missing))
        return ids
    if all_pages:
        chosen = [i for i in files if page_of(i) is not None]
    elif pages:
        chosen = [i for i in files if page_of(i) in pages]
    else:
        raise BatchError("--page、--ids、--all のいずれかを指定してください。")
    if not chosen:
        raise BatchError("対象の要求JSONがありません。ファイル名は p01-01.json のようにページ番号から始めます。")
    return chosen


def candidates(root: Path, request_id: str) -> list[Path]:
    folder = root / CANDIDATES_DIR / request_id
    return sorted(folder.glob("r[0-9][0-9][0-9].png")) if folder.is_dir() else []


def next_candidate(root: Path, request_id: str) -> int:
    """次の候補番号。PNGのない実行記録（結果不明）があれば、再送にならないよう止める。"""
    folder = root / CANDIDATES_DIR / request_id
    records = sorted(folder.glob("r[0-9][0-9][0-9].novelai.json")) if folder.is_dir() else []
    unknown = [r.name for r in records if not r.with_name(r.name.split(".")[0] + ".png").is_file()]
    if unknown:
        raise BatchError(f"{request_id} に結果不明の実行記録があります: {', '.join(unknown)}。"
                         "NovelAI側の結果と消費を確認し、記録を failed/ へ移してから再実行してください。")
    numbers = [int(p.name[1:4]) for p in candidates(root, request_id)] + [int(r.name[1:4]) for r in records]
    return max(numbers or [0]) + 1


def load_adopted(root: Path) -> dict:
    path = root / ADOPTED
    if not path.is_file():
        return {"schema_version": 1, "adopted": {}}
    data = api.read_json(path)
    data.setdefault("adopted", {})
    return data


# ---------------------------------------------------------------- キャラ別プロンプト変数

def parse_value(raw: str) -> str:
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        if end < 0:
            raise BatchError("変数の引用符が閉じていません。")
        return raw[1:end]
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()


def read_variables(root: Path) -> dict[str, tuple[str, str]]:
    """NOVELAI_CHAR_* だけを読み、他の行（APIキーを含む）は保持も表示もしない。"""
    found: dict[str, list[tuple[str, str]]] = {}
    for name, value in os.environ.items():
        if VAR_NAME.fullmatch(name):
            found.setdefault(name, []).append((value, "環境変数"))
    for relative in VAR_FILES:
        path = api.project_path(root, relative)
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            match = re.match(r"^\s*(?:export\s+)?(NOVELAI_CHAR_[A-Z0-9_]+)\s*=(.*)$", line)
            if match:
                found.setdefault(match.group(1), []).append((parse_value(match.group(2)), relative))
    duplicated = [f"{n}（{'・'.join(s for _, s in v)}）" for n, v in found.items() if len(v) > 1]
    if duplicated:
        raise BatchError("同じ変数が複数の場所にあります。１か所にしてください: " + ", ".join(duplicated))
    return {name: values[0] for name, values in found.items()}


def expand(value, variables: dict[str, tuple[str, str]], used: set[str]):
    if isinstance(value, str):
        def replace(match):
            name = match.group(1)
            if not VAR_NAME.fullmatch(name):
                raise BatchError(f"使えない変数名です: ${{{name}}}。キャラ別プロンプトは NOVELAI_CHAR_ で始めます。")
            if name not in variables:
                raise BatchError(f"変数 {name} が .env 等にありません。`vars` で確認してください。")
            used.add(name)
            return variables[name][0]
        return PLACEHOLDER.sub(replace, value)
    if isinstance(value, list):
        return [expand(v, variables, used) for v in value]
    if isinstance(value, dict):
        return {k: expand(v, variables, used) for k, v in value.items()}
    return value


def resolved_request(root: Path, request_id: str, variables) -> tuple[dict, set[str]]:
    raw = api.read_json(request_files(root)[request_id])
    used: set[str] = set()
    return expand(raw, variables, used), used


def env_set(root: Path, name: str, value: str) -> str:
    if not VAR_NAME.fullmatch(name):
        raise BatchError("変数名は NOVELAI_CHAR_ で始まる半角英大文字・数字・_ にしてください。")
    if "\n" in value or "\r" in value:
        raise BatchError("値は１行にしてください。")
    if '"' in value and "'" in value:
        raise BatchError("値に ' と \" の両方は使えません。")
    elsewhere = [s for n, (_, s) in read_variables(root).items() if n == name and s != ".env"]
    if elsewhere:
        raise BatchError(f"{name} は {elsewhere[0]} にあります。そちらを編集するか、片方を削除してください。")
    quote = "'" if '"' in value else '"'
    new_line = f"{name}={quote}{value}{quote}"
    path = api.project_path(root, ".env")
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.is_file() else []
    pattern = re.compile(r"^\s*(?:export\s+)?" + re.escape(name) + r"\s*=")
    replaced = False
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = new_line
            replaced = True
    if not replaced:
        lines.append(new_line)
    temporary = path.with_suffix(".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(path)
    return "更新" if replaced else "追加"


def templatize(root: Path, name: str, dry_run: bool) -> dict[str, int]:
    variables = read_variables(root)
    if name not in variables:
        raise BatchError(f"変数 {name} がありません。先に env-set で設定してください。")
    value = variables[name][0]
    if len(value) < 8:
        raise BatchError("値が短すぎるため、誤置換を避けて自動置換しません。")
    counts = {}

    def walk(node):
        if isinstance(node, str):
            counts["_"] = counts.get("_", 0) + node.count(value)
            return node.replace(value, "${" + name + "}")
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        return node

    result = {}
    for request_id, path in request_files(root).items():
        counts.clear()
        data = walk(api.read_json(path))
        if counts.get("_"):
            result[request_id] = counts["_"]
            if not dry_run:
                write_json(path, data)
    return result


# ---------------------------------------------------------------- 生成・採用

def generate(root: Path, args) -> None:
    ids = select_ids(root, args.page, args.ids, args.all)
    if len(ids) > args.max:
        raise BatchError(f"対象が{len(ids)}件で上限{args.max}件を超えます。ページを分けるか --max を指定してください。")
    variables = read_variables(root)
    plan = []
    warned = []
    cameras: dict[int | None, list[tuple[str, str | None]]] = {}
    characters = load_characters(root)
    for request_id in ids:
        request, used = resolved_request(root, request_id, variables)
        notes = lint_prompt(request) + lint_identity(request_id, request, characters)
        cameras.setdefault(page_of(request_id), []).append((request_id, camera_of(request)))
        existing = candidates(root, request_id)
        mode = args.seed if args.seed != "auto" else ("request" if not existing else "random")
        if mode == "random":
            request.setdefault("parameters", {})["seed"] = secrets.randbelow(4294967296)
        request, payload = api.prepare_request_data(root, request)
        number = next_candidate(root, request_id)
        output = f"{CANDIDATES_DIR}/{request_id}/r{number:03d}.png"
        params = request["parameters"]
        plan.append((request_id, request, payload, output))
        print(f"{request_id}: {params['width']}×{params['height']}px / {params['steps']} steps / seed {params['seed']}"
              f" / 変数 {','.join(sorted(used)) or 'なし'} → {output}")
        for note in notes:
            print(f"  [警告] {note}")
        if notes:
            warned.append(request_id)
    selected = set(ids)
    for page in cameras:
        if page is None:
            continue
        # 一部のコマだけを再生成する場合も、ページ内の全コマ（p01-03 の形式。差し替え案は除く）の並びで判定する。
        base_ids = [i for i in request_files(root) if page_of(i) == page and re.fullmatch(r"p\d{1,3}-\d{1,3}", i)]
        items = [(i, camera_of(resolved_request(root, i, variables)[0])) for i in base_ids]
        for i in range(2, len(items)):
            if not selected.intersection(r for r, _ in items[i - 2:i + 1]):
                continue
            run = [c for _, c in items[i - 2:i + 1]]
            if run[0] and run.count(run[0]) == 3:
                print(f"  [警告] {items[i][0]}: 同じ画角（{run[0]}）が３コマ続く。字コンテの意図に合うか確認する")
                warned.append(items[i][0])
    if warned:
        print(f"プロンプトの警告：{len(set(warned))}件。直すか、残す理由を docs/production/NOVELAI-BATCH.md に書いてから"
              " --accept-warnings を付けて送信する。書き方は docs/knowledge/novelai-composed-production.md の要求プロンプトの組み立て。")
    if not args.execute:
        print(f"送信なし（{len(plan)}件）。実行には --execute と費用確認の指定が必要です。")
        return
    if warned and not args.accept_warnings:
        raise BatchError("プロンプトの警告が残っているため送信しません（" + ", ".join(sorted(set(warned))) + "）。")
    done = []
    for index, (request_id, request, payload, output) in enumerate(plan):
        if index:
            time.sleep(args.interval)
        print(f"[{index + 1}/{len(plan)}] {request_id}")
        try:
            api.execute_generation(root, request, payload, output, args)
        except api.ClientError as error:
            raise BatchError(f"{request_id} で停止しました（成功{len(done)}件）。残りは送信していません。自動再送はしません。\n{error}") from None
        done.append(output)
    print(f"完了：{len(done)}件。候補を見比べ、採用する番号を adopt で記録してください。")
    print("例: python -X utf8 scripts/novelai_batch.py adopt " + plan[0][0] + " --candidate " + Path(plan[0][3]).stem[1:])


def adopt(root: Path, request_id: str, number: int | None, file: str | None) -> Path:
    if request_id not in request_files(root) and not file:
        raise BatchError(f"要求JSONがありません: {request_id}")
    if file:
        path = api.project_path(root, file)
    else:
        path = root / CANDIDATES_DIR / request_id / f"r{number:03d}.png"
    if not path.is_file():
        raise BatchError("採用する画像がありません: " + (rel(root, path) if path.is_relative_to(root) else str(file)))
    data = load_adopted(root)
    data["adopted"][request_id] = {"path": rel(root, path), "sha256": sha(path), "adopted_at": now()}
    write_json(root / ADOPTED, data)
    return path


# ---------------------------------------------------------------- ページの組み直し

def placement(frame, image_size, focus, zoom, rotation):
    """コマの外接矩形に画像を覆うように置く。focusは画像内の中心に置く点（0〜1）。"""
    x0, y0, x1, y1 = frame
    bw, bh = x1 - x0, y1 - y0
    iw, ih = image_size
    theta = math.radians(rotation)
    c, s = math.cos(theta), math.sin(theta)
    need_w, need_h = bw * abs(c) + bh * abs(s), bw * abs(s) + bh * abs(c)
    scale = max(need_w / iw, need_h / ih) * zoom
    fx, fy = focus[0] * iw, focus[1] * ih
    notes = []
    if not rotation:
        hw, hh = bw / (2 * scale), bh / (2 * scale)
        cx, cy = min(max(fx, hw), iw - hw) if iw >= 2 * hw else iw / 2, min(max(fy, hh), ih - hh) if ih >= 2 * hh else ih / 2
        # 画像がコマにちょうど収まる方向は動かせないので注記しない。動かせる方向で端に当たった場合だけ知らせる。
        movable_x, movable_y = iw - 2 * hw > 1, ih - 2 * hh > 1
        if (movable_x and abs(cx - fx) > 0.5) or (movable_y and abs(cy - fy) > 0.5):
            notes.append("focusが画像の端を越えたため、見える範囲を端で止めた")
        fx, fy = cx, cy
    ox, oy = bw / 2, bh / 2
    # コマ内座標 → 元画像座標の逆変換（PILのAFFINE形式）。
    a, b = c / scale, s / scale
    d, e = -s / scale, c / scale
    return [a, b, fx - (a * ox + b * oy), d, e, fy - (d * ox + e * oy)], notes


def build(root: Path, page: int, write_psd: bool) -> Path:
    from PIL import Image
    import export_composed_psd as exporter
    import typeset_manga as typesetter

    manifest_path = root / PAGES_DIR / f"page-{page:02d}.json"
    if not manifest_path.is_file():
        raise BatchError(f"ページ構成がありません: {rel(root, manifest_path)}")
    manifest = api.read_json(manifest_path)
    if manifest.get("schema_version") != 1:
        raise BatchError("ページ構成の schema_version は 1 にしてください。")
    layout = api.read_json(api.project_path(root, manifest["layout"]))
    working = layout["dimensions"]["working"]
    size = [int(round(working["width"])), int(round(working["height"]))]
    polygons = {p["order"]: [list(v) for v in p["polygon"]] for p in layout["template"]["panels"]}
    adopted = load_adopted(root)["adopted"]

    base = root / BUILD_DIR / f"page-{page:02d}"
    number = 1 + max([int(p.name[1:]) for p in base.glob("v[0-9][0-9][0-9]")] or [0])
    out_dir = base / f"v{number:03d}"

    panels, notes, missing = [], {}, []
    for entry in manifest.get("panels", []):
        order = entry["panel"]
        if order not in polygons:
            raise BatchError(f"コマ{order}がレイアウトにありません。")
        if entry.get("source"):
            source = entry["source"]
        elif entry.get("request"):
            chosen = adopted.get(entry["request"])
            if not chosen:
                missing.append(entry["request"])
                continue
            source = chosen["path"]
            if sha(api.project_path(root, source)) != chosen["sha256"]:
                raise BatchError(f"採用画像が採用時から変わっています: {source}")
        else:
            continue  # 絵を置かないコマ
        with Image.open(api.project_path(root, source)) as opened:
            image_size = opened.size
        polygon = polygons[order]
        xs, ys = [v[0] for v in polygon], [v[1] for v in polygon]
        frame = [min(xs), min(ys), max(xs), max(ys)]
        affine, note = placement(frame, image_size, entry.get("focus", [0.5, 0.5]), float(entry.get("zoom", 1.0)),
                                 float(entry.get("rotation", 0)))
        a, b, c, d, e, f = affine
        uncovered = False
        for px, py in polygon:  # コマの角が元画像の外に当たるなら、その部分に絵がない
            lx, ly = px - frame[0], py - frame[1]
            sx, sy = a * lx + b * ly + c, d * lx + e * ly + f
            uncovered |= not (-1 <= sx <= image_size[0] + 1 and -1 <= sy <= image_size[1] + 1)
        if uncovered:
            note = note + ["コマの一部に画像がない。focus・zoom・rotationを見直すか、PSDで手作業で調整する"]
        if note:
            notes[f"コマ{order}"] = note
        panel = {"name": entry.get("name", f"コマ{order:02d}"), "source": source, "frame": frame,
                 "inverse_affine": affine, "polygon": polygon}
        if entry.get("original_source"):
            panel["original_source"] = entry["original_source"]
        panels.append(panel)
    if missing:
        raise BatchError("採用画像が未選択です: " + ", ".join(missing) + "。adopt で選んでから build してください。")

    # 組版（フキダシ・文字・画中の文字・枠）を透明レイヤーで作る。枠は最上段近くに重なり、コマ外を隠す。
    typeset_spec = api.read_json(api.project_path(root, manifest["typeset"])) if manifest.get("typeset") else {
        "schema_version": 1, "balloons": []}
    typeset_spec.setdefault("layout", manifest["layout"])
    report = typesetter.render(typeset_spec, root, out_dir / "typeset", None, not manifest.get("frames_in_art", False))

    # 効果音等の追加素材は、コマ枠の上・フキダシの下に重ねる。
    extra = []
    for index, item in enumerate(manifest.get("overlays", []), 1):
        with Image.open(api.project_path(root, item["source"])) as opened:
            image = opened.convert("RGBA")
        scale = float(item.get("scale", 1.0))
        if scale != 1.0:
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
        if item.get("rotation"):
            image = image.rotate(float(item["rotation"]), resample=Image.Resampling.BICUBIC, expand=True)
        path = out_dir / "overlays" / f"{index:02d}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        cx, cy = item["center"]
        extra.append({"name": item.get("name", f"追加素材{index:02d}"), "source": rel(root, path),
                      "position": [int(round(cx - image.width / 2)), int(round(cy - image.height / 2))]})
    overlays = []
    for layer in report["overlays_for_export_composed_psd"]:
        if layer["name"] == "フキダシ":
            overlays.extend(extra)
            extra = []
        overlays.append(layer)
    overlays.extend(extra)

    spec = {"schema_version": 1, "page": {"size": size, "dpi": manifest.get("dpi", 300)}, "panels": panels, "overlays": overlays}
    result = exporter.export(spec, root, Path(rel(root, out_dir / f"page-{page:02d}")), write_psd, False)
    # 確認用の縮小・注記画像は、原画を合成した完成ページから作る（組版フォルダの見本は原画を含まない）。
    review = typesetter.review_images(out_dir / f"page-{page:02d}.png", typeset_spec, root, out_dir, f"page-{page:02d}")
    write_json(out_dir / "build.json", {
        "schema_version": 1, "built_at": now(), "page": page, "manifest": rel(root, manifest_path),
        "manifest_sha256": sha(manifest_path), "panels": [{"name": p["name"], "source": p["source"]} for p in panels],
        "placement_notes": notes, "typeset_summary": report["summary"], "typeset_check": rel(root, out_dir / "typeset" / "check.json"),
        "png": result["output_png"], "psd": rel(root, out_dir / f"page-{page:02d}.psd") if write_psd else None,
        "review_display": rel(root, review["display"]), "review_check_overlay": rel(root, review["check_overlay"]),
        "psd_verification": result["verification"]})
    print(f"page {page}: {result['output_png']}" + (f"（PSDあり）" if write_psd else "") +
          f" / 組版の点検 エラー{report['summary']['error']}・警告{report['summary']['warning']}")
    print(f"  確認用（原画入り）: {rel(root, review['display'])}、注記入り: {rel(root, review['check_overlay'])}（掲載には使わない）")
    for name, messages in notes.items():
        print(f"  [配置] {name}: {'・'.join(messages)}")
    for issue in report["issues"]:
        if issue["level"] == "error":
            print(f"  [error] {issue['code']} {issue['target']}: {issue['message_ja']}")
    return out_dir


# ---------------------------------------------------------------- CLI

def pages_from_manifests(root: Path) -> list[int]:
    folder = root / PAGES_DIR
    found = [int(m.group(1)) for p in folder.glob("page-*.json") if (m := re.fullmatch(r"page-(\d{2,3})", p.stem))] if folder.is_dir() else []
    if not found:
        raise BatchError(f"{PAGES_DIR}/page-01.json のようなページ構成がありません。")
    return sorted(found)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="要求・候補・採用の一覧")
    listing.add_argument("--page", type=int, action="append")
    show = commands.add_parser("vars", help="キャラ別プロンプト変数の一覧")
    show.add_argument("--show-values", action="store_true", help="値（プロンプト本文）も表示する")
    setter = commands.add_parser("env-set", help="キャラ別プロンプト変数を .env へ書く")
    setter.add_argument("name")
    group = setter.add_mutually_exclusive_group(required=True)
    group.add_argument("--value")
    group.add_argument("--value-file", help="値を書いたUTF-8テキスト（作品内の相対パス）")
    templ = commands.add_parser("templatize", help="要求JSON内の変数値を ${変数名} に置き換える")
    templ.add_argument("name")
    templ.add_argument("--dry-run", action="store_true")
    gen = commands.add_parser("generate", help="要求を１枚ずつ順に生成（既定は送信しない確認）")
    gen.add_argument("--page", type=int, action="append", help="ページ番号。複数指定可")
    gen.add_argument("--ids", type=lambda s: [v for v in s.split(",") if v], help="要求IDをカンマ区切りで指定")
    gen.add_argument("--all", action="store_true", help="全ページの要求（p01-… の形式）")
    gen.add_argument("--seed", choices=("auto", "request", "random"), default="auto",
                     help="auto：初回は要求のseed、２回目以降は乱数（既定）")
    gen.add_argument("--interval", type=float, default=3.0, help="送信間隔（秒）")
    gen.add_argument("--max", type=int, default=30, help="１回の実行で送る上限件数")
    gen.add_argument("--execute", action="store_true", help="人が依頼した生成を送信する")
    gen.add_argument("--accept-warnings", action="store_true", help="プロンプトの警告を確認し、残す理由を記録済み")
    costs = gen.add_mutually_exclusive_group()
    costs.add_argument("--confirm-zero-anlas", action="store_true")
    costs.add_argument("--allow-anlas", action="store_true")
    gen.add_argument("--confirm-v5-allowance", action="store_true")
    gen.add_argument("--cost-note")
    pick = commands.add_parser("adopt", help="採用画像を記録する")
    pick.add_argument("request_id")
    which = pick.add_mutually_exclusive_group(required=True)
    which.add_argument("--candidate", type=int, help="候補番号（r003.png なら 3）")
    which.add_argument("--file", help="修正版など作品内の画像を直接指定")
    make = commands.add_parser("build", help="ページPNG（指定時はPSD）を組み直す")
    make.add_argument("--page", type=int, action="append")
    make.add_argument("--all", action="store_true")
    make.add_argument("--write-psd", action="store_true", help="PSDも作る（PNG確認後、依頼がある場合）")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        if not (root / "project.json").is_file():
            raise BatchError("作品プロジェクトの scripts/ から実行してください。")
        if args.command == "list":
            adopted = load_adopted(root)["adopted"]
            for request_id, path in request_files(root).items():
                if args.page and page_of(request_id) not in args.page:
                    continue
                used = set(PLACEHOLDER.findall(path.read_text(encoding="utf-8-sig")))
                chosen = adopted.get(request_id, {}).get("path", "未採用")
                print(f"{request_id}: 候補{len(candidates(root, request_id))}件 / 採用 {chosen} / 変数 {','.join(sorted(used)) or 'なし'}")
        elif args.command == "vars":
            variables = read_variables(root)
            if not variables:
                print("NOVELAI_CHAR_ で始まる変数はありません。")
            for name, (value, source) in sorted(variables.items()):
                print(f"{name}（{source}、{len(value)}字）" + (f": {value}" if args.show_values else ""))
        elif args.command == "env-set":
            value = args.value if args.value is not None else api.project_path(root, args.value_file).read_text(encoding="utf-8-sig").strip()
            print(f"{args.name} を .env に{env_set(root, args.name, value)}しました（他の行は変更していません）。")
        elif args.command == "templatize":
            result = templatize(root, args.name, args.dry_run)
            for request_id, count in result.items():
                print(f"{request_id}: {count}か所" + ("（確認のみ）" if args.dry_run else ""))
            if not result:
                print("置き換える箇所はありません。")
        elif args.command == "generate":
            generate(root, args)
        elif args.command == "adopt":
            path = adopt(root, args.request_id, args.candidate, args.file)
            print(f"{args.request_id}: {rel(root, path)} を採用しました。")
        elif args.command == "build":
            pages = pages_from_manifests(root) if args.all else (args.page or [])
            if not pages:
                raise BatchError("--page または --all を指定してください。")
            for page in pages:
                build(root, page, args.write_psd)
    except api.ClientError as error:
        print("エラー: " + str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"エラー: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
