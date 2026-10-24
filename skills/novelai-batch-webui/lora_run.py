"""lora_apply.py（作品ごとに実装するLoRA適用の外部処理）を、指定したコマへ１件ずつ順に適用する。

  python -X utf8 .agents/skills/novelai-batch-webui/lora_run.py --ids p01-03,p01-04
  python -X utf8 .agents/skills/novelai-batch-webui/lora_run.py --page 2 --page 3 --input latest --adopt
  python -X utf8 .agents/skills/novelai-batch-webui/lora_run.py --all

結果は output/lora/<要求ID>/lNNN.png と実行記録 lNNN.lora.json。NovelAIの候補（output/novelai/candidates/）は変更しない。
--adopt を付けた場合だけ、結果を scripts/novelai_batch.py の adopt（--file と同じ処理）で採用する。
失敗したら残りを実行せずに止まり、自動で再試行しない。
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import traceback
from typing import Callable

HERE = Path(__file__).resolve().parent
OUTPUT_DIR = "output/lora"


def find_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / "project.json").is_file() and (path / "scripts" / "novelai_batch.py").is_file():
            return path
    raise SystemExit("作品ルートが見つかりません。")


def load_hook():
    spec = importlib.util.spec_from_file_location("lora_apply", HERE / "lora_apply.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def readiness(root: Path) -> tuple[bool, str, str]:
    """(準備済みか, 理由, 処理名)。READY・apply・check() の順に確かめる。"""
    try:
        hook = load_hook()
    except Exception as error:
        return False, f"lora_apply.py を読み込めません: {type(error).__name__}: {error}", "?"
    name = str(getattr(hook, "NAME", "?"))
    if not getattr(hook, "READY", False):
        return False, "LoRA適用の処理が未実装です（lora_apply.py の READY が False）。", name
    if not callable(getattr(hook, "apply", None)):
        return False, "lora_apply.py に apply(job) がありません。", name
    check = getattr(hook, "check", None)
    if not callable(check):
        return False, "lora_apply.py に check(root) がありません。", name
    try:
        ok, message = check(root)
    except Exception as error:
        return False, f"check() で失敗しました: {type(error).__name__}: {error}", name
    if not ok:
        return False, str(message), name
    return True, "準備済み", name


@dataclass
class LoraJob:
    root: Path
    request_id: str
    page: int | None
    source_image: Path | None
    request: dict
    raw_request: dict
    output: Path
    work_dir: Path
    log: Callable[[str], None] = field(default=print)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def next_number(folder: Path) -> int:
    numbers = [int(m.group(1)) for p in folder.glob("l*") if (m := re.fullmatch(r"l(\d{3,})(?:\.png|\.lora\.json)", p.name))]
    return max(numbers or [0]) + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--ids", type=lambda s: [v for v in s.split(",") if v])
    target.add_argument("--page", type=int, action="append")
    target.add_argument("--all", action="store_true")
    parser.add_argument("--input", choices=("adopted", "latest"), default="adopted",
                        help="元にする画像：adopted＝採用中の画像（既定）、latest＝最新の候補")
    parser.add_argument("--adopt", action="store_true", help="結果を採用する（novelai_batch.py adopt --file と同じ処理）")
    parser.add_argument("--root")
    args = parser.parse_args()
    root = find_root(Path(args.root).resolve() if args.root else Path.cwd().resolve())
    sys.path.insert(0, str(root / "scripts"))
    import novelai_batch as batch  # noqa: E402

    ok, message, name = readiness(root)
    if not ok:
        print("エラー: " + message, file=sys.stderr)
        return 1
    hook = load_hook()
    try:
        ids = batch.select_ids(root, args.page, args.ids, args.all)
        variables = batch.read_variables(root)
    except Exception as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    adopted = batch.load_adopted(root)["adopted"]
    print(f"LoRA適用：{name}（版 {getattr(hook, 'VERSION', '?')}）／対象 {len(ids)}件／元画像 {args.input}" + ("／結果を採用" if args.adopt else ""))
    done = 0
    for index, request_id in enumerate(ids, 1):
        print(f"[{index}/{len(ids)}] {request_id}")
        if args.input == "adopted" and adopted.get(request_id):
            source = root / adopted[request_id]["path"]
        else:
            found = batch.candidates(root, request_id)
            source = found[-1] if found else None
        folder = root / OUTPUT_DIR / request_id
        folder.mkdir(parents=True, exist_ok=True)
        number = next_number(folder)
        output = folder / f"l{number:03d}.png"
        record_path = folder / f"l{number:03d}.lora.json"
        raw = json.loads(batch.request_files(root)[request_id].read_text(encoding="utf-8-sig"))
        resolved, _ = batch.resolved_request(root, request_id, variables)
        record = {"schema_version": 1, "request_id": request_id, "hook": name, "hook_version": str(getattr(hook, "VERSION", "?")),
                  "input_mode": args.input, "source_image": source.relative_to(root).as_posix() if source else None,
                  "source_sha256": sha256(source) if source and source.is_file() else None,
                  "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": "running"}
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        job = LoraJob(root, request_id, batch.page_of(request_id), source, resolved, raw, output, folder / "work",
                      lambda text: print("  " + str(text), flush=True))
        try:
            job.work_dir.mkdir(exist_ok=True)
            result = hook.apply(job)
            if not output.is_file():
                raise RuntimeError(f"書き出し先に画像がありません: {output.relative_to(root).as_posix()}")
            from PIL import Image
            with Image.open(output) as image:
                size = image.size
        except Exception as error:
            record.update(status="failed", error=f"{type(error).__name__}: {error}", finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            traceback.print_exc()
            print(f"エラー: {request_id} で停止しました（成功{done}件）。残りは実行していません。自動で再試行しません。", file=sys.stderr)
            return 1
        record.update(status="done", output=output.relative_to(root).as_posix(), output_sha256=sha256(output), size=list(size),
                      result=result, finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  保存: {output.relative_to(root).as_posix()}（{size[0]}×{size[1]}px）")
        if args.adopt:
            batch.adopt(root, request_id, None, output.relative_to(root).as_posix())
            print("  採用しました。")
        done += 1
    print(f"完了：{done}件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
