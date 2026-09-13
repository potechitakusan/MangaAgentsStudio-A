"""公開物への私的データ混入と書き出しの上書きを検証する。"""
import json
from pathlib import Path
import shutil
import sys
import unittest
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.public_release import check, export, public_files


class PublicReleaseTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / '.work' / ('public-test-' + uuid.uuid4().hex) / 'renamed-kit'
        for source in public_files(ROOT):
            destination = self.root / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

    def test_private_files_are_excluded_and_archive_matches(self):
        for name in ('backup/private.txt', '.work/private.txt', 'output/example.mp4', 'input/request.txt',
                     'docs/PLAN.md', 'docs/PROGRESS.md', 'matelial/private.png'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('非公開', encoding='utf-8')
        result = export(self.root / '.work/release-0.1.0', self.root)
        self.assertFalse(result['errors'])
        self.assertTrue(result['zip'].endswith('release-0.1.0.zip'))
        expected = {p.relative_to(self.root).as_posix() for p in public_files(self.root)}
        with zipfile.ZipFile(self.root / result['zip']) as archive:
            self.assertEqual(set(archive.namelist()), expected)
            for name in expected:
                self.assertEqual(archive.read(name), (self.root / name).read_bytes())
        manifest = json.loads((self.root / result['manifest']).read_text(encoding='utf-8'))
        self.assertEqual({i['path'] for i in manifest['files']}, expected)

    def test_existing_manifest_prevents_any_export(self):
        target = self.root / '.work/release'
        target.parent.mkdir(parents=True)
        manifest = Path(str(target) + '.manifest.json')
        manifest.write_text('保持', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            export(target, self.root)
        self.assertFalse(target.exists())
        self.assertEqual(manifest.read_text(encoding='utf-8'), '保持')

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


if __name__ == '__main__':
    unittest.main()
