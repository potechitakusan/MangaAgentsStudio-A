"""公開対象の文書・コードを検査し、公開用フォルダとZIPを書き出す。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import unicodedata
from urllib.parse import unquote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ('.gitignore', '.gitattributes', 'README.md', 'AGENTS.md', 'LICENSE', 'distribution-version.txt')
DOC_FILES = ('README.md', 'architecture.md', 'SOURCES.md', 'RIGHTS.md', 'publication.md')
PUBLIC_TREES = ('docs/knowledge', 'skills', 'templates/manga-project', 'scripts', 'tests')
EXTENSIONS = {'.md', '.py', '.ps1', '.json'}
SPECIAL_FILES = {'.gitignore', '.env.example'}
OLD_FOLDER_NAME = 'Proto' + 'type'
ABSOLUTE_PATH = re.compile(r'(?<![\w])(?:[A-Za-z]:[\\/]|\\\\[\w.-]+\\[\w.$ -]+|/(?:Users|home|mnt|tmp|opt|var)/)')
URL = re.compile(r'https?://[^\s<>`\])]+')
SECRET = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')


def public_files(root=ROOT):
    """明示した公開範囲だけを列挙し、リンクや想定外の形式を拒否する。"""
    root = Path(root).resolve()
    files = []
    def reject_link(path):
        for current in (path, *path.parents):
            if current == root:
                break
            if current.is_symlink() or (getattr(current.stat(), 'st_file_attributes', 0) & 0x400):
                raise ValueError(f'公開範囲にリンクがあります: {path.relative_to(root)}')
    for relative in (*ROOT_FILES, *(f'docs/{name}' for name in DOC_FILES)):
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'公開ファイルがないか、リンクになっています: {relative}')
        reject_link(path)
        files.append(path)
    for relative in PUBLIC_TREES:
        base = root / relative
        if not base.is_dir() or base.is_symlink():
            raise ValueError(f'公開ディレクトリがありません: {relative}')
        reject_link(base)
        for current, directories, filenames in os.walk(base, followlinks=False):
            for name in directories:
                directory = Path(current) / name
                if directory.is_symlink() or (getattr(directory.stat(), 'st_file_attributes', 0) & 0x400):
                    raise ValueError(f'公開範囲にリンクがあります: {directory.relative_to(root)}')
            directories[:] = [name for name in directories if name != '__pycache__']
            for name in filenames:
                path = Path(current) / name
                if path.suffix in ('.pyc', '.pyo'):
                    continue
                relative_path = path.relative_to(root).as_posix()
                if path.is_symlink() or (getattr(path.stat(), 'st_file_attributes', 0) & 0x400):
                    raise ValueError(f'公開範囲にリンクがあります: {relative_path}')
                if path.suffix not in EXTENSIONS and name not in SPECIAL_FILES:
                    raise ValueError(f'公開範囲に想定外のファイルがあります: {relative_path}')
                if (name.startswith('.env') and name != '.env.example') or '.secrets' in path.parts:
                    raise ValueError(f'公開範囲に秘密設定があります: {relative_path}')
                files.append(path)
    return sorted(set(files))


def anchors(body):
    found = set(re.findall(r'<a\s+id="([^"]+)"', body))
    counts = {}
    for heading in re.findall(r'^#{1,6}\s+(.+)$', body, re.M):
        heading = re.sub(r'<[^>]*>', '', heading).lower()
        slug = ''.join(c for c in heading if c in '-_ ' or not unicodedata.category(c).startswith(('P', 'S'))).replace(' ', '-')
        occurrence = counts.get(slug, 0)
        counts[slug] = occurrence + 1
        found.add(slug if occurrence == 0 else f'{slug}-{occurrence}')
    return found


def distributed_target(root, target):
    """原本の分離配置を、新規作品に配布した際の配置へ対応させる。"""
    template = root / 'templates/manga-project'
    try:
        relative = target.relative_to(template).as_posix()
    except ValueError:
        relative = None
    if relative:
        if relative.startswith('docs/knowledge/'):
            return root / relative
        if relative.startswith('.agents/skills/'):
            return root / 'skills' / relative.removeprefix('.agents/skills/')
        if relative.startswith('scripts/'):
            return root / relative
        if relative == 'docs/toolkit-license.txt':
            return root / 'LICENSE'
    try:
        relative = target.relative_to(root).as_posix()
    except ValueError:
        return target
    if relative.startswith(('docs/story/', 'docs/production/', 'docs/reviews/', 'docs/experiments/', 'docs/feedback/')):
        return template / relative
    return target


def check(root=ROOT):
    root = Path(root).resolve()
    files = public_files(root)
    included = set(files)
    errors, local_links = [], 0
    for path in files:
        relative = path.relative_to(root).as_posix()
        body = path.read_text(encoding='utf-8-sig')
        without_urls = URL.sub('', body)
        if OLD_FOLDER_NAME.lower() in without_urls.lower():
            errors.append(f'固定フォルダ名が残っています: {relative}')
        if ABSOLUTE_PATH.search(without_urls):
            errors.append(f'作業用の絶対パスがあります: {relative}')
        if SECRET.search(body):
            errors.append(f'秘密情報らしい値があります: {relative}')
        if path.suffix != '.md':
            continue
        # コード例はリンク検証から除く。文章中と参照定義のリンクを対象にする。
        prose = re.sub(r'^```[^\n]*\n.*?^```\s*$', '', body, flags=re.M | re.S)
        targets = re.findall(r'\[[^\]\n]*\]\(([^)\s]+)\)', prose)
        targets += re.findall(r'^\[[^\]\n]+\]:\s+(\S+)', prose, re.M)
        for value in targets:
            if re.match(r'https?://|mailto:', value):
                continue
            local_links += 1
            link_path, _, fragment = unquote(value).partition('#')
            target = (path.parent / link_path).resolve() if link_path else path
            target = distributed_target(root, target)
            if target not in included:
                errors.append(f'公開対象にないリンク: {relative} => {value}')
            elif fragment and target.suffix == '.md' and fragment not in anchors(target.read_text(encoding='utf-8-sig')):
                errors.append(f'見出しがないリンク: {relative} => {value}')
        columns = None
        for line in prose.splitlines():
            if line.startswith('|') and line.endswith('|'):
                count = len(re.split(r'(?<!\\)\|', line)) - 2
                if columns is not None and count != columns:
                    errors.append(f'表の列数が不一致: {relative}')
                columns = count
            else:
                columns = None
    return {'version': (root / 'distribution-version.txt').read_text().strip(),
            'files': len(files), 'local_links': local_links, 'errors': errors}


def export(output, root=ROOT):
    root, output = Path(root).resolve(), Path(output).resolve()
    report = check(root)
    if report['errors']:
        raise ValueError('\n'.join(report['errors']))
    # 公開対象への書き出し混入を避け、専用の一時領域へ限定する。
    if not output.is_relative_to(root / '.work') or output == root / '.work':
        raise ValueError('公開用書き出し先は .work/ 内の新しいフォルダにしてください。')
    archive = Path(str(output) + '.zip')
    verification = Path(str(output) + '.manifest.json')
    if output.exists() or archive.exists() or verification.exists():
        raise FileExistsError('書き出し先・ZIP・検証記録が既にあります。新しい名前を指定してください。')
    selected = public_files(root)
    output.mkdir(parents=True)
    inventory = []
    for path in selected:
        relative = path.relative_to(root)
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        inventory.append({'path': relative.as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as bundle:
        for item in inventory:
            bundle.write(output / item['path'], item['path'])
    verification.write_text(json.dumps({'version': report['version'], 'files': inventory}, ensure_ascii=False, indent=2), encoding='utf-8')
    return {**report, 'output': output.relative_to(root).as_posix(), 'zip': archive.relative_to(root).as_posix(),
            'manifest': verification.relative_to(root).as_posix()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    export_parser = sub.add_parser('export')
    export_parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = check() if args.command == 'check' else export(args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(bool(report['errors']))


if __name__ == '__main__':
    main()
