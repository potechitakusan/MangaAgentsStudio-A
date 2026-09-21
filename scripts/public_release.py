"""このフォルダから直接コミットする公開対象の文書・コード・画像を検査する。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import struct
import unicodedata
from urllib.parse import unquote
import zlib

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ('.gitignore', '.gitattributes', 'README.md', 'AGENTS.md', 'LICENSE', 'distribution-version.txt')
DOC_FILES = ('README.md', 'architecture.md', 'SOURCES.md', 'RIGHTS.md', 'publication.md')
PUBLIC_TREES = ('docs/knowledge', 'skills', 'templates/manga-project', 'resources', 'scripts', 'tests', 'examples')
EXTENSIONS = {'.md', '.py', '.ps1', '.json'}
PANEL_ROOT = 'templates/manga-project/templates/panel-templates'
NOVELAI_RESOURCE_ROOT = 'resources/novelai-style-samples'
TEMPLATE_REQUIREMENTS = 'templates/manga-project/scripts/requirements-composition.txt'
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
PNG_IMAGE_CHUNKS = {b'IHDR', b'PLTE', b'IDAT', b'IEND', b'tRNS'}
JPEG_JFIF_SEGMENT = b'\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
WEBP_IMAGE_CHUNKS = {b'VP8 ', b'VP8L', b'VP8X', b'ALPH', b'ANIM', b'ANMF'}
SPECIAL_FILES = {'.gitignore', '.env.example'}
OLD_FOLDER_NAME = 'Proto' + 'type'
ABSOLUTE_PATH = re.compile(r'(?<![\w])(?:[A-Za-z]:[\\/]|\\\\[\w.-]+\\[\w.$ -]+|/(?:Users|home|mnt|tmp|opt|var)/)')
URL = re.compile(r'https?://[^\s<>`\])]+')
SECRET = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')
KNOWLEDGE_MANIFEST = 'docs/knowledge/supervision/distribution.json'
KNOWLEDGE_PATH = re.compile(
    r'(?:docs/knowledge/supervision/(?:README|routing|sources)\.md'
    r'|docs/knowledge/supervision/gag/(?:README|mechanisms|design-and-review|know-how)\.md'
    r'|docs/knowledge/supervision/(?:tsukkomi|allure|stature|horror|conflict|grief|romance|trust|awkwardness|urgency|revelation|payoff|endearment|bargaining|reconciliation)/README\.md)'
)


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
    for relative in (*ROOT_FILES, *(f'docs/{name}' for name in DOC_FILES), KNOWLEDGE_MANIFEST):
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'公開ファイルがないか、リンクになっています: {relative}')
        reject_link(path)
        files.append(path)
    manifest = json.loads((root / KNOWLEDGE_MANIFEST).read_text(encoding='utf-8-sig'))
    if (not isinstance(manifest, dict) or type(manifest.get('schemaVersion')) is not int
            or manifest['schemaVersion'] != 1 or not isinstance(manifest.get('files'), list)
            or not manifest['files']):
        raise ValueError('知識の配布マニフェストが不正です。')
    seen = set()
    for relative in manifest['files']:
        if not isinstance(relative, str) or not KNOWLEDGE_PATH.fullmatch(relative):
            raise ValueError(f'知識の配布に許可されていないパスです: {relative}')
        if relative.casefold() in seen:
            raise ValueError(f'知識の配布パスが重複しています: {relative}')
        seen.add(relative.casefold())
        path = root / relative
        if not path.is_file():
            raise ValueError(f'配布する知識がありません: {relative}')
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
            # 監修は明示リストから列挙するため、一括走査から除外する。
            if relative == 'docs/knowledge' and Path(current) == base:
                directories[:] = [name for name in directories if name != 'supervision']
            for name in filenames:
                path = Path(current) / name
                if path.suffix in ('.pyc', '.pyo'):
                    continue
                relative_path = path.relative_to(root).as_posix()
                if path.is_symlink() or (getattr(path.stat(), 'st_file_attributes', 0) & 0x400):
                    raise ValueError(f'公開範囲にリンクがあります: {relative_path}')
                example_image = relative == 'examples' and path.suffix in ('.png', '.jpg', '.jpeg')
                panel_asset = (
                    relative_path == f'{PANEL_ROOT}/index.html'
                    or (path.parent.relative_to(root).as_posix() in (f'{PANEL_ROOT}/svg', f'{PANEL_ROOT}/guides') and path.suffix == '.svg')
                    or (path.parent.relative_to(root).as_posix() in (f'{PANEL_ROOT}/png', f'{PANEL_ROOT}/previews') and path.suffix == '.png')
                )
                novelai_resource = (
                    relative_path == f'{NOVELAI_RESOURCE_ROOT}/index.html'
                    or (path.parent.relative_to(root).as_posix() == f'{NOVELAI_RESOURCE_ROOT}/previews' and path.suffix == '.webp')
                )
                onomatopoeia_asset = (
                    relative_path == 'templates/manga-project/templates/onomatopoeia/index.html'
                    or (path.parent.relative_to(root).as_posix() == 'templates/manga-project/templates/onomatopoeia/images' and path.suffix == '.webp')
                )
                panel_renderer = relative_path == 'scripts/render_panel_templates.cjs'
                template_requirements = relative_path == TEMPLATE_REQUIREMENTS
                if path.suffix not in EXTENSIONS and name not in SPECIAL_FILES and not example_image and not panel_asset and not novelai_resource and not onomatopoeia_asset and not panel_renderer and not template_requirements:
                    raise ValueError(f'公開範囲に想定外のファイルがあります: {relative_path}')
                if (name.startswith('.env') and name != '.env.example') or '.secrets' in path.parts:
                    raise ValueError(f'公開範囲に秘密設定があります: {relative_path}')
                if relative == 'templates/manga-project':
                    template_parts = path.relative_to(base).parts
                    if any(part in ('.work', '.codex') for part in template_parts):
                        raise ValueError(f'雛形へ個人の工程記録・Hooks設定を含めないでください: {relative_path}')
                    if relative_path == 'templates/manga-project/config/process-requirements.json':
                        process_data = json.loads(path.read_text(encoding='utf-8-sig'))
                        if (not isinstance(process_data, dict)
                                or type(process_data.get('schemaVersion')) is not int
                                or process_data != {'schemaVersion': 1, 'requirements': []}):
                            raise ValueError('配布原本のプロセス必須事項は空にしてください。')
                    if relative_path == 'templates/manga-project/AGENTS.md':
                        if '<!-- process-checker:strong:start -->' in path.read_text(encoding='utf-8-sig'):
                            raise ValueError('雛形へ個人の強い指示を含めないでください。')
                files.append(path)
    return sorted(set(files))


def png_chunks(data):
    """PNGの区切りとCRCを検査し、再圧縮せず各チャンクを取り出す。"""
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError('PNGの署名が不正です。')
    chunks, offset = [], len(PNG_SIGNATURE)
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError('PNGチャンクが途中で切れています。')
        length = struct.unpack_from('>I', data, offset)[0]
        end = offset + length + 12
        if end > len(data):
            raise ValueError('PNGチャンクの長さが不正です。')
        kind = data[offset + 4:offset + 8]
        crc = struct.unpack_from('>I', data, end - 4)[0]
        if zlib.crc32(data[offset + 4:end - 4]) != crc:
            raise ValueError('PNGチャンクのCRCが一致しません。')
        if not chunks and (kind != b'IHDR' or length != 13):
            raise ValueError('PNGの先頭に正しいIHDRがありません。')
        if kind[0] & 32 == 0 and kind not in PNG_IMAGE_CHUNKS:
            raise ValueError('PNGに未対応の必須チャンクがあります。')
        chunks.append((kind, data[offset:end]))
        offset = end
        if kind == b'IEND':
            if length or offset != len(data):
                raise ValueError('PNGの終端または末尾データが不正です。')
            if not any(name == b'IDAT' for name, _ in chunks):
                raise ValueError('PNGに画像データがありません。')
            return chunks
    raise ValueError('PNGにIENDがありません。')


def jpeg_segments(data):
    """JPEGの区切りを読み、圧縮データを含めて再圧縮せず取り出す。"""
    if not data.startswith(b'\xff\xd8'):
        raise ValueError('JPEGの署名が不正です。')
    segments, offset, has_frame, has_scan = [(0xD8, data[:2])], 2, False, False
    while offset < len(data):
        start = offset
        if data[offset] != 0xFF:
            raise ValueError('JPEGのマーカーが不正です。')
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset == len(data):
            raise ValueError('JPEGのマーカーが途中で切れています。')
        kind = data[offset]
        offset += 1
        if kind == 0xD9:
            if offset != len(data) or not has_frame or not has_scan:
                raise ValueError('JPEGの画像データ・終端・末尾データが不正です。')
            return segments + [(kind, data[start:offset])]
        if kind in (0x00, 0x01, 0xD8) or 0xD0 <= kind <= 0xD7:
            raise ValueError('JPEGに想定外のマーカーがあります。')
        if offset + 2 > len(data):
            raise ValueError('JPEGセグメントが途中で切れています。')
        length = struct.unpack_from('>H', data, offset)[0]
        end = offset + length
        if length < 2 or end > len(data):
            raise ValueError('JPEGセグメントの長さが不正です。')
        segments.append((kind, data[start:end]))
        offset = end
        if kind in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            has_frame = True
        if kind == 0xDA:
            # FF00と再開マーカーは画像本体。複数スキャン間のメタ情報も読む。
            marker = re.search(b'\xff+(?=[^\x00\xff\xd0-\xd7])', data[offset:])
            if marker is None or marker.start() == 0:
                raise ValueError('JPEGの圧縮データまたは終端がありません。')
            end = offset + marker.start()
            segments.append((None, data[offset:end]))
            offset, has_scan = end, True
    raise ValueError('JPEGに終端がありません。')


def jpeg_metadata_segment(kind, segment):
    """個別の付加情報を含まない固定のJFIFヘッダーだけを許可する。"""
    return (kind is not None and (0xE0 <= kind <= 0xEF or kind == 0xFE)
            and segment != JPEG_JFIF_SEGMENT)


def webp_chunks(data):
    """WebPのRIFF区切りを検査し、チャンクを取り出す。"""
    if len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WEBP':
        raise ValueError('WebPのRIFF署名が不正です。')
    if struct.unpack_from('<I', data, 4)[0] != len(data) - 8:
        raise ValueError('WebPのRIFFサイズが不正です。')
    chunks, offset = [], 12
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError('WebPチャンクが途中で切れています。')
        length = struct.unpack_from('<I', data, offset + 4)[0]
        end = offset + 8 + length + (length & 1)
        if end > len(data):
            raise ValueError('WebPチャンクの長さが不正です。')
        kind = data[offset:offset + 4]
        chunks.append((kind, data[offset:end]))
        offset = end
    if not any(kind in {b'VP8 ', b'VP8L', b'ANMF'} for kind, _ in chunks):
        raise ValueError('WebPに画像データがありません。')
    return chunks


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
    if relative in ('OPTION.md', 'PRINT-OPTION.md') or relative.startswith(('docs/story/', 'docs/production/', 'docs/reviews/', 'docs/experiments/', 'docs/feedback/', 'templates/panel-templates/', 'config/')):
        return template / relative
    return target


def check(root=ROOT):
    root = Path(root).resolve()
    files = public_files(root)
    included = set(files)
    errors, local_links = [], 0
    for path in files:
        relative = path.relative_to(root).as_posix()
        if path.suffix == '.png':
            try:
                if any(kind not in PNG_IMAGE_CHUNKS for kind, _ in png_chunks(path.read_bytes())):
                    errors.append(f'PNGに公開前に除去するメタ情報があります: {relative}')
            except ValueError as error:
                errors.append(f'PNGの検査に失敗しました: {relative}: {error}')
            continue
        if path.suffix in ('.jpg', '.jpeg'):
            try:
                if any(jpeg_metadata_segment(kind, segment) for kind, segment in jpeg_segments(path.read_bytes())):
                    errors.append(f'JPEGに公開前に除去するメタ情報があります: {relative}')
            except ValueError as error:
                errors.append(f'JPEGの検査に失敗しました: {relative}: {error}')
            continue
        if path.suffix == '.webp':
            try:
                if any(kind not in WEBP_IMAGE_CHUNKS for kind, _ in webp_chunks(path.read_bytes())):
                    errors.append(f'WebPに公開前に除去するメタ情報があります: {relative}')
            except ValueError as error:
                errors.append(f'WebPの検査に失敗しました: {relative}: {error}')
            continue
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    parser.parse_args()
    try:
        report = check()
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(bool(report['errors']))


if __name__ == '__main__':
    main()
