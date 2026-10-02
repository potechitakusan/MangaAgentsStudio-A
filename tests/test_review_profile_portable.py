"""移植版のレビュー設定検証と優先順位を確認する。"""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.resolve_review_profile import KEYS, resolve_profile


class ReviewProfilePortableTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='レビュー設定 ')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / '設定.json'
        self.config = {
            'schemaVersion': 1,
            'defaults': dict.fromkeys(KEYS, 3),
            'presets': {'物語': {'story': 5, 'cinema': 2}, '映像': {'cinema': 5}},
            'scenes': {'冒頭': {'preset': '物語', 'weights': {'story': 4}, 'reason': '導入'}},
        }

    def write(self, config=None, encoding='utf-8'):
        self.path.write_text(json.dumps(self.config if config is None else config,
                                        ensure_ascii=False), encoding=encoding)

    def test_defaults_and_presets(self):
        self.write()
        result = resolve_profile(self.path)
        self.assertEqual(result, {'schemaVersion': 1, 'sceneId': '', 'preset': '',
                                  'weights': dict.fromkeys(KEYS, 3)})
        self.assertEqual(resolve_profile(self.path, '映像')['weights']['cinema'], 5)

    def test_scene_overrides_preset_and_weights(self):
        self.write()
        result = resolve_profile(self.path, '映像', '冒頭')
        self.assertEqual(result['preset'], '物語')
        self.assertEqual(result['weights']['cinema'], 2)
        self.assertEqual(result['weights']['story'], 4)

    def test_scene_without_preset_preserves_argument(self):
        self.config['scenes']['冒頭'].pop('preset')
        self.write()
        result = resolve_profile(self.path, '映像', '冒頭')
        self.assertEqual(result['preset'], '映像')
        self.assertEqual(result['weights']['cinema'], 5)

    def test_bom_input(self):
        self.write(encoding='utf-8-sig')
        self.assertEqual(resolve_profile(self.path)['schemaVersion'], 1)

    def test_invalid_weight_types_and_ranges(self):
        for value in (True, False, 0, 6, 3.0, '3', None, [], {}):
            with self.subTest(value=value):
                self.config['defaults']['story'] = value
                self.write()
                with self.assertRaises(ValueError):
                    resolve_profile(self.path)

    def test_invalid_schema(self):
        for value in (True, 1.0, '1', None, 2):
            with self.subTest(value=value):
                self.config['schemaVersion'] = value
                self.write()
                with self.assertRaises(ValueError):
                    resolve_profile(self.path)

    def test_missing_required_fields(self):
        for key in ('schemaVersion', 'defaults', 'presets', 'scenes'):
            with self.subTest(key=key):
                config = copy.deepcopy(self.config)
                del config[key]
                self.write(config)
                with self.assertRaises(ValueError):
                    resolve_profile(self.path)
        del self.config['defaults']['story']
        self.write()
        with self.assertRaises(ValueError):
            resolve_profile(self.path)

    def test_unknown_fields(self):
        for location in ((), ('defaults',), ('presets', '物語'),
                         ('scenes', '冒頭'), ('scenes', '冒頭', 'weights')):
            with self.subTest(location=location):
                config = copy.deepcopy(self.config)
                target = config
                for key in location:
                    target = target[key]
                target['unknown'] = 3
                self.write(config)
                with self.assertRaises(ValueError):
                    resolve_profile(self.path)

    def test_invalid_unused_entries(self):
        invalid_entries = [
            ('presets', ' ', {}), ('presets', '未選択', []),
            ('presets', '未選択', {'story': True}),
            ('scenes', '', {}), ('scenes', '未選択', []),
            ('scenes', '未選択', {'preset': '不明'}),
            ('scenes', '未選択', {'preset': None}),
            ('scenes', '未選択', {'reason': 3}),
            ('scenes', '未選択', {'weights': None}),
        ]
        for section, name, entry in invalid_entries:
            with self.subTest(section=section, name=name, entry=entry):
                config = copy.deepcopy(self.config)
                config[section][name] = entry
                self.write(config)
                with self.assertRaises(ValueError):
                    resolve_profile(self.path)

    def test_unknown_selection_rejected(self):
        self.write()
        for preset, scene in (('不明', ''), ('', '不明'), ('不明', '冒頭')):
            with self.subTest(preset=preset, scene=scene):
                with self.assertRaises(ValueError):
                    resolve_profile(self.path, preset, scene)

    def test_invalid_json_and_root(self):
        for content in ('{', '[]', 'null', '{"schemaVersion":NaN}'):
            with self.subTest(content=content):
                self.path.write_text(content, encoding='utf-8')
                with self.assertRaises(ValueError):
                    resolve_profile(self.path)

    def test_python_cli_json_and_failure(self):
        self.write()
        command = [sys.executable, str(ROOT / 'scripts' / 'resolve_review_profile.py'),
                   '--config-path', str(self.path), '--scene-id', '冒頭']
        result = subprocess.run(command, cwd=self.directory.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), resolve_profile(self.path, scene_id='冒頭'))
        self.path.write_text('{}', encoding='utf-8')
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertTrue(result.stderr)

    @unittest.skipIf(os.name == 'nt', 'POSIXシェル用の確認')
    def test_shell_wrapper_from_other_directory(self):
        self.write()
        result = subprocess.run(
            [str(ROOT / 'scripts' / 'Resolve-ReviewProfile.sh'),
             '-ConfigPath', str(self.path), '-Preset', '映像'],
            cwd=self.directory.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), resolve_profile(self.path, '映像'))


if __name__ == '__main__':
    unittest.main()
