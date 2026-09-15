"""直接コミットする公開対象への私的データ混入と検査の非破壊性を検証する。"""
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest
import uuid
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.public_release import PNG_IMAGE_CHUNKS, PNG_SIGNATURE, check, png_chunks, public_files


def png_chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))


def example_png(extra=b''):
    # 透明度付きパレットを使う1ピクセルのPNG。画像に必要な補助チャンクも確認する。
    return (PNG_SIGNATURE + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 3, 0, 0, 0))
            + png_chunk(b'PLTE', b'\xff\x00\x00') + png_chunk(b'tRNS', b'\x80') + extra
            + png_chunk(b'IDAT', zlib.compress(b'\x00\x00')) + png_chunk(b'IEND', b''))


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

    def test_git_candidates_cover_public_files(self):
        # 実際のGit追加候補と検査対象を照合し、素材の配布漏れを検出する。
        result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                                cwd=ROOT, check=True, capture_output=True)
        candidates = set(result.stdout.decode('utf-8').split('\0')) - {''}
        expected = {p.relative_to(ROOT).as_posix() for p in public_files(ROOT)}
        self.assertEqual(expected, candidates)

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
