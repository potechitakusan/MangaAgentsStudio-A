"""PixAI一括制作（pixai_batch.py）をブラウザーから操作するローカルWebUI。

作品プロジェクト（project.json と scripts/pixai_batch.py がある作品ルート）で起動する。

  python -X utf8 .agents/skills/pixai-batch-webui/pixai_webui.py            # http://127.0.0.1:8775/?token=…
  python -X utf8 .agents/skills/pixai-batch-webui/pixai_webui.py --port 8800 --root 作品ルート

できること
  - .env.pixai のキャラクター・絵柄・背景・LoRAの変数（PIXAI_CHAR_・PIXAI_STYLE_・PIXAI_BACKGROUND_・PIXAI_LORA_）の
    表示・編集・追加、templatize
  - 要求JSON（input/pixai/requests/）の編集。v2 はプロンプト・除外・縦横比・解像度・mode・画風プリセット・LoRA（最大5件）・
    seed・枚数・promptHelper を画面の項目で、v1 は parameters をJSONで。差し替え案の複製、変数展開後の確認
  - 生成（送信なし確認／実行）、完了待ちが途切れた記録の取得し直し（fetch）、候補の比較と採用、最新候補の一括採用
  - ページ構成（input/pages/）・組版指定（input/typeset/）のJSON編集、build（PSDは指定時のみ）、ページ送りの確認
  - APIキーの読込確認（key-status）と接続確認（status。画像生成なし）

守ること
  - 生成・採用・組み直し・.env.pixai の書き込みは、作品の scripts/pixai_batch.py・pixai_api.py をそのまま呼ぶ。
    費用確認・実行記録・自動再送しない扱いはスクリプト側のまま。生成には、利用者がクレジット消費を明示許可したチェックと
    確認内容（cost-note）が必要。
  - APIキーは読まない・表示しない（変数は pixai_batch.read_variables が許可した接頭辞だけ）。
  - 127.0.0.1 だけで待ち受け、起動ごとのトークンがないAPI呼び出しを拒否する。ブラウザーは自動で開かない。
  - JSONを保存するときは、前の内容を output/webui-pixai/history/ に残す。
Python 3.10以上の標準ライブラリだけで動く（build には作品の既存要件の Pillow が必要）。
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading
from urllib.parse import parse_qs, urlparse

IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp"}
SERVE_DIRS = ("output/", "input/", "templates/onomatopoeia/")
WORK = "output/webui-pixai"
MAX_LIMIT = 1000  # generate --max の上限（pixai_batch.py の既定は30件）
PAGE_FILE = re.compile(r"page-(\d{2,3})\.json")


def find_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / "project.json").is_file() and (path / "scripts" / "pixai_batch.py").is_file():
            return path
    raise SystemExit("作品ルート（project.json と scripts/pixai_batch.py）が見つかりません。--root で指定してください。")


class Project:
    def __init__(self, root: Path):
        self.root = root
        sys.path.insert(0, str(root / "scripts"))
        import pixai_batch  # noqa: E402  作品の同梱スクリプトを使う
        self.batch = pixai_batch
        self.api = pixai_batch.api
        self.job: dict | None = None
        self.lock = threading.Lock()

    # ------------------------------------------------------------ パス
    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    def inside(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("作品ルート外のパスです")
        return path

    def backup(self, path: Path) -> None:
        if path.is_file():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            target = self.root / WORK / "history" / f"{path.parent.name}-{path.stem}-{stamp}{path.suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)

    def write_json(self, path: Path, data) -> None:
        self.backup(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    # ------------------------------------------------------------ 読み取り
    def options(self) -> dict:
        """画面の選択肢（公式の値）。pixai_api.py の表をそのまま使う。"""
        return {"aspects": list(self.api.RESOLUTIONS), "resolutions": self.api.RESOLUTIONS, "sizes": list(self.api.SIZES),
                "modes": list(self.api.MODES), "styles": self.api.STYLE_PRESETS, "samplers": list(self.api.SAMPLERS),
                "models": {m["id"]: f"{m['label']}（{m['type'].upper()}）" for m in self.api.MODELS.values()},
                "model_types": self.api.MODEL_TYPES}

    def variables(self) -> list[dict]:
        try:
            found = self.batch.read_variables(self.root)
        except Exception as error:  # 重複定義など
            return [{"error": str(error)}]
        return [{"name": n, "value": v, "source": s} for n, (v, s) in sorted(found.items())]

    def pages(self) -> list[dict]:
        result = []
        manifests = self.root / self.batch.PAGES_DIR
        numbers = sorted({int(m.group(1)) for p in manifests.glob("page-*.json") if (m := PAGE_FILE.fullmatch(p.name))}) if manifests.is_dir() else []
        for page in numbers:
            folder = self.root / self.batch.BUILD_DIR / f"page-{page:02d}"
            versions = sorted((p for p in folder.glob("v[0-9][0-9][0-9]") if p.is_dir()), key=lambda p: p.name) if folder.is_dir() else []
            latest = None
            if versions:
                v = versions[-1]
                files = {k: v / f"page-{page:02d}{suffix}" for k, suffix in
                         (("png", ".png"), ("display", "-display.png"), ("check", "-check-overlay.png"), ("psd", ".psd"))}
                latest = {"version": v.name, **{k: self.rel(p) for k, p in files.items() if p.is_file()}}
                build = v / "build.json"
                if build.is_file():
                    info = json.loads(build.read_text(encoding="utf-8"))
                    latest["summary"] = info.get("typeset_summary")
                    latest["notes"] = info.get("placement_notes")
            result.append({"page": page, "versions": [v.name for v in versions], "latest": latest})
        return result

    def state(self) -> dict:
        adopted = self.batch.load_adopted(self.root)["adopted"]
        requests = []
        for request_id, path in self.batch.request_files(self.root).items():
            text = path.read_text(encoding="utf-8-sig")
            try:
                kind = json.loads(text).get("api")
            except (ValueError, AttributeError):
                kind = None
            requests.append({
                "id": request_id, "page": self.batch.page_of(request_id), "api": kind,
                "candidates": [self.rel(p) for p in self.batch.candidates(self.root, request_id)],
                "batches": [self.batch.reserved_numbers(r) for r in self.batch.run_records(self.root, request_id)],
                "unknown": len(self.batch.unknown_records(self.root, request_id)),
                "adopted": adopted.get(request_id, {}).get("path"),
                "vars": sorted(set(self.batch.PLACEHOLDER.findall(text))),
            })
        return {"project": json.loads((self.root / "project.json").read_text(encoding="utf-8-sig")).get("name", self.root.name),
                "requests": requests, "pages": self.pages(), "variables": self.variables(), "job": self.job_view(),
                "options": self.options()}

    def request(self, request_id: str) -> dict:
        path = self.batch.request_files(self.root).get(request_id)
        if not path:
            raise ValueError("要求JSONがありません: " + request_id)
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        try:
            resolved, used = self.batch.resolved_request(self.root, request_id, self.batch.read_variables(self.root))
            lint = self.batch.lint_prompt(resolved)
        except Exception as error:
            resolved, used, lint = None, set(), [f"展開できません: {error}"]
        return {"id": request_id, "raw": raw, "resolved": resolved, "used": sorted(used), "lint": lint}

    def save_request(self, request_id: str, data: dict, new: bool = False) -> None:
        if not self.batch.REQUEST_ID.fullmatch(request_id):
            raise ValueError("要求IDは英数字・-・_ で書いてください（例 p01-03b）")
        if not isinstance(data, dict) or not (
                (data.get("api") == "v2" and isinstance(data.get("body"), dict) and isinstance(data["body"].get("prompt"), str))
                or (data.get("api") == "v1" and isinstance(data.get("parameters"), dict) and isinstance(data["parameters"].get("prompts"), str))):
            raise ValueError('要求JSONの形（{"api": "v2", "body": {"prompt": …}} か {"api": "v1", "parameters": {"prompts": …}}）がありません')
        path = self.root / self.batch.REQUESTS_DIR / f"{request_id}.json"
        if new and path.exists():
            raise ValueError("同じIDの要求があります: " + request_id)
        self.write_json(path, data)

    def page(self, number: int) -> dict:
        manifest = self.root / self.batch.PAGES_DIR / f"page-{number:02d}.json"
        data = {"page": number, "manifest": None, "typeset": None, "typeset_path": None}
        if manifest.is_file():
            data["manifest"] = json.loads(manifest.read_text(encoding="utf-8-sig"))
            typeset = data["manifest"].get("typeset")
            if typeset and self.inside(typeset).is_file():
                data["typeset_path"] = typeset
                data["typeset"] = json.loads(self.inside(typeset).read_text(encoding="utf-8-sig"))
        return data

    def save_page(self, number: int, manifest: dict | None, typeset: dict | None) -> None:
        if manifest is not None:
            if manifest.get("schema_version") != 1 or not isinstance(manifest.get("panels"), list):
                raise ValueError("ページ構成は schema_version 1 と panels が必要です")
            self.write_json(self.root / self.batch.PAGES_DIR / f"page-{number:02d}.json", manifest)
        if typeset is not None:
            current = self.page(number)["manifest"] or manifest or {}
            target = current.get("typeset")
            if not target:
                raise ValueError("ページ構成に typeset のパスがありません")
            if typeset.get("schema_version") != 1:
                raise ValueError("組版指定は schema_version 1 が必要です")
            self.write_json(self.inside(target), typeset)

    # ------------------------------------------------------------ 実行（既存スクリプトを呼ぶ）
    def command(self, action: str, body: dict) -> list[str]:
        script = ["scripts/pixai_batch.py"]
        ids = [i for i in body.get("ids", []) if i]
        for i in ids:
            if not self.batch.REQUEST_ID.fullmatch(i):
                raise ValueError("要求IDが不正です: " + i)
        pages = [int(p) for p in body.get("pages", [])]
        target: list[str] = []
        if body.get("all"):
            target = ["--all"]
        elif ids:
            target = ["--ids", ",".join(ids)]
        elif pages:
            for p in pages:
                target += ["--page", str(p)]
        if action == "generate":
            if not target:
                raise ValueError("対象（ID・ページ・全ページ）を指定してください")
            args = script + ["generate", *target, "--seed", body.get("seed", "auto")]
            if body.get("seed") not in ("auto", "request", "random"):
                raise ValueError("seed の指定が不正です")
            limit = int(body.get("max") or 30)
            if not 1 <= limit <= MAX_LIMIT:
                raise ValueError(f"上限件数は1～{MAX_LIMIT}で指定してください")
            if limit != 30:
                args += ["--max", str(limit)]
            size = str(body.get("batch_size", "auto"))
            if size not in ("auto", "1", "4"):
                raise ValueError("枚数の指定が不正です")
            if size != "auto":
                args += ["--batch-size", size]
            if body.get("execute"):
                note = str(body.get("cost_note", "")).strip()
                if not body.get("confirm_credits") or not note:
                    raise ValueError("実行には「クレジット消費の明示許可を確認した」チェックと確認内容（cost-note）が必要です。")
                args += ["--execute", "--confirm-credits", "--cost-note", note]
                if body.get("allow_unverified"):
                    args.append("--allow-unverified")
                if body.get("accept_warnings"):
                    args.append("--accept-warnings")
            return args
        if action == "fetch":
            if not target:
                raise ValueError("対象を指定してください")
            return script + ["fetch", *target]
        if action == "adopt":
            if len(ids) != 1 or not str(body.get("candidate", "")).isdigit():
                raise ValueError("採用には要求IDと候補番号が必要です")
            return script + ["adopt", ids[0], "--candidate", str(int(body["candidate"]))]
        if action == "adopt-latest":
            if not target:
                raise ValueError("対象を指定してください")
            return script + ["adopt-latest", *target] + (["--dry-run"] if body.get("dry_run") else [])
        if action == "build":
            if not (body.get("all") or pages):
                raise ValueError("ページを指定してください")
            return script + ["build", *(["--all"] if body.get("all") else [a for p in pages for a in ("--page", str(p))])] + \
                (["--write-psd"] if body.get("write_psd") else [])
        if action == "list":
            return script + ["list"]
        if action == "templatize":
            name = str(body.get("name", ""))
            if not self.batch.VAR_NAME.fullmatch(name):
                raise ValueError("変数名が不正です")
            return script + ["templatize", name] + (["--dry-run"] if body.get("dry_run") else [])
        if action == "env-set":
            name, value = str(body.get("name", "")), str(body.get("value", ""))
            if not self.batch.VAR_NAME.fullmatch(name):
                raise ValueError("変数名は " + self.batch.VAR_HELP)
            return script + ["env-set", name, "--value", value]
        if action in ("key-status", "status"):
            return ["scripts/pixai_api.py", action]
        raise ValueError("未対応の操作です: " + action)

    def start(self, action: str, body: dict) -> dict:
        args = self.command(action, body)
        with self.lock:
            if self.job and self.job["state"] == "running":
                raise ValueError("前の操作が実行中です。終わってから実行してください。")
            shown = ["python", "-X", "utf8", *args]
            self.job = {"id": secrets.token_hex(4), "action": action, "command": " ".join(quote(a) for a in shown),
                        "state": "running", "log": "", "code": None, "started": datetime.now().isoformat(timespec="seconds")}
            job = self.job
        threading.Thread(target=self.run, args=(job, args), daemon=True).start()
        return self.job_view()

    def run(self, job: dict, args: list[str]) -> None:
        try:
            # -u：出力をため込まず１行ずつ受け取り、実行中も進み具合（[3/39] p01-03・タスクの状態）をログへ出す。
            process = subprocess.Popen([sys.executable, "-u", "-X", "utf8", *args], cwd=self.root, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            job["process"] = process
            for line in process.stdout:
                job["log"] += line
            job["code"] = process.wait()
        except OSError as error:
            job["log"] += f"起動できません: {error}\n"
            job["code"] = -1
        job["state"] = "done" if job["code"] == 0 else "failed"
        log = self.root / WORK / "logs" / f"{datetime.now():%Y%m%d-%H%M%S}-{job['action']}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(job["command"] + "\n\n" + job["log"], encoding="utf-8")

    def job_view(self) -> dict | None:
        return {k: v for k, v in self.job.items() if k != "process"} if self.job else None

    def stop(self) -> dict | None:
        """実行中の操作を中止する。完了待ちの途中なら、その記録は taskId 付きで残る（fetch で取得し直せる）。"""
        job = self.job
        if not job or job["state"] != "running" or not job.get("process"):
            raise ValueError("実行中の操作はありません。")
        job["log"] += ("\n[WebUI] 中止を指示しました。作成済みのタスクはPixAI側で続き、記録は画像なしで残ります"
                       "（実行結果の整理の「PixAIから取得し直す」で取得できます）。\n")
        job["process"].kill()
        return self.job_view()

    # ------------------------------------------------------------ 実行結果の整理（削除せず、サブフォルダへ移す）
    def folder(self, request_id: str) -> Path:
        if not self.batch.REQUEST_ID.fullmatch(request_id):
            raise ValueError("要求IDが不正です: " + request_id)
        return self.root / self.batch.CANDIDATES_DIR / request_id

    def records(self, request_id: str) -> dict:
        folder = self.folder(request_id)
        adopted = self.batch.load_adopted(self.root)["adopted"].get(request_id, {}).get("path")
        result = {"id": request_id, "exists": request_id in self.batch.request_files(self.root), "adopted": adopted}
        items, moved = {}, []
        if folder.is_dir():
            for path in folder.iterdir():
                m = re.fullmatch(r"r(\d{3,})\.(.+)", path.name)
                if path.is_file() and m:
                    items.setdefault(int(m.group(1)), []).append(path)
            for sub in ("failed", "discarded"):
                for batch_dir in sorted((folder / sub).glob("*")) if (folder / sub).is_dir() else []:
                    names = sorted(p.name for p in batch_dir.iterdir()) if batch_dir.is_dir() else []
                    moved.append({"where": sub, "folder": self.rel(batch_dir), "files": names})
        entries = []
        incomplete = set(self.batch.unknown_records(self.root, request_id))
        for number, paths in sorted(items.items()):
            png = folder / f"r{number:03d}.png"
            record_path = folder / f"r{number:03d}.pixai.json"
            info = {}
            if record_path.is_file():
                try:
                    data = json.loads(record_path.read_text(encoding="utf-8"))
                    info = {k: data.get(k) for k in ("status", "startedAt", "finishedAt", "taskId", "error", "costMode")}
                except (OSError, json.JSONDecodeError):
                    info = {"status": "記録を読めません"}
            rel_png = self.rel(png) if png.is_file() else None
            entries.append({"n": number, "png": rel_png, "unknown": record_path in incomplete,
                            "adopted": bool(rel_png and rel_png == adopted), "files": sorted(p.name for p in paths),
                            "record": {k: v for k, v in info.items() if v is not None}})
        result["pixai"] = {"folder": self.rel(folder) if folder.is_dir() else None, "entries": entries, "moved": moved}
        return result

    def scan_unknown(self) -> list[dict]:
        found = []
        base = self.root / self.batch.CANDIDATES_DIR
        ids = set(self.batch.request_files(self.root)) | ({p.name for p in base.iterdir() if p.is_dir()} if base.is_dir() else set())
        for request_id in sorted(i for i in ids if self.batch.REQUEST_ID.fullmatch(i)):
            for e in self.records(request_id)["pixai"]["entries"]:
                if e["unknown"]:
                    found.append({"id": request_id, "n": e["n"], "status": e["record"].get("status"), "taskId": e["record"].get("taskId")})
        return found

    def move(self, body: dict) -> dict:
        # 生成の開始と整理を排他にし、実行中判定から移動完了までを一体にする。
        with self.lock:
            return self._move(body)

    def _move(self, body: dict) -> dict:
        if self.job and self.job["state"] == "running":
            raise ValueError("実行中の操作があります。終わってから整理してください。")
        request_id, action = str(body.get("id", "")), body.get("action")
        folder = self.folder(request_id)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        if action == "restore":
            source = self.inside(str(body.get("folder", "")))
            if not source.is_dir() or source.parent.parent != folder or source.parent.name != "discarded":
                raise ValueError("戻せるのは discarded/ の中のフォルダだけです")
            files = [p for p in source.iterdir() if p.name != "moved.json"]
            clash = [p.name for p in files if (folder / p.name).exists()]
            if clash:
                raise ValueError("同じ名前のファイルがあるため戻せません: " + ", ".join(clash))
            for path in files:
                shutil.move(str(path), str(folder / path.name))
            # 整理の記録を候補直下へ戻すと次回の復元で同名衝突するため、履歴へ保管する。
            record = source / "moved.json"
            if record.is_file():
                history = self.root / WORK / "history" / "records"
                history.mkdir(parents=True, exist_ok=True)
                shutil.move(str(record), str(history / f"{request_id}-{source.name}-{secrets.token_hex(4)}.json"))
            source.rmdir()
            self.note(f"戻す {self.rel(source)} → {self.rel(folder)}")
            return self.records(request_id)
        number = int(body.get("n", -1))
        files = [p for p in folder.glob(f"r{number:03d}.*") if p.is_file()] if folder.is_dir() else []
        if not files:
            raise ValueError("対象のファイルがありません")
        png = folder / f"r{number:03d}.png"
        if action == "move-unknown":
            if png.is_file():
                raise ValueError("画像があるため結果不明ではありません（不要なら「廃棄」を使います）")
            if not body.get("confirmed"):
                raise ValueError("PixAIから取得し直せないこと、PixAI側の生成とクレジットを確認したチェックが必要です")
            target = folder / "failed" / f"{stamp}-r{number:03d}-{secrets.token_hex(4)}"
        elif action == "discard":
            if not png.is_file():
                raise ValueError("画像がありません（結果不明の記録は failed/ へ移します）")
            adopted = self.batch.load_adopted(self.root)["adopted"].get(request_id, {}).get("path")
            if adopted == self.rel(png):
                raise ValueError("採用中の画像は廃棄できません。先に別の候補を採用してください")
            target = folder / "discarded" / f"{stamp}-r{number:03d}-{secrets.token_hex(4)}"
        else:
            raise ValueError("操作が不正です")
        target.mkdir(parents=True)
        for path in files:
            shutil.move(str(path), str(target / path.name))
        (target / "moved.json").write_text(json.dumps({"action": action, "request_id": request_id, "kind": "pixai", "number": number,
                                                        "files": [p.name for p in files], "moved_at": datetime.now().isoformat(timespec="seconds"),
                                                        "note": body.get("note", "")}, ensure_ascii=False, indent=2), encoding="utf-8")
        self.note(f"{action} {request_id} r{number:03d} → {self.rel(target)}")
        return self.records(request_id)

    def note(self, text: str) -> None:
        path = self.root / WORK / "logs" / "records.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"{datetime.now().isoformat(timespec='seconds')} {text}\n")


def quote(arg: str) -> str:
    return arg if re.fullmatch(r"[\w./,:=+-]+", arg) else "'" + arg.replace("'", "''") + "'"


def make_handler(project: Project, token: str, port: int):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 通常のアクセスログは出さない
            pass

        def send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def reply(self, data, status: int = 200) -> None:
            self.send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def allowed(self, query: dict) -> bool:
            if self.headers.get("Host") not in hosts:
                return False
            given = self.headers.get("X-Token") or (query.get("token") or [""])[0]
            return secrets.compare_digest(given, token)

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if not self.allowed(query):
                return self.send(403, "トークンが必要です。起動時に表示されたURLを開いてください。".encode("utf-8"), "text/plain; charset=utf-8")
            try:
                if url.path == "/":
                    return self.send(200, PAGE.replace("__TOKEN__", token).encode("utf-8"), "text/html; charset=utf-8")
                if url.path == "/api/state":
                    return self.reply(project.state())
                if url.path == "/api/records":
                    return self.reply(project.records(query["id"][0]))
                if url.path == "/api/records/scan":
                    return self.reply(project.scan_unknown())
                if url.path == "/api/job":
                    return self.reply(project.job_view())
                if url.path == "/api/request":
                    return self.reply(project.request(query["id"][0]))
                if url.path == "/api/page":
                    return self.reply(project.page(int(query["n"][0])))
                if url.path == "/file":
                    relative = query["path"][0]
                    path = project.inside(relative)
                    if not project.rel(path).startswith(SERVE_DIRS) or path.suffix.lower() not in IMAGE_TYPES or not path.is_file():
                        return self.send(404, b"not found", "text/plain")
                    return self.send(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
                return self.reply({"error": str(error)}, 400)
            self.send(404, b"not found", "text/plain")

        def do_POST(self):
            url = urlparse(self.path)
            if not self.allowed({}) or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.reply({"error": "拒否しました"}, 403)
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8") or "{}")
                if url.path == "/api/request":
                    project.save_request(body["id"], body["data"], bool(body.get("new")))
                    return self.reply({"ok": True})
                if url.path == "/api/page":
                    project.save_page(int(body["page"]), body.get("manifest"), body.get("typeset"))
                    return self.reply({"ok": True})
                if url.path == "/api/records":
                    return self.reply(project.move(body))
                if url.path == "/api/job/stop":
                    return self.reply(project.stop())
                if url.path == "/api/run":
                    return self.reply(project.start(body.get("action", ""), body))
            except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
                return self.reply({"error": str(error)}, 400)
            self.reply({"error": "not found"}, 404)

    return Handler


PAGE = r"""<!doctype html>
<html lang="ja">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PixAI制作パネル</title>
<style>
:root{--bg:#f4f6f8;--panel:#fff;--ink:#1b1e22;--sub:#626b75;--line:#d7dde3;--accent:#2563eb;--ok:#15803d;--warn:#b45309;--ng:#b91c1c}
@media (prefers-color-scheme:dark){:root{--bg:#14171a;--panel:#1d2125;--ink:#e6eaee;--sub:#9aa4ae;--line:#343b42;--accent:#60a5fa;--ok:#4ade80;--warn:#fbbf24;--ng:#f87171}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,"Yu Gothic UI",sans-serif}
header{display:flex;gap:1rem;align-items:center;padding:.5rem 1rem;border-bottom:1px solid var(--line);background:var(--panel);position:sticky;top:0;z-index:5}
header h1{font-size:15px;margin:0}nav{display:flex;gap:.25rem;flex-wrap:wrap}nav button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
button,select,input,textarea{font:inherit;color:inherit;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:.3rem .6rem}
button{cursor:pointer}button:hover{border-color:var(--accent)}button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
textarea{width:100%;font-family:ui-monospace,Consolas,monospace;font-size:12.5px}
main{display:grid;grid-template-columns:260px 1fr;gap:0;height:calc(100vh - 49px)}
aside{border-right:1px solid var(--line);overflow:auto;padding:.5rem;background:var(--panel)}
section.view{overflow:auto;padding:1rem}
.item{display:flex;gap:.5rem;align-items:center;padding:.25rem;border-radius:6px;cursor:pointer}.item:hover,.item.on{background:var(--bg)}
.item img{width:44px;height:44px;object-fit:cover;border-radius:4px;background:var(--line)}
.muted{color:var(--sub);font-size:12px}.row{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin:.4rem 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:.8rem;margin-bottom:1rem}
.card h3{margin:0 0 .5rem;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:.6rem}
.cand{border:2px solid transparent;border-radius:8px;padding:.3rem;background:var(--bg)}.cand.adopted{border-color:var(--ok)}
.cand img{width:100%;height:170px;object-fit:contain;cursor:zoom-in}
.batchgroup{border:1px dashed var(--line,#999);border-radius:8px;padding:.4rem;margin:.4rem 0}
.lora{border:1px dashed var(--line);border-radius:8px;padding:.4rem .5rem;margin:.3rem 0}
.lint{color:var(--warn)}.err{color:var(--ng)}.ok{color:var(--ok)}
pre.log{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:.6rem;max-height:50vh;overflow:auto;font-size:12px}
dialog{border:1px solid var(--line);border-radius:12px;background:var(--panel);color:var(--ink);max-width:640px}
#zoom{max-width:95vw;max-height:95vh;padding:0}#zoom img{max-width:94vw;max-height:90vh;display:block}
.pageimg{max-width:100%;max-height:75vh;border:1px solid var(--line);background:#fff}
label.chk{display:flex;gap:.4rem;align-items:flex-start;margin:.3rem 0}
#jobbar{margin-left:auto;font-size:12px}
.range input{width:4.5em}
@media (max-width:800px){main{grid-template-columns:1fr;height:auto}aside{max-height:40vh}}
</style>
<header>
  <h1 id="title">PixAI制作パネル</h1>
  <nav id="tabs">
    <button data-tab="panels" class="on">コマ（プロンプト・生成・採用）</button>
    <button data-tab="pages">ページ（構成・組版・ビルド）</button>
    <button data-tab="vars">変数（.env.pixai）</button>
    <button data-tab="preview">プレビュー</button>
    <button data-tab="log">実行ログ・接続</button>
  </nav>
  <span id="jobbar" class="muted"></span>
</header>
<main>
  <aside id="side"></aside>
  <section class="view" id="view"></section>
</main>
<dialog id="gen">
  <form method="dialog" id="genform">
    <h3 id="gentitle">生成</h3>
    <p class="muted">送信は作品の pixai_batch.py generate が行います。PixAIのクレジットの残高・消費はAPIで照会できないため、スクリプトは無料を判定しません。確認していない項目にチェックを付けないでください。</p>
    <div class="row">１コマの枚数：<select name="batch_size"><option value="auto">自動（作り直しのコマは4枚、初回は要求のとおり）</option><option value="4">4枚から選ぶ（1枚の約1.75倍のクレジット）</option><option value="1">1枚</option></select></div>
    <div class="row">seed：<select name="seed"><option value="auto">auto（初回は要求のseed、以後は乱数）</option><option value="request">request（要求のseedで固定）</option><option value="random">random</option></select></div>
    <div class="row">１回の上限件数（--max、タスク数）：<input type="number" name="max" min="1" max="1000" value="30" style="width:7em"><span class="muted">既定30件。１タスク4枚の要求は4枚分のクレジットを使う。送信間隔（既定3秒）と失敗時に止まる扱いは同じ</span></div>
    <label class="chk"><input type="checkbox" name="confirm_credits">今回の範囲（タスク数・枚数・モデル・mode・解像度・LoRA・追加機能）のクレジット消費を、利用者が明示的に許可したことを確認した（--confirm-credits）</label>
    <label class="chk"><input type="checkbox" name="allow_unverified">現行の公式文書にない項目（i2i・ControlNet・参照画像・v1のseed・除外など）を試すことを利用者が了承した（--allow-unverified）</label>
    <label class="chk"><input type="checkbox" name="accept_warnings">送信なし確認の警告を確認し、残す理由を記録した（--accept-warnings）</label>
    <div>確認した方法・日時・許可の範囲（--cost-note）<textarea name="cost_note" rows="2"></textarea></div>
    <p class="muted">チェックと上限件数は、このURL（トークン）で開いている間は記憶します。サーバーを起動し直して新しいURLで開くと消えます。</p>
    <div class="row"><button value="cancel">やめる</button><button value="dry">送信なしで確認</button><button value="exec" class="primary">生成する</button></div>
  </form>
</dialog>
<dialog id="zoom"><img alt=""></dialog>
<script>
const TOKEN = "__TOKEN__";
const $ = (s, el = document) => el.querySelector(s);
const h = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (k === 'class') e.className = v; else if (k.startsWith('on')) e[k] = v; else if (v !== undefined && v !== null) e.setAttribute(k, v); }
  for (const k of kids.flat()) if (k !== null && k !== undefined) e.append(k instanceof Node ? k : document.createTextNode(String(k))); return e; };
const img = (path, attrs = {}) => h('img', {src: '/file?path=' + encodeURIComponent(path) + '&token=' + TOKEN + '&t=' + Date.now(), loading: 'lazy', ...attrs});
const sel_ = (values, current, labels = {}) => { const s = h('select'); for (const v of values) { const o = h('option', {value: v}, labels[v] ? `${v}（${labels[v]}）` : (v === '' ? '（指定なし）' : v)); if (v === (current ?? '')) o.selected = true; s.append(o); } return s; };
async function api(path, body) {
  const opt = body === undefined ? {headers: {'X-Token': TOKEN}} : {method: 'POST', headers: {'X-Token': TOKEN, 'Content-Type': 'application/json'}, body: JSON.stringify(body)};
  const r = await fetch(path + (path.includes('?') ? '&' : '?') + 'token=' + TOKEN, opt); const j = await r.json();
  if (!r.ok || (j && j.error)) throw new Error(j && j.error || r.statusText); return j; }
function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
let S = null, tab = 'panels', sel = {panel: null, page: null}, lastJob = null, renderSeq = 0;

async function refresh() { S = await api('/api/state'); $('#title').textContent = 'PixAI制作パネル — ' + S.project; render(); }
// ページ範囲（指定ページから指定ページまで）
function pageNumbers() { return [...new Set(S.requests.map(r => r.page).filter(p => p !== null))].sort((a, b) => a - b); }
function rangeControl() { const nums = pageNumbers(); if (!nums.length) return null;
  const a = h('input', {type: 'number', min: nums[0], max: nums[nums.length - 1]}), b = a.cloneNode(); a.value = store('pxRangeFrom') || nums[0]; b.value = store('pxRangeTo') || nums[nums.length - 1];
  const pick = () => { const x = +a.value, y = +b.value; store('pxRangeFrom', a.value); store('pxRangeTo', b.value); const lo = Math.min(x, y), hi = Math.max(x, y);
    const pages = nums.filter(n => n >= lo && n <= hi); if (!pages.length) { alert('範囲に要求のあるページがありません。'); return null; } return {pages, label: `${lo}～${hi}ページ（${S.requests.filter(r => pages.includes(r.page)).length}件）`}; };
  return h('div', {class: 'row range'}, a, '～', b, 'ページ', h('button', {onclick: () => { const r = pick(); if (r) generateDialog({pages: r.pages}, r.label); }}, '範囲を生成…')); }
function zoom(path) { const d = $('#zoom'); $('img', d).src = '/file?path=' + encodeURIComponent(path) + '&token=' + TOKEN + '&t=' + Date.now(); d.showModal(); d.onclick = () => d.close(); }
async function run(action, body = {}) {
  try { const j = await api('/api/run', {action, ...body}); showJob(j); poll(); } catch (e) { alert(e.message); } }
function showJob(j) { lastJob = j; const step = j ? [...j.log.matchAll(/\[(\d+)\/(\d+)\] (\S+)/g)].pop() : null, task = j ? [...j.log.matchAll(/タスク (\d+): (\w+)/g)].pop() : null;
  $('#jobbar').textContent = j ? `${j.action}：${{running: '実行中…', done: '完了', failed: '失敗'}[j.state]}` + (step ? ` ${step[1]}/${step[2]}件目 ${step[3]}` : '') + (task && j.state === 'running' ? `（${task[2]}）` : '') + '（クリックでログ）' : '';
  $('#jobbar').className = j && j.state === 'failed' ? 'err' : j && j.state === 'done' ? 'ok' : 'muted'; if (tab === 'log') render(); }
async function poll() { const j = await api('/api/job'); showJob(j); if (j && j.state === 'running') setTimeout(poll, 1200); else { await refresh(); if (j && j.state === 'failed' && tab !== 'log') { if (confirm('失敗しました。ログを開きますか？')) { tab = 'log'; tabs(); render(); } } } }
// 生成画面のチェックと上限件数は、起動ごとのトークン単位で記憶する（新しいURLで開くと古いトークンの記憶は消す）。
const CHECKS = ['confirm_credits', 'allow_unverified', 'accept_warnings'], GEN_KEY = 'pxGenOptions:' + TOKEN;
try { for (let i = localStorage.length - 1; i >= 0; i--) { const k = localStorage.key(i); if (k.startsWith('pxGenOptions:') && k !== GEN_KEY) localStorage.removeItem(k); } } catch (e) {}
function generateDialog(target, label) {
  const d = $('#gen'), f = n => $('#genform').elements.namedItem(n); $('#gentitle').textContent = '生成：' + label;
  let saved = {}; try { saved = JSON.parse(store(GEN_KEY) || '{}'); } catch (e) {}
  f('cost_note').value = store('pxCostNote') || ''; CHECKS.forEach(n => f(n).checked = !!saved[n]); f('max').value = saved.max || 30;
  d.returnValue = ''; d.showModal();
  d.onclose = () => { const v = d.returnValue; if (v !== 'dry' && v !== 'exec') return;
    const options = {max: +f('max').value || 30}; CHECKS.forEach(n => options[n] = f(n).checked); store(GEN_KEY, JSON.stringify(options));
    const body = {...target, seed: f('seed').value, batch_size: f('batch_size').value, max: options.max};
    if (v === 'exec') { Object.assign(body, options, {execute: true, cost_note: f('cost_note').value}); store('pxCostNote', f('cost_note').value); }
    run('generate', body); }; }

// ---------------------------------------------------------------- コマ
function sidePanels() {
  const side = $('#side'); side.replaceChildren(h('div', {class: 'row'}, h('span', {class: 'muted'}, '要求（input/pixai/requests）'),
    h('button', {onclick: () => generateDialog({all: true}, '全ページ（' + S.requests.filter(r => r.page !== null).length + '件。上限件数を確認）')}, '全ページを生成…'), h('button', {onclick: () => confirm('全ページの各コマで、最新（最大番号）の候補を採用しますか？（候補のないコマがあると何も変更せずに止まります）') && run('adopt-latest', {all: true})}, '全ページで最新を採用')), rangeControl());
  const groups = {}; for (const r of S.requests) (groups[r.page ?? 'その他'] ||= []).push(r);
  for (const [g, list] of Object.entries(groups)) {
    side.append(h('div', {class: 'row'}, h('b', {}, g === 'その他' ? 'その他（人物試作など）' : g + 'ページ'),
      g !== 'その他' ? h('button', {onclick: () => generateDialog({pages: [+g]}, g + 'ページ全体')}, '生成') : null,
      g !== 'その他' ? h('button', {onclick: () => confirm(g + 'ページの各コマで最新の候補を採用しますか？') && run('adopt-latest', {pages: [+g]})}, '最新を採用') : null));
    for (const r of list) side.append(h('div', {class: 'item' + (sel.panel === r.id ? ' on' : ''), onclick: () => { sel.panel = r.id; render(); }},
      r.adopted ? img(r.adopted) : h('img', {alt: ''}), h('div', {}, h('div', {}, r.id + (r.api ? ` [${r.api}]` : '')), h('div', {class: 'muted'}, `候補${r.candidates.length}・${r.adopted ? '採用済み' : '未採用'}` + (r.unknown ? `・画像なしの記録${r.unknown}` : '')))));
  } }
function v2Editor(raw) { const O = S.options, B = raw.body, kind = O.model_types[B.modelVersionId] || raw.model_type;
  const prompt = h('textarea', {rows: 5}); prompt.value = B.prompt || '';
  const negative = h('textarea', {rows: 2}); negative.value = B.negativePrompt || '';
  const model = h('input', {style: 'width:16em'}); model.value = B.modelVersionId || '';
  const aspect = sel_(O.aspects, B.aspectRatio), size = sel_(O.sizes, B.size || '1k'), mode = sel_(['', ...O.modes], B.mode);
  const styleKind = sel_(['', 'preset', 'custom'], B.style?.type, {preset: 'プリセット', custom: '自由記述'}), styleKey = sel_(Object.keys(O.styles), B.style?.key, O.styles);
  const styleCustom = h('input', {style: 'width:28em'}); styleCustom.value = B.style?.custom || '';
  const seed = h('input', {type: 'number', style: 'width:10em'}); seed.value = B.seed ?? '';
  const batch = sel_(['1', '4'], String(B.batchSize || 1)), helper = sel_(['disable', 'enable'], B.promptHelper || 'disable', {disable: '書き換えない', enable: '書き換える'});
  const sampling = h('textarea', {rows: 1}); sampling.value = B.sampling ? JSON.stringify(B.sampling) : '';
  const size_ = h('span', {class: 'muted'}); const showSize = () => { const r = O.resolutions[aspect.value]; size_.textContent = r ? `→ ${r[O.sizes.indexOf(size.value)].join('×')}px` : ''; }; aspect.onchange = size.onchange = showSize; showSize();
  const loraBox = h('div'), loras = [];
  function addLora(item = {}) { if (loras.length >= 5) return alert('LoRAは最大5件です（公式）。');
    const id = h('input', {placeholder: 'バージョンID または ${PIXAI_LORA_…}', style: 'width:20em'}), w = h('input', {type: 'number', step: '0.05', min: 0, max: 1, style: 'width:6em'}), t = h('input', {placeholder: 'トリガー語（省略可）', style: 'width:18em'});
    id.value = item.modelId || ''; w.value = item.weight ?? 1; t.value = item.triggerWords || '';
    const row = {id, w, t}; row.el = h('div', {class: 'lora row'}, 'LoRA', id, '重み', w, t, h('button', {onclick: () => { loras.splice(loras.indexOf(row), 1); row.el.remove(); }}, '削除'));
    loras.push(row); loraBox.append(row.el); }
  (B.loras || []).forEach(addLora);
  function collect() { const d = JSON.parse(JSON.stringify(raw)), b = d.body;
    b.prompt = prompt.value; if (negative.value.trim()) b.negativePrompt = negative.value; else delete b.negativePrompt;
    b.modelVersionId = model.value.trim(); b.aspectRatio = aspect.value; b.size = size.value; if (mode.value) b.mode = mode.value; else delete b.mode;
    if (styleKind.value === 'preset') b.style = {type: 'preset', key: styleKey.value}; else if (styleKind.value === 'custom') b.style = {type: 'custom', custom: styleCustom.value}; else delete b.style;
    if (seed.value !== '') b.seed = +seed.value; else delete b.seed; b.batchSize = +batch.value; b.promptHelper = helper.value;
    const L = loras.map(r => { const x = {modelId: r.id.value.trim(), weight: +r.w.value}; if (r.t.value.trim()) x.triggerWords = r.t.value.trim(); return x; }).filter(x => x.modelId);
    if (L.length) b.loras = L; else delete b.loras;
    if (sampling.value.trim()) b.sampling = JSON.parse(sampling.value); else delete b.sampling; return d; }
  const el = h('div', {},
    h('div', {class: 'muted'}, 'プロンプト（prompt）。${変数名} は .env.pixai の値に展開されます。丸括弧の強調 (word:1.2) に対応し、角括弧・波括弧は使えません。'), prompt,
    h('div', {class: 'muted'}, '除外（negativePrompt）'), negative,
    h('div', {class: 'row'}, 'モデル（modelVersionId）', model, h('span', {class: 'muted'}, (O.models[B.modelVersionId] || '既知でないモデル') + (kind ? '' : '・種類不明'))),
    h('div', {class: 'row'}, '縦横比', aspect, '解像度', size, size_, kind === 'sdxl' ? null : ['mode', mode]),
    kind === 'sdxl' ? h('div', {class: 'muted'}, 'mode・画風プリセットはTsubaki系だけで使えます。') : h('div', {class: 'row'}, '画風', styleKind, styleKey, styleCustom),
    h('div', {class: 'muted'}, 'LoRA（最大5件。IDはモデルページのURLの最後の数字。重み0〜1）'), loraBox, h('button', {onclick: () => addLora()}, 'LoRAを追加'),
    h('div', {class: 'row'}, 'seed', seed, '枚数', batch, 'promptHelper', helper),
    kind === 'dit' ? null : h('div', {}, h('div', {class: 'muted'}, 'sampling（SDXLのみ。例 {"method": "DPM++ 2M Karras", "steps": 25, "cfgScale": 6}。空で指定なし）'), sampling));
  return {el, collect}; }
function v1Editor(raw) { const P = raw.parameters, prompts = h('textarea', {rows: 5}); prompts.value = P.prompts || '';
  const rest = {...P}; delete rest.prompts; const json = h('textarea', {rows: 14}); json.value = JSON.stringify(rest, null, 2);
  const el = h('div', {}, h('div', {class: 'muted'}, 'v1 の要求（i2i・ControlNet・参照画像・Hires・ADetailer）。プロンプト（prompts）。${変数名} は .env.pixai の値に展開されます。'), prompts,
    h('div', {class: 'muted'}, 'その他の parameters（JSON）。作品内の画像は mediaFile・controlNets[].mediaFile・ipAdapter.referenceFiles に相対パスで書くと、送信時にアップロードされます。'), json);
  return {el, collect: () => { const d = JSON.parse(JSON.stringify(raw)); d.parameters = {prompts: prompts.value, ...JSON.parse(json.value)}; return d; }}; }
async function viewPanel() {
  const v = $('#view'); if (!sel.panel) { v.replaceChildren(h('p', {class: 'muted'}, '左の一覧から要求を選んでください。')); return; }
  const seq = renderSeq, R = await api('/api/request?id=' + encodeURIComponent(sel.panel)); if (seq !== renderSeq || tab !== 'panels') return; const raw = R.raw;
  const info = S.requests.find(r => r.id === sel.panel) || {candidates: []};
  const editor = raw.api === 'v1' ? v1Editor(raw) : raw.api === 'v2' ? v2Editor(raw) : null;
  async function save(id = sel.panel, isNew = false) { try { await api('/api/request', {id, data: editor.collect(), new: isNew}); sel.panel = id; await refresh(); return true; } catch (e) { alert(e.message); return false; } }
  const varsInfo = S.variables.filter(x => x.name).map(x => x.name);
  const shown = R.resolved ? (R.resolved.api === 'v1' ? R.resolved.parameters : R.resolved.body) : null;
  const resolved = h('pre', {class: 'log'}, shown ? JSON.stringify(shown, null, 2) : '展開できません');
  const card = p => { const n = +p.match(/r(\d+)\.png$/)[1];
    return h('div', {class: 'cand' + (info.adopted === p ? ' adopted' : '')}, img(p, {onclick: () => zoom(p)}),
      h('div', {class: 'row'}, 'r' + String(n).padStart(3, '0'), info.adopted === p ? h('span', {class: 'ok'}, '採用中') : h('button', {onclick: () => run('adopt', {ids: [sel.panel], candidate: n})}, '採用'),
        info.adopted === p ? null : h('button', {title: 'discarded/ へ移す（削除しない）', onclick: () => discard(sel.panel, n)}, '廃棄'))); };
  // 同じ生成（batchSize 4 の１タスク）の候補はまとめて並べ、その中から選べるようにする。
  const num = p => +p.match(/r(\d+)\.png$/)[1], byNum = new Map(info.candidates.map(p => [num(p), p])), used = new Set(), groups = [];
  for (const nums of (info.batches || []).slice().sort((a, b) => b[0] - a[0])) { const ps = nums.map(n => byNum.get(n)).filter(Boolean);
    if (ps.length > 1) { ps.forEach(p => used.add(p)); groups.push({first: nums[0], ps}); } }
  for (const p of info.candidates) if (!used.has(p)) groups.push({first: num(p), ps: [p]});
  groups.sort((a, b) => b.first - a.first);
  const cands = h('div', {}, ...groups.map(g => g.ps.length > 1
    ? h('div', {class: 'batchgroup'}, h('div', {class: 'muted'}, `同じ生成の${g.ps.length}枚（r${String(num(g.ps[0])).padStart(3, '0')}～r${String(num(g.ps[g.ps.length - 1])).padStart(3, '0')}）から選ぶ`), h('div', {class: 'grid'}, ...g.ps.map(card)))
    : h('div', {class: 'grid'}, card(g.ps[0]))));
  v.replaceChildren(
    h('div', {class: 'card'}, h('h3', {}, sel.panel + ' の要求（' + (raw.api || '形式不明') + '）'),
      editor ? editor.el : h('p', {class: 'err'}, 'api が v2・v1 ではありません。JSONを直接直してください。'),
      h('div', {class: 'muted'}, '使える変数：' + (varsInfo.join('、') || 'なし')),
      R.lint.length ? h('div', {class: 'lint'}, '点検の警告：' + R.lint.join(' / ')) : h('div', {class: 'muted'}, '点検の警告なし（語の検出のみ。内容の照合は別に行う）'),
      info.unknown ? h('div', {class: 'err'}, `画像のない実行記録が${info.unknown}件あります。`, h('button', {onclick: () => run('fetch', {ids: [sel.panel]})}, 'PixAIから取得し直す（fetch）')) : null,
      editor ? h('div', {class: 'row'}, h('button', {class: 'primary', onclick: () => save()}, '保存'),
        h('button', {onclick: async () => { if (await save()) generateDialog({ids: [sel.panel]}, sel.panel); }}, '保存して生成…'),
        h('button', {onclick: () => { const id = prompt('差し替え案のID（例 ' + sel.panel + 'b）', sel.panel + 'b'); if (id) save(id, true); }}, '差し替え案として複製')) : null),
    h('div', {class: 'card'}, h('h3', {}, '候補（新しい順）'), info.candidates.length ? cands : h('p', {class: 'muted'}, 'まだ候補がありません。')),
    h('details', {class: 'card'}, h('summary', {}, '変数を展開した送信内容（保存済みの版）'), resolved)); }

// ---------------------------------------------------------------- ページ
function sidePages() { const side = $('#side');
  side.replaceChildren(h('div', {class: 'row'}, h('b', {}, 'ページ'), h('button', {onclick: () => confirm('全ページのPNGを組み直しますか？') && run('build', {all: true})}, '全ページPNG'),
    h('button', {onclick: () => confirm('全ページのPSDを作りますか？（同じ版のPNGも作られます。PNG確認後・依頼がある場合）') && run('build', {all: true, write_psd: true})}, '全ページPSD'), h('button', {onclick: () => confirm('全ページの各コマで、最新（最大番号）の候補を採用しますか？（候補のないコマがあると何も変更せずに止まります）') && run('adopt-latest', {all: true})}, '全ページで最新を採用')), rangeControl());
  for (const p of S.pages) side.append(h('div', {class: 'item' + (sel.page === p.page ? ' on' : ''), onclick: () => { sel.page = p.page; render(); }},
    p.latest?.display ? img(p.latest.display) : h('img', {alt: ''}), h('div', {}, h('div', {}, p.page + 'ページ'), h('div', {class: 'muted'}, p.latest ? '最新 ' + p.latest.version : '未ビルド')))); }
async function viewPage() { const v = $('#view'); if (!sel.page) { v.replaceChildren(h('p', {class: 'muted'}, '左の一覧からページを選んでください。')); return; }
  const seq = renderSeq, D = await api('/api/page?n=' + sel.page); if (seq !== renderSeq || tab !== 'pages') return; const info = S.pages.find(p => p.page === sel.page), L = info.latest;
  const man = h('textarea', {rows: 14}), ts = h('textarea', {rows: 18}); man.value = JSON.stringify(D.manifest, null, 2); ts.value = D.typeset ? JSON.stringify(D.typeset, null, 2) : '';
  const rows = (D.manifest?.panels || []).map(p => { const f = (k, d, step) => { const e = h('input', {type: 'number', step, style: 'width:6em'}); e.value = k === 'fx' ? (p.focus?.[0] ?? .5) : k === 'fy' ? (p.focus?.[1] ?? .5) : (p[k] ?? d); e.dataset.k = k; return e; };
    const tr = h('tr', {}, h('td', {}, 'コマ' + p.panel), h('td', {}, p.request || p.source || ''), h('td', {}, f('fx', .5, .01)), h('td', {}, f('fy', .5, .01)), h('td', {}, f('zoom', 1, .05)), h('td', {}, f('rotation', 0, 1))); tr.dataset.panel = p.panel; return tr; });
  function applyRows() { const m = JSON.parse(man.value); for (const tr of rows) { const p = m.panels.find(x => x.panel === +tr.dataset.panel); const g = k => +tr.querySelector(`[data-k=${k}]`).value;
      p.focus = [g('fx'), g('fy')]; if (g('zoom') !== 1) p.zoom = g('zoom'); else delete p.zoom; if (g('rotation')) p.rotation = g('rotation'); else delete p.rotation; } man.value = JSON.stringify(m, null, 2); }
  async function save(build) { try { applyRows(); await api('/api/page', {page: sel.page, manifest: JSON.parse(man.value), typeset: ts.value.trim() ? JSON.parse(ts.value) : null});
      if (build) run('build', {pages: [sel.page], write_psd: build === 'psd'}); else refresh(); } catch (e) { alert(e.message); } }
  v.replaceChildren(
    h('div', {class: 'card'}, h('h3', {}, sel.page + 'ページ ' + (L ? '（最新 ' + L.version + '）' : '（未ビルド）')),
      h('div', {class: 'row'}, h('button', {class: 'primary', onclick: () => save('png')}, '保存してPNGをビルド'),
        h('button', {onclick: () => confirm('PSDを作りますか？（同じ版のPNGも作られます。PNG確認後・依頼がある場合）') && save('psd')}, '保存してPSDをビルド'),
        h('button', {onclick: () => generateDialog({pages: [sel.page]}, sel.page + 'ページ全体')}, 'このページを生成…'),
        h('button', {onclick: () => confirm('各コマの最新候補を採用しますか？') && run('adopt-latest', {pages: [sel.page]})}, '最新を採用')),
      h('div', {class: 'muted'}, 'ページ構成の request は input/pixai/adopted.json の採用画像を使います。他の手段の画像を置くコマは source に画像のパスを書きます。'),
      L ? h('div', {class: 'muted'}, `組版の点検：エラー${L.summary?.error ?? '?'}・警告${L.summary?.warning ?? '?'}` + (L.notes && Object.keys(L.notes).length ? '／配置の注記：' + JSON.stringify(L.notes) : '')) : null,
      L ? h('div', {class: 'row'}, L.display ? img(L.display, {class: 'pageimg', onclick: () => zoom(L.png)}) : null, L.check ? img(L.check, {class: 'pageimg', style: 'max-width:45%', onclick: () => zoom(L.check)}) : null) : null),
    h('div', {class: 'card'}, h('h3', {}, 'コマ内の見せ方（focus＝画像内でコマの中心に置く点、zoom、rotation）'),
      h('table', {}, h('tr', {}, ...['コマ', '画像', 'focus x', 'focus y', 'zoom', 'rotation'].map(t => h('th', {}, t))), ...rows)),
    h('div', {class: 'card'}, h('h3', {}, 'ページ構成 JSON（input/pages）'), man, h('h3', {}, '組版指定 JSON（' + (D.typeset_path || 'なし') + '）'),
      h('div', {class: 'muted'}, 'フキダシ（balloons）の center・tail・text・size、文字を置かない範囲（keep_out）、画中の文字（inserts）。座標はページのpx。'), ts,
      h('div', {class: 'row'}, h('button', {onclick: () => save(false)}, '保存のみ'), h('button', {class: 'primary', onclick: () => save('png')}, '保存してPNGをビルド'), h('button', {onclick: () => confirm('PSDを作りますか？') && save('psd')}, '保存してPSDをビルド')))); }

// ---------------------------------------------------------------- 変数
// 変数タブの案内（docs/pixai-prompts/README.md の Step 0 の依頼文例と同じ）。
const VARS_GUIDE = 'このページでキャラの見た目や衣装、背景のプロンプトを一括で調整できるようにするには、作品フォルダでAIエージェントに次のように依頼してください。', VARS_EXAMPLE = '「既存のPixAIの要求をもとに、キャラクター・絵柄・背景を .env.pixai から自分で編集できるように準備してください。キャラクターLoRAを使う場合はそのIDも変数にしてください。今回は画像の生成は行わず、準備だけお願いします。」';
function viewVars() { $('#side').replaceChildren(h('p', {class: 'muted'}, '.env.pixai のキャラクター・絵柄・背景・LoRAの変数を編集します（APIキー・URLの共通設定は .env）。APIキーは表示・変更しません。'),
    h('div', {class: 'card'}, h('p', {}, VARS_GUIDE), h('p', {class: 'muted'}, VARS_EXAMPLE)));
  const v = $('#view'); const list = S.variables;
  const blocks = list.map(x => { if (x.error) return h('p', {class: 'err'}, x.error); const t = h('textarea', {rows: 3}); t.value = x.value;
    const used = S.requests.filter(r => r.vars.includes(x.name)).map(r => r.id);
    return h('div', {class: 'card'}, h('h3', {}, x.name + '（' + x.source + '）'), t, h('div', {class: 'muted'}, '使う要求：' + (used.join(', ') || 'なし')),
      h('div', {class: 'row'}, h('button', {class: 'primary', onclick: () => run('env-set', {name: x.name, value: t.value.replace(/\s*\n\s*/g, ' ')})}, '保存（env-set）'),
        used.length ? h('button', {onclick: () => generateDialog({ids: used}, x.name + ' を使う' + used.length + 'コマ')}, 'この変数を使うコマを生成…') : null,
        h('button', {onclick: () => run('templatize', {name: x.name, dry_run: true})}, '置き換え箇所を確認'),
        h('button', {onclick: () => confirm('要求JSON内の同じ文を ${' + x.name + '} に置き換えますか？') && run('templatize', {name: x.name})}, '要求へ取り込む（templatize）'))); });
  const name = h('input', {placeholder: 'PIXAI_CHAR_NAME', style: 'width:22em'}), val = h('textarea', {rows: 2});
  const empty = !list.some(x => !x.error) ? h('div', {class: 'err', style: 'font-weight:bold'}, h('p', {}, VARS_GUIDE), h('p', {}, VARS_EXAMPLE)) : null;
  v.replaceChildren(...blocks, ...(empty ? [empty] : []), h('div', {class: 'card'}, h('h3', {}, '変数を追加'), h('div', {class: 'muted'}, 'PIXAI_CHAR_・PIXAI_STYLE_・PIXAI_BACKGROUND_・PIXAI_LORA_ で始まる半角英大文字・数字・_。値は１行。PIXAI_LORA_ の値はLoRAのバージョンID（数字）。追加後に「要求へ取り込む」で既存の要求の同じ文を変数参照にできます。'),
    name, val, h('div', {class: 'row'}, h('button', {class: 'primary', onclick: () => run('env-set', {name: name.value.trim(), value: val.value.replace(/\s*\n\s*/g, ' ')})}, '追加（env-set）')))); }

// ---------------------------------------------------------------- プレビュー
function viewPreview() { $('#side').replaceChildren(h('p', {class: 'muted'}, '各ページの最新ビルド（掲載幅の確認用画像）。← で次のページ（右から左へ読む）。'));
  const pages = S.pages.filter(p => p.latest?.display); let i = 0; const v = $('#view');
  if (!pages.length) { v.replaceChildren(h('p', {class: 'muted'}, 'ビルド済みのページがありません。')); return; }
  const im = h('img', {class: 'pageimg', style: 'max-height:82vh'}), info = h('span');
  const show = k => { i = Math.max(0, Math.min(pages.length - 1, k)); const p = pages[i]; im.src = '/file?path=' + encodeURIComponent(p.latest.display) + '&token=' + TOKEN; im.onclick = () => zoom(p.latest.png); info.textContent = `${p.page}ページ（${p.latest.version}） ${i + 1}/${pages.length}`; };
  v.replaceChildren(h('div', {class: 'row'}, h('button', {onclick: () => show(i + 1)}, '← 次'), info, h('button', {onclick: () => show(i - 1)}, '前 →')), im); show(0);
  document.onkeydown = e => { if (tab !== 'preview') return; if (e.key === 'ArrowLeft') show(i + 1); if (e.key === 'ArrowRight') show(i - 1); }; }

// ---------------------------------------------------------------- ログ
async function discard(id, n) { if (!confirm(`${id} の r${String(n).padStart(3, '0')} を discarded/ へ移しますか？（削除はしません。整理の欄から戻せます）`)) return;
  try { await api('/api/records', {action: 'discard', id, n}); await refresh(); } catch (e) { alert(e.message); } }
// 実行結果の整理：記録をサブフォルダ（failed/・discarded/）へ移す。ファイルは削除しない。
function recordsPane() { const id = h('input', {placeholder: '要求ID（例 p07-03）', list: 'reqids', style: 'width:12em'}), out = h('div');
  id.value = store('pxRecordsId') || '';
  const list = h('datalist', {id: 'reqids'}, ...S.requests.map(r => h('option', {value: r.id})));
  async function show() { const v = id.value.trim(); if (!v) return; store('pxRecordsId', v);
    try { draw(await api('/api/records?id=' + encodeURIComponent(v))); } catch (e) { out.replaceChildren(h('p', {class: 'err'}, e.message)); } }
  async function act(body) { try { draw(await api('/api/records', body)); refresh(); } catch (e) { alert(e.message); } }
  function draw(D) { const K = D.pixai, kids = [h('div', {class: 'muted'}, `${D.id}：${D.exists ? '要求あり' : '要求JSONなし'}／採用中 ${D.adopted || 'なし'}`)];
    if (!K.entries.length && !K.moved.length) kids.push(h('div', {class: 'muted'}, 'PixAIの候補：なし'));
    else kids.push(h('h3', {}, 'PixAIの候補（' + (K.folder || '') + '）'));
    for (const e of K.entries) { const name = 'r' + String(e.n).padStart(3, '0'), rec = e.record;
      if (e.unknown) { const ok = h('input', {type: 'checkbox'});
        kids.push(h('div', {class: 'card'}, h('b', {class: 'err'}, name + '：画像なし（完了待ちの途中・送信の結果が不明）'),
          h('div', {class: 'muted'}, `状態：${rec.status || '記録なし'}／開始：${rec.startedAt || '?'}` + (rec.taskId ? `／taskId：${rec.taskId}` : '／taskIdなし') + (rec.error ? `／${rec.error}` : '') + `／ファイル：${e.files.join(', ')}`),
          rec.taskId ? h('div', {class: 'row'}, h('button', {class: 'primary', onclick: () => run('fetch', {ids: [D.id]})}, 'PixAIから取得し直す（fetch）'), h('span', {class: 'muted'}, 'タスクの状態を照会し、完了していれば画像を保存します（生成は再送しません。画像は無期限には保存されません）')) : null,
          h('div', {class: 'muted'}, '取得できない場合は、PixAIの画面で生成とクレジットの消費を確認してください。画像を手で保存した場合は ' + K.folder + '/' + name + '.png として置けば結果として扱えます（移す必要はありません）。'),
          h('label', {class: 'chk'}, ok, '取得し直せないこと、PixAI側の生成とクレジットを確認した（画像はできていない、または不要）'),
          h('button', {onclick: () => act({action: 'move-unknown', id: D.id, n: e.n, confirmed: ok.checked})}, 'failed/ へ移す')));
      } else if (e.png) kids.push(h('div', {class: 'row'}, img(e.png, {style: 'width:64px;height:64px;object-fit:cover', onclick: () => zoom(e.png)}), name,
          e.adopted ? h('span', {class: 'ok'}, '採用中') : h('button', {onclick: () => confirm(name + ' を discarded/ へ移しますか？') && act({action: 'discard', id: D.id, n: e.n})}, '廃棄'),
          h('span', {class: 'muted'}, rec.status || ''))); }
    for (const m of K.moved) kids.push(h('div', {class: 'row muted'}, (m.where === 'failed' ? '画像なしとして移動済み：' : '廃棄済み：') + m.folder + '（' + m.files.filter(f => f !== 'moved.json').join(', ') + '）',
      m.where === 'discarded' ? h('button', {onclick: () => act({action: 'restore', id: D.id, folder: m.folder})}, '戻す') : null));
    out.replaceChildren(...kids); }
  async function scan() { try { const L = await api('/api/records/scan');
      out.replaceChildren(L.length ? h('div', {}, h('b', {}, '画像のない実行記録'), ...L.map(x => h('div', {class: 'row'}, `${x.id}（r${String(x.n).padStart(3, '0')}：${x.status || '?'}${x.taskId ? '・taskIdあり' : ''}）`,
        h('button', {onclick: () => { id.value = x.id; show(); }}, '開く')))) : h('p', {class: 'ok'}, '画像のない実行記録はありません。')); } catch (e) { alert(e.message); } }
  if (id.value) setTimeout(show, 0);
  return h('div', {class: 'card', id: 'recpane'}, h('h3', {}, '実行結果の整理'),
    h('div', {class: 'muted'}, '「画像のない実行記録があります」で止まったときや、不要な候補を片づけるときに使います。taskId があればまずPixAIから取得し直します。ファイルは削除せず、同じフォルダの failed/・discarded/ へ移します（操作は output/webui-pixai/logs/records.log に記録）。'),
    h('div', {class: 'row'}, id, list, h('button', {class: 'primary', onclick: show}, '点検'), h('button', {onclick: scan}, '全コマから画像なしの記録を探す')), out); }
function viewLog() { const before = $('#view pre.output'), kept = before ? before.scrollTop : 0, auto = store('pxLogAutoScroll') !== '0';
  const follow = h('input', {type: 'checkbox'}); follow.checked = auto;
  follow.onchange = () => { store('pxLogAutoScroll', follow.checked ? '1' : '0'); if (follow.checked) toBottom(); };
  const toBottom = () => { const out = $('#view pre.output'); if (out) out.scrollTop = out.scrollHeight; };
  $('#side').replaceChildren(h('p', {class: 'muted'}, '実行したコマンドと出力。ログは output/webui-pixai/logs/ にも保存されます。'),
    h('div', {class: 'card'}, h('h3', {}, 'APIの接続'), h('div', {class: 'row'}, h('button', {onclick: () => run('key-status')}, 'キーの読込確認（通信なし）')),
      h('div', {class: 'row'}, h('button', {onclick: () => confirm('接続確認のAPIを1回呼びます（画像生成・クレジット消費なし）。よろしいですか？') && run('status')}, '接続確認（status）')),
      h('div', {class: 'muted'}, 'クレジットの残高・消費はAPIで照会できません。PixAIの画面で確認してください。'), h('div', {class: 'row'}, h('button', {onclick: () => run('list')}, '一覧（list）'))),
    lastJob && lastJob.state === 'running' ? h('div', {class: 'card'}, h('h3', {}, '実行中の操作'), h('div', {class: 'muted'}, '止まらない場合だけ使います。完了待ちの途中で中止すると、作成済みのタスクはPixAI側で続き、記録は画像なしで残ります（右の「実行結果の整理」で取得し直します）。'),
      h('button', {onclick: async () => { if (confirm('実行中の操作を中止しますか？')) try { showJob(await api('/api/job/stop', {})); } catch (e) { alert(e.message); } }}, '中止')) : null);
  // 整理の欄は入力を保つため、ログの更新では作り直さない
  if (!$('#view #recpane')) $('#view').replaceChildren(h('div', {id: 'jobpane'}), recordsPane());
  const j = lastJob; $('#jobpane').replaceChildren(j ? h('div', {class: 'card'}, h('h3', {}, `${j.action}（${j.started}）：${{running: '実行中', done: '完了', failed: '失敗'}[j.state]}${j.code !== null ? '・終了コード ' + j.code : ''}`),
    h('div', {class: 'muted'}, '同じ操作のコマンド（作品ルートで実行）：'), h('pre', {class: 'log'}, j.command),
    h('label', {class: 'chk'}, follow, '自動スクロール（ONの間は更新のたびに出力の一番下を表示）'), h('pre', {class: 'log output'}, j.log || '（出力なし）')) : h('p', {class: 'muted'}, 'まだ実行していません。'));
  if (auto) toBottom(); else { const out = $('#view pre.output'); if (out) out.scrollTop = kept; } }

function tabs() { document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === tab)); }
function render() { if (!S) return; tabs(); renderSeq++;
  if (tab === 'panels') { sidePanels(); viewPanel(); } else if (tab === 'pages') { sidePages(); viewPage(); } else if (tab === 'vars') viewVars(); else if (tab === 'preview') viewPreview(); else viewLog(); }
document.querySelectorAll('#tabs button').forEach(b => b.onclick = () => { tab = b.dataset.tab; render(); });
$('#jobbar').style.cursor = 'pointer'; $('#jobbar').onclick = () => { tab = 'log'; render(); };
refresh().then(() => api('/api/job')).then(j => { showJob(j); if (j && j.state === 'running') poll(); }).catch(e => alert(e.message));
</script>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="作品ルート（既定は現在のフォルダから上へ探す）")
    parser.add_argument("--port", type=int, default=8775, help="NovelAIのWebUI（既定8765）と同時に使えるよう、既定は8775")
    args = parser.parse_args()
    root = find_root(Path(args.root).resolve() if args.root else Path.cwd().resolve())
    project = Project(root)
    token = secrets.token_urlsafe(16)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(project, token, args.port))
    print(f"作品: {root}")
    print(f"ブラウザーで開いてください: http://127.0.0.1:{args.port}/?token={token}")
    print("終了は Ctrl+C。このURLは起動ごとに変わります。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
