"""直接コミットする公開対象への私的データ混入と検査の非破壊性を検証する。"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import unittest
import uuid
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.public_release import JPEG_JFIF_SEGMENT, PNG_IMAGE_CHUNKS, PNG_SIGNATURE, check, jpeg_segments, png_chunks, public_files


def png_chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))


def example_png(extra=b''):
    # 透明度付きパレットを使う1ピクセルのPNG。画像に必要な補助チャンクも確認する。
    return (PNG_SIGNATURE + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 3, 0, 0, 0))
            + png_chunk(b'PLTE', b'\xff\x00\x00') + png_chunk(b'tRNS', b'\x80') + extra
            + png_chunk(b'IDAT', zlib.compress(b'\x00\x00')) + png_chunk(b'IEND', b''))


def jpeg_segment(kind, payload):
    return bytes((0xFF, kind)) + struct.pack('>H', len(payload) + 2) + payload


def example_jpeg(extra=b''):
    # 区切り検査用。FF00、再開マーカー、複数スキャンを含める。
    frame = jpeg_segment(0xC0, b'\x08\x00\x01\x00\x01\x01\x01\x11\x00')
    scan = jpeg_segment(0xDA, b'\x01\x01\x00\x00\x3f\x00')
    return (b'\xff\xd8' + JPEG_JFIF_SEGMENT + frame + scan
            + b'\x12\xff\x00\x34\xff\xd0\x56' + extra + scan + b'\x78\xff\xd9')


class PublicReleaseTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / '.work' / ('public-test-' + uuid.uuid4().hex) / 'renamed-kit'
        for source in public_files(ROOT):
            destination = self.root / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

    def test_private_files_are_excluded_and_examples_are_included(self):
        private_names = ('backup/private.txt', '.work/private.txt', 'output/example.mp4', 'input/request.txt',
                         'docs/PLAN.md', 'docs/PROGRESS.md', 'matelial/private.png',
                         'docs/knowledge/supervision/unlisted.md',
                         'docs/knowledge/supervision/gag/unlisted.md',
                         'docs/knowledge/supervision/tsukkomi/unlisted.md',
                         'docs/knowledge/supervision/allure/unlisted.md',
                         'docs/knowledge/supervision/stature/unlisted.md',
                         'docs/knowledge/supervision/horror/unlisted.md',
                         'docs/knowledge/supervision/conflict/unlisted.md',
                         'docs/knowledge/supervision/grief/unlisted.md',
                         'docs/knowledge/supervision/romance/unlisted.md',
                         'docs/knowledge/supervision/trust/unlisted.md',
                         'docs/knowledge/supervision/awkwardness/unlisted.md',
                         'docs/knowledge/supervision/urgency/unlisted.md',
                         'docs/knowledge/supervision/revelation/unlisted.md',
                         'docs/knowledge/supervision/payoff/unlisted.md',
                         'docs/knowledge/supervision/endearment/unlisted.md',
                         'docs/knowledge/supervision/bargaining/unlisted.md',
                         'docs/knowledge/supervision/reconciliation/unlisted.md',
                         'docs/knowledge/supervision/unreleased-theme/README.md',
                         '特別な理由でこのフォルダの中で漫画を作ります.txt')
        for name in private_names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('非公開', encoding='utf-8')
        result = check(self.root)
        self.assertFalse(result['errors'])
        expected = {p.relative_to(self.root).as_posix() for p in public_files(self.root)}
        self.assertTrue(expected.isdisjoint(private_names))
        self.assertIn('examples/README.md', expected)
        self.assertTrue(any(name.startswith('examples/') and name.endswith('.png') for name in expected))
        self.assertEqual(result['files'], len(expected))

    def test_check_does_not_create_or_change_files(self):
        def snapshot():
            return {path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in self.root.rglob('*') if path.is_file()}
        before = snapshot()
        self.assertFalse(check(self.root)['errors'])
        self.assertEqual(snapshot(), before)

    def test_personal_process_data_cannot_be_distributed(self):
        template = self.root / 'templates/manga-project'
        registry = template / 'config/process-requirements.json'
        original = registry.read_bytes()
        registry.write_text(json.dumps({'schemaVersion': 1, 'requirements': [{'instruction': '個人の指示'}]}), encoding='utf-8')
        with self.assertRaises(ValueError):
            public_files(self.root)
        registry.write_bytes(original)
        for relative, body in (('.work/process-checker/state.json', '{}'), ('.codex/hooks.json', '{}')):
            path = template / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding='utf-8')
            with self.assertRaises(ValueError):
                public_files(self.root)
            path.unlink()
        with (template / 'AGENTS.md').open('a', encoding='utf-8') as stream:
            stream.write('\n<!-- process-checker:strong:start -->\n個人の指示\n<!-- process-checker:strong:end -->\n')
        with self.assertRaises(ValueError):
            public_files(self.root)

    def test_absolute_working_path_is_rejected_but_urls_are_allowed(self):
        path = self.root / 'docs/knowledge/fixture.md'
        path.write_text('参考: https://example.org/docs\n', encoding='utf-8')
        self.assertFalse(check(self.root)['errors'])
        path.write_text('設定: ' + str(self.root.resolve()), encoding='utf-8')
        self.assertTrue(any('絶対パス' in error for error in check(self.root)['errors']))

    def test_missing_link_and_unexpected_media_are_rejected(self):
        path = self.root / 'docs/knowledge/fixture.md'
        path.write_text('[参照](missing.md)', encoding='utf-8')
        self.assertTrue(any('リンク' in error for error in check(self.root)['errors']))
        (self.root / 'templates/manga-project/example.png').write_bytes(b'private')
        with self.assertRaises(ValueError):
            public_files(self.root)

    def test_example_png_preserves_palette_and_transparency(self):
        path = self.root / 'examples/fixture.png'
        path.write_bytes(example_png())
        self.assertIn(path, public_files(self.root))
        self.assertFalse(check(self.root)['errors'])
        self.assertEqual(PNG_SIGNATURE + b''.join(chunk for kind, chunk in png_chunks(path.read_bytes())
                                                if kind in PNG_IMAGE_CHUNKS), path.read_bytes())

    def test_example_metadata_fails_check(self):
        path = self.root / 'examples/fixture.png'
        for kind in (b'eXIf', b'tEXt', b'zTXt', b'iTXt', b'caBX', b'iCCP', b'pHYs', b'tIME'):
            with self.subTest(kind=kind):
                path.write_bytes(example_png(png_chunk(kind, b'private metadata')))
                self.assertTrue(any('メタ情報' in error for error in check(self.root)['errors']))

    def test_invalid_png_prevents_publication(self):
        path = self.root / 'examples/fixture.png'
        clean = example_png()
        for bad in (b'not a PNG', clean[:-2], clean[:-12], clean + b'private data',
                    clean[:-1] + bytes([clean[-1] ^ 1])):
            with self.subTest(length=len(bad)):
                path.write_bytes(bad)
                self.assertTrue(any('PNGの検査に失敗' in error for error in check(self.root)['errors']))

    def test_example_jpeg_is_included_and_scan_data_is_preserved(self):
        for suffix in ('.jpg', '.jpeg'):
            with self.subTest(suffix=suffix):
                path = self.root / ('examples/fixture' + suffix)
                path.write_bytes(example_jpeg())
                self.assertIn(path, public_files(self.root))
                self.assertFalse(check(self.root)['errors'])
                self.assertEqual(b''.join(segment for _, segment in jpeg_segments(path.read_bytes())),
                                 path.read_bytes())

    def test_jpeg_metadata_between_scans_fails_check(self):
        path = self.root / 'examples/fixture.jpg'
        for kind in (*range(0xE0, 0xF0), 0xFE):
            with self.subTest(kind=kind):
                path.write_bytes(example_jpeg(jpeg_segment(kind, b'private metadata')))
                self.assertTrue(any('JPEGに公開前に除去するメタ情報' in error
                                    for error in check(self.root)['errors']))

    def test_invalid_jpeg_prevents_publication(self):
        path = self.root / 'examples/fixture.jpg'
        clean = example_jpeg()
        for bad in (b'not a JPEG', clean[:-1], clean[:-2], clean + b'private data',
                    b'\xff\xd8\xff\xd9', b'\xff\xd8\xff\xe1\x00\x01',
                    b'\xff\xd8\xff\xe1\xff\xff'):
            with self.subTest(data=bad[:20]):
                path.write_bytes(bad)
                self.assertTrue(any('JPEGの検査に失敗' in error for error in check(self.root)['errors']))

    def test_jpeg_outside_examples_is_rejected(self):
        (self.root / 'docs/knowledge/fixture.jpg').write_bytes(example_jpeg())
        with self.assertRaises(ValueError):
            public_files(self.root)

    def test_git_candidates_cover_public_files(self):
        # 配布元に.gitがない場合も、隔離した検証用リポジトリで追加候補を照合する。
        subprocess.run(['git', 'init', '--quiet'], cwd=self.root, check=True, capture_output=True)
        # 除外設定の単一階層パターンからテスト用フォルダを生成する。
        ignore_patterns = (self.root / '.gitignore').read_text(encoding='utf-8')
        ignored_directories = re.findall(r'^([\w.-]+/)\s*$', ignore_patterns, re.MULTILINE)
        self.assertTrue(ignored_directories)
        private_names = [name + 'temp.md' for name in ignored_directories] + [
            'docs/PLAN.md', 'docs/PROGRESS.md',
            'docs/knowledge/supervision/unlisted.md',
            'docs/knowledge/supervision/gag/unlisted.md',
            'docs/knowledge/supervision/tsukkomi/unlisted.md',
            'docs/knowledge/supervision/allure/unlisted.md',
            'docs/knowledge/supervision/stature/unlisted.md',
            'docs/knowledge/supervision/horror/unlisted.md',
            'docs/knowledge/supervision/conflict/unlisted.md',
            'docs/knowledge/supervision/grief/unlisted.md',
            'docs/knowledge/supervision/romance/unlisted.md',
            'docs/knowledge/supervision/trust/unlisted.md',
            'docs/knowledge/supervision/awkwardness/unlisted.md',
            'docs/knowledge/supervision/urgency/unlisted.md',
            'docs/knowledge/supervision/revelation/unlisted.md',
            'docs/knowledge/supervision/payoff/unlisted.md',
            'docs/knowledge/supervision/endearment/unlisted.md',
            'docs/knowledge/supervision/bargaining/unlisted.md',
            'docs/knowledge/supervision/reconciliation/unlisted.md',
            'docs/knowledge/supervision/unreleased-theme/README.md',
        ]
        for name in private_names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('除外検査用のテストデータ', encoding='utf-8')
        result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                                cwd=self.root, check=True, capture_output=True)
        candidates = set(result.stdout.decode('utf-8').split('\0')) - {''}
        expected = {p.relative_to(self.root).as_posix() for p in public_files(self.root)}
        self.assertEqual(expected, candidates)

    def test_knowledge_manifest_rejects_unlisted_paths_and_duplicates(self):
        path = self.root / 'docs/knowledge/supervision/distribution.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        for extra in ('docs/knowledge/supervision/unlisted.md',
                      'docs/knowledge/supervision/gag/unlisted.md',
                      'docs/knowledge/supervision/tsukkomi/unlisted.md',
                      'docs/knowledge/supervision/allure/unlisted.md',
                      'docs/knowledge/supervision/stature/unlisted.md',
                      'docs/knowledge/supervision/horror/unlisted.md',
                      'docs/knowledge/supervision/conflict/unlisted.md',
                      'docs/knowledge/supervision/grief/unlisted.md',
                      'docs/knowledge/supervision/romance/unlisted.md',
                      'docs/knowledge/supervision/trust/unlisted.md',
                      'docs/knowledge/supervision/awkwardness/unlisted.md',
                      'docs/knowledge/supervision/urgency/unlisted.md',
                      'docs/knowledge/supervision/revelation/unlisted.md',
                      'docs/knowledge/supervision/payoff/unlisted.md',
                      'docs/knowledge/supervision/endearment/unlisted.md',
                      'docs/knowledge/supervision/bargaining/unlisted.md',
                      'docs/knowledge/supervision/reconciliation/unlisted.md',
                      'docs/knowledge/supervision/unreleased-theme/README.md',
                      'docs/knowledge/unlisted.md',
                      '../unlisted.md', manifest['files'][0]):
            with self.subTest(extra=extra):
                changed = dict(manifest, files=manifest['files'] + [extra])
                path.write_text(json.dumps(changed), encoding='utf-8')
                with self.assertRaises(ValueError):
                    public_files(self.root)

    def test_distributed_knowledge_link_is_checked(self):
        path = self.root / 'templates/manga-project/README.md'
        with path.open('a', encoding='utf-8') as stream:
            stream.write('\n[汎用](docs/knowledge/manga/03-beat-pacing-timing.md#reader-anticipation)\n')
        self.assertFalse(check(self.root)['errors'])
        with path.open('a', encoding='utf-8') as stream:
            stream.write('\n[リンクテスト](docs/knowledge/supervision/unlisted.md)\n')
        self.assertTrue(any('リンク' in error for error in check(self.root)['errors']))

    def test_panel_media_permission_is_limited_to_designated_locations(self):
        for name in ('scripts/panel-templates-private.png', 'docs/knowledge/panel-templates/private.png',
                     'templates/manga-project/private.svg', 'templates/manga-project/private.html',
                     'scripts/private.cjs'):
            with self.subTest(name=name):
                path = self.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('非公開のダミー情報', encoding='utf-8')
                try:
                    with self.assertRaises(ValueError):
                        public_files(self.root)
                finally:
                    path.unlink()

    def test_panel_png_metadata_is_checked(self):
        path = self.root / 'templates/manga-project/templates/panel-templates/png/fixture.png'
        path.write_bytes(example_png(png_chunk(b'tEXt', b'private metadata')))
        self.assertTrue(any('メタ情報' in error for error in check(self.root)['errors']))

    def test_feedback_starts_with_only_a_blank_template(self):
        folder = self.root / 'templates/manga-project/docs/feedback'
        self.assertEqual({p.name for p in folder.iterdir()}, {'TEMPLATE.md'})


if __name__ == '__main__':
    unittest.main()
