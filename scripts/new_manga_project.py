"""PowerShellを必要としない作品作成。Python 3.10以上・標準ライブラリのみ。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata

ROOT = Path(__file__).absolute().parent.parent
THEMES = 'tsukkomi|allure|stature|horror|conflict|grief|romance|trust|awkwardness|urgency|revelation|payoff|endearment|bargaining|reconciliation'
KNOWLEDGE = re.compile(r'docs/knowledge/supervision/(?:(?:README|routing|sources)\.md|gag/(?:README|mechanisms|design-and-review|know-how)\.md|(?:' + THEMES + r')/README\.md)')
PROJECT_SCRIPTS = ('Resolve-ReviewProfile.ps1', 'resolve_review_profile.py', 'Resolve-ReviewProfile.sh',
                   'Initialize-OptionalSkills.ps1', 'initialize_optional_skills.py', 'Initialize-OptionalSkills.sh',
                   'validate_panel_plan.py', 'prepare_page_layout.py', 'process_checker.py')


def no_links(path: Path) -> None:
    """存在しない末尾も許容し、親を含むリンクを拒否する。"""
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ValueError(f'リンクを経由するパスは使用できません: {item}')


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_files(root: Path, skip: tuple[str, ...] = ()):
    for item in sorted(root.iterdir()):
        no_links(item)
        if item.is_dir():
            if item.name not in ('__pycache__', *skip):
                yield from package_files(item)
        elif item.is_file():
            yield item
        else:
            raise ValueError(f'通常ファイル以外は配布できません: {item}')


def collect_package(root: Path) -> dict[str, Path]:
    no_links(root)
    template = root / 'templates/manga-project'
    no_links(template / 'config/process-requirements.json')
    process = read_json(template / 'config/process-requirements.json')
    if not isinstance(process, dict) or set(process) != {'schemaVersion', 'requirements'} or type(process['schemaVersion']) is not int or process['schemaVersion'] != 1 or process['requirements'] != []:
        raise ValueError('配布原本のプロセス必須事項は空にしてください。')
    no_links(template / 'AGENTS.md')
    if '<!-- process-checker:strong:start -->' in (template / 'AGENTS.md').read_text(encoding='utf-8-sig'):
        raise ValueError('雛形のAGENTS.mdへ個人の強い指示を含めないでください。')
    package = {}

    def add(source: Path, destination: str):
        no_links(source)
        if not source.is_file():
            raise ValueError(f'配布元のファイルがありません: {source}')
        if destination.casefold() in {name.casefold() for name in package}:
            raise ValueError(f'配布先が重複しています: {destination}')
        package[destination] = source

    mappings = (
        ('templates/manga-project', '', {'.md', '.json', '.py'}, {'.gitignore', '.env.example', 'requirements-composition.txt'}, ('agent-modes',)),
        ('docs/knowledge', 'docs/knowledge', {'.md'}, set(), ('supervision',)),
        ('skills', '.agents/skills', {'.md'}, set(), ()),
        ('scripts/video', 'scripts/video', {'.py'}, set(), ()),
    )
    for source_relative, destination, extensions, special, skip in mappings:
        source_root = root / source_relative
        no_links(source_root)
        files = list(package_files(source_root, skip))
        if not files:
            raise ValueError(f'配布元のフォルダが空です: {source_root}')
        for file in files:
            relative = file.relative_to(source_root).as_posix()
            if any(part in {'.secrets', '.git', '.work', '.codex'} for part in file.relative_to(source_root).parts) or (file.name.startswith('.env') and file.name != '.env.example') or re.search(r'secret|credential|api[-_]?key|token', file.name, re.I):
                raise ValueError(f'秘密情報を含む可能性のある配布名です: {relative}')
            asset = source_relative == 'templates/manga-project' and (
                relative in {'templates/panel-templates/index.html', 'templates/onomatopoeia/index.html'}
                or re.fullmatch(r'templates/panel-templates/(?:svg|guides)/[^/]+\.svg', relative)
                or re.fullmatch(r'templates/panel-templates/(?:png|previews)/[^/]+\.png', relative)
                or re.fullmatch(r'templates/onomatopoeia/images/[^/]+\.webp', relative))
            if file.suffix.lower() not in extensions and file.name not in special and not asset:
                raise ValueError(f'許可されていない配布形式です: {relative}')
            add(file, f'{destination}/{relative}' if destination else relative)
    manifest_path = root / 'docs/knowledge/supervision/distribution.json'
    no_links(manifest_path)
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or type(manifest.get('schemaVersion')) is not int or manifest['schemaVersion'] != 1 or not isinstance(manifest.get('files'), list) or not manifest['files']:
        raise ValueError('知識の配布マニフェストが不正です。')
    for relative in manifest['files']:
        if not isinstance(relative, str) or not KNOWLEDGE.fullmatch(relative):
            raise ValueError(f'知識の配布に許可されていないパスです: {relative}')
        add(root / relative, relative)
    add(manifest_path, manifest_path.relative_to(root).as_posix())
    for name in PROJECT_SCRIPTS:
        add(root / 'scripts' / name, f'scripts/{name}')
    add(root / 'LICENSE', 'docs/toolkit-license.txt')
    return package


def create_project(project_name: str, destination_parent: str | Path | None = None,
                   process_requirements_from: str | Path | None = None,
                   agent_mode: str = 'Codex', what_if: bool = False,
                   root: Path = ROOT) -> dict:
    root = Path(os.path.abspath(root))
    def letter_number(char):
        return unicodedata.category(char)[0] in 'LN'
    if not 1 <= len(project_name) <= 64 or project_name != project_name.strip() or not letter_number(project_name[0]) or not all(letter_number(c) or c in ' _-' for c in project_name) or re.fullmatch(r'CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³]', project_name, re.I):
        raise ValueError('作品名は1～64文字の文字・数字・空白・_・-で指定し、Windows予約名は避けてください。')
    if agent_mode not in {'Codex', 'Claude', 'Antigravity'}:
        raise ValueError('AgentModeはCodex・Claude・Antigravityのいずれかを指定してください。')
    parent = Path(os.path.abspath(destination_parent if destination_parent is not None else root.parent))
    no_links(parent)
    if not parent.is_dir():
        raise ValueError('作成先の親フォルダは既存のフォルダを指定してください。')
    target = parent / project_name
    if target.exists() or target.is_symlink():
        raise ValueError(f'既存の作品は上書きしません: {target}')
    package = collect_package(root)
    if agent_mode == 'Claude':
        for name in ('CLAUDE.md', 'AGENT-MODE.md'):
            source = root / 'templates/manga-project/agent-modes/claude' / name
            no_links(source)
            if not source.is_file():
                raise ValueError(f'Claude用の雛形がありません: {name}')
            package[name] = source
    if agent_mode == 'Antigravity':
        for name in ('GEMINI.md', 'AGENT-MODE.md'):
            source = root / 'templates/manga-project/agent-modes/antigravity' / name
            no_links(source)
            if not source.is_file():
                raise ValueError(f'Antigravity用の雛形がありません: {name}')
            package[name] = source
    # 設定の妥当性は、出力を作る前に確認する。
    from resolve_review_profile import resolve_profile
    resolve_profile(root / 'templates/manga-project/config/review-profiles.json')
    source = None
    if process_requirements_from:
        source = Path(os.path.abspath(process_requirements_from))
        no_links(source)
        if not (source / 'project.json').is_file():
            raise ValueError('引継ぎ元には作品のproject.jsonが必要です。')
        subprocess.run([sys.executable, '-X', 'utf8', str(root / 'scripts/process_checker.py'), 'validate-source', '--from-project', str(source)], check=True, stdout=subprocess.DEVNULL)
    no_links(root / 'distribution-version.txt')
    version = (root / 'distribution-version.txt').read_text(encoding='utf-8-sig').strip()
    result = {'ProjectName': project_name, 'Path': os.path.relpath(target), 'AbsolutePath': str(target), 'Version': version, 'CopiedFiles': len(package), 'AgentMode': agent_mode}
    if what_if:
        return {**result, 'WhatIf': True}
    created = False
    try:
        no_links(parent)
        target.mkdir()  # 既存フォルダは許可しない。
        created = True
        for relative, file in package.items():
            no_links(file)
            dest = target / relative
            no_links(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, dest)
            if dest.suffix == '.sh':
                dest.chmod(dest.stat().st_mode | 0o111)
        ignore = target / '.gitignore'
        ignore.write_text(ignore.read_text(encoding='utf-8-sig').rstrip() + '\n/config/process-requirements.json\n', encoding='utf-8')
        for directory in ('input', 'assets/characters', 'assets/references', 'workflows', 'output', '.secrets'):
            (target / directory).mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        project = {'schemaVersion': 1, 'name': project_name, 'createdAt': now, 'distributionVersion': version, 'sourceKitRelativePath': Path(os.path.relpath(root, target)).as_posix(), 'agentMode': agent_mode}
        if source:
            project['processRequirementsSourceRelativePath'] = Path(os.path.relpath(source, target)).as_posix()
        write_json(target / 'project.json', project)
        if source:
            subprocess.run([sys.executable, '-X', 'utf8', str(target / 'scripts/process_checker.py'), '--project', str(target), 'import', '--from-project', str(source)], check=True, stdout=subprocess.DEVNULL)
        snapshot = [{'path': relative, 'sha256': digest(target / relative)} for relative in sorted(package)]
        write_json(target / 'docs/distribution-snapshot.json', {'version': version, 'createdAt': now, 'files': snapshot})
    except Exception:
        if created:
            print(f'作成が失敗しました。確認用の途中出力を保持しています: {target}', file=sys.stderr)
        raise
    return result


def main() -> int:
    if sys.version_info < (3, 10):
        print('Python 3.10以上が必要です。', file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', nargs='?', help='作品名')
    parser.add_argument('--project-name', '-ProjectName')
    parser.add_argument('--destination-parent', '-DestinationParent')
    parser.add_argument('--process-requirements-from', '-ProcessRequirementsFrom')
    parser.add_argument('--agent-mode', '-AgentMode', choices=('Codex', 'Claude', 'Antigravity'), default='Codex')
    parser.add_argument('--what-if', '--dry-run', '-WhatIf', action='store_true')
    args = parser.parse_args()
    if bool(args.name) == bool(args.project_name):
        parser.error('作品名は位置引数または--project-nameのどちらか一方で指定してください。')
    try:
        result = create_project(args.name or args.project_name, args.destination_parent, args.process_requirements_from, args.agent_mode, args.what_if)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'エラー: {error}\n')
    if args.what_if:
        print('配置の確認のみです。作品は作成していません。', file=sys.stderr)
    else:
        print(f'漫画プロジェクトを作成しました。作成先の絶対パス: {result["AbsolutePath"]}', file=sys.stderr)
        print(f'このフォルダで{args.agent_mode}を開き直してください。作品フォルダで新しい会話を始めてから漫画を制作します。', file=sys.stderr)
        if args.agent_mode == 'Antigravity':
            print('GEMINI.md と AGENT-MODE.md を追加しました。作画は既定でNovelAIを使います。利用可能な生成・画像表示機能と通信の許可を確認してから作画します。', file=sys.stderr)
        print('やり方がわからない場合は、ご利用の環境（Windows／Mac／Linux、アプリ／VS Code）を教えてください。必要な手順をご案内します。', file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
