"""既存素材の互換、任意ガイドの分離、不正設定時の出力防止を検証する。"""
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_page_layout import place_template, prepare, resolve_config

TEMPLATE = ROOT / 'templates/manga-project'


@contextmanager
def test_directory():
    # 他の配布テストと同じく、調査用の生成物を非公開の.workに保持する。
    path = ROOT / '.work' / ('page-layout-test-' + uuid.uuid4().hex)
    path.mkdir(parents=True)
    yield path


class PageLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.options = json.loads((TEMPLATE / 'config/page-layout.json').read_text(encoding='utf-8'))
        # 素材原本との互換は、その寸法を明示して検査する。新規作品の既定寸法とは区別する。
        cls.config, _ = resolve_config(cls.options, canvas={'width': 2000, 'height': 3000})
        cls.catalog = json.loads((TEMPLATE / 'templates/panel-templates/catalog.json').read_text(encoding='utf-8'))

    def test_all_79_defaults_match_distributed_png_coordinates(self):
        self.assertEqual(len(self.catalog['templates']), 79)
        for item in self.catalog['templates']:
            original = copy.deepcopy(item)
            placed = place_template(item, self.catalog['canvas'], self.config)
            for before, after in zip(item['panels'], placed['panels']):
                self.assertEqual(before['order'], after['order'])
                for src, dst in zip(before['polygon'], after['polygon']):
                    self.assertAlmostEqual(dst[0], 2 * src[0])
                    self.assertAlmostEqual(dst[1], 2 * src[1])
            for before, after in zip(item['modifiers'], placed['modifiers']):
                if 'region' in before:
                    for src, dst in zip(before['region'], after['region']):
                        self.assertAlmostEqual(dst[0], 2 * src[0])
                        self.assertAlmostEqual(dst[1], 2 * src[1])
            self.assertEqual(item, original)

    def test_asymmetric_custom_frame_keeps_order_and_maps_corners(self):
        config = copy.deepcopy(self.config)
        config['canvas'] = {'width': 1200, 'height': 1800}
        config['basicFrame'] = {'left': 80, 'right': 100, 'top': 140, 'bottom': 180}
        item = next(t for t in self.catalog['templates'] if t['id'] == 'P1-splash')
        placed = place_template(item, self.catalog['canvas'], config)
        self.assertEqual(placed['panels'][0]['polygon'], [[80, 140], [1100, 140], [1100, 1620], [80, 1620]])
        self.assertNotIn('assets', placed)
        self.assertEqual(placed['coordinateSystem']['unit'], 'px')

    def test_unknown_generation_size_does_not_silently_choose_3000(self):
        with self.assertRaisesRegex(ValueError, '寸法が未確定'):
            resolve_config(self.options)

    def test_changing_canvas_alone_scales_margins_lines_and_guides(self):
        config = copy.deepcopy(self.options)
        config['canvas'] = {'width': 1024, 'height': 1536}
        effective, dimensions = resolve_config(config)
        self.assertAlmostEqual(effective['basicFrame']['left'], 61.44)
        self.assertAlmostEqual(effective['basicFrame']['top'], 61.44)
        self.assertAlmostEqual(effective['textSafeArea']['right'], 81.92)
        self.assertAlmostEqual(effective['frameStroke'], 5.12)
        self.assertAlmostEqual(effective['guideStroke'], 1.536)
        self.assertEqual(dimensions['working'], dimensions['export'])
        self.assertEqual(dimensions['workingToExportScale'], 1)
        item = next(t for t in self.catalog['templates'] if t['id'] == 'P1-splash')
        placed = place_template(item, self.catalog['canvas'], effective)
        self.assertEqual(placed['panels'][0]['polygon'],
                         [[61.44, 61.44], [962.56, 61.44], [962.56, 1474.56], [61.44, 1474.56]])

    def test_fixed_pixels_override_only_selected_values(self):
        config = copy.deepcopy(self.options)
        config['fixedPixels'] = {'basicFrame': {'left': 80}, 'frameStroke': 6}
        before = copy.deepcopy(config)
        small, _ = resolve_config(config, canvas={'width': 1000, 'height': 1500})
        large, _ = resolve_config(config, canvas={'width': 2000, 'height': 3000})
        self.assertEqual(small['basicFrame'], {'left': 80, 'right': 60, 'top': 60, 'bottom': 60})
        self.assertEqual(small['frameStroke'], 6)
        self.assertEqual(small['textSafeArea']['left'], 80)
        self.assertEqual(large['basicFrame']['right'], 120)
        self.assertEqual(config, before)

    def test_changed_aspect_ratio_uses_axis_margins_and_uniform_stroke(self):
        effective, _ = resolve_config(self.options, canvas={'width': 1000, 'height': 3000})
        self.assertEqual(effective['basicFrame'], {'left': 60, 'right': 60, 'top': 120, 'bottom': 120})
        self.assertEqual(effective['frameStroke'], 5)

    def test_actual_png_size_takes_precedence_over_generation_request(self):
        config = copy.deepcopy(self.options)
        config['generationCanvas'] = {'width': 1024, 'height': 1536}
        source = TEMPLATE / 'templates/panel-templates/png/P1-splash.png'
        before = source.read_bytes()
        with test_directory() as temp:
            record = prepare(self.catalog, 'P1-splash', config, temp / 'from-png', page_image=source)
        self.assertEqual(record['dimensions']['generationRequested'], {'width': 1024, 'height': 1536})
        self.assertEqual(record['dimensions']['generationActual'], {'width': 2000, 'height': 3000})
        self.assertEqual(record['dimensions']['working'], record['dimensions']['generationActual'])
        self.assertEqual(source.read_bytes(), before)
        self.assertNotIn(str(source), json.dumps(record))

    def test_export_dimensions_do_not_change_working_frames(self):
        config = copy.deepcopy(self.options)
        config['exportCanvas'] = {'width': 2000, 'height': 3000}
        with test_directory() as temp:
            before = prepare(self.catalog, 'P1-splash', self.options, temp / 'same',
                             canvas={'width': 1024, 'height': 1536})
            after = prepare(self.catalog, 'P1-splash', config, temp / 'export',
                            canvas={'width': 1024, 'height': 1536})
            self.assertEqual((temp / 'same/frames.svg').read_bytes(), (temp / 'export/frames.svg').read_bytes())
        self.assertEqual(before['page'], after['page'])
        self.assertEqual(after['dimensions']['workingToExportScale'], 1.953125)
        self.assertIsNone(after['dimensions']['generationActual'])

    def test_aspect_mismatch_is_not_silently_stretched(self):
        config = copy.deepcopy(self.options)
        config['exportCanvas'] = {'width': 1000, 'height': 1000}
        with self.assertRaisesRegex(ValueError, '縦横比'):
            resolve_config(config, canvas={'width': 1024, 'height': 1536})
        with self.assertRaisesRegex(ValueError, '縦横比'):
            resolve_config(self.options, canvas={'width': 1024, 'height': 1536},
                           generated_canvas={'width': 1024, 'height': 1024})

    def test_legacy_config_keeps_pixels_and_explicit_resize_scales_from_it(self):
        legacy = {'schemaVersion': 1, 'canvas': {'width': 1200, 'height': 1800},
                  'basicFrame': {'left': 80, 'right': 100, 'top': 140, 'bottom': 180},
                  'textSafeArea': {'left': 100, 'right': 120, 'top': 160, 'bottom': 200},
                  'frameStroke': 8, 'showGuide': False}
        effective, _ = resolve_config(legacy)
        resized, _ = resolve_config(legacy, canvas={'width': 600, 'height': 900})
        self.assertEqual(effective['basicFrame'], legacy['basicFrame'])
        self.assertEqual(effective['frameStroke'], 8)
        self.assertEqual(resized['basicFrame'], {'left': 40, 'right': 50, 'top': 70, 'bottom': 90})
        self.assertEqual(resized['frameStroke'], 4)

    def test_guide_never_changes_publishable_frames(self):
        with test_directory() as temp:
            for item in self.catalog['templates']:
                base = Path(temp) / item['id']
                clean, guided = base / 'clean', base / 'guided'
                a = prepare(self.catalog, item['id'], self.config, clean)
                b = prepare(self.catalog, item['id'], self.config, guided, True)
                self.assertFalse((clean / 'guide.svg').exists())
                self.assertEqual((clean / 'frames.svg').read_bytes(), (guided / 'frames.svg').read_bytes())
                self.assertEqual(a['template'], b['template'])
                svg = ET.parse(guided / 'frames.svg').getroot()
                self.assertEqual(len(svg.findall('.//{*}polygon')), item['panelCount'])
                self.assertFalse(svg.findall('.//{*}rect'))
                self.assertFalse(svg.findall('.//{*}text'))
                guide = ET.parse(guided / 'guide.svg').getroot()
                self.assertEqual(len(guide.findall('.//{*}rect')), 2)

    def test_guide_config_can_be_overridden_off(self):
        config = copy.deepcopy(self.config)
        config['showGuide'] = True
        with test_directory() as temp:
            for override, expected, name in ((None, True, 'on'), (False, False, 'off')):
                output = Path(temp) / name
                record = prepare(self.catalog, 'P1-splash', config, output, override)
                self.assertEqual((output / 'guide.svg').exists(), expected)
                self.assertEqual(record['page']['showGuide'], expected)

    def test_invalid_settings_fail_before_creating_output(self):
        invalid = []
        for keys, value in ((('canvas', 'width'), 0), (('canvas', 'height'), True),
                            (('basicFrame', 'left'), -1), (('basicFrame', 'right'), 2000),
                            (('textSafeArea', 'top'), float('nan')), (('frameStroke',), 0),
                            (('showGuide',), 'false'), (('schemaVersion',), True)):
            config = copy.deepcopy(self.config)
            target = config
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = value
            invalid.append(config)
        with test_directory() as temp:
            output = Path(temp) / 'invalid'
            for config in invalid:
                with self.assertRaises(ValueError):
                    prepare(self.catalog, 'P1-splash', config, output)
                self.assertFalse(output.exists())

    def test_unknown_id_and_existing_output_are_not_overwritten(self):
        with test_directory() as temp:
            output = Path(temp) / 'page'
            with self.assertRaises(ValueError):
                prepare(self.catalog, 'missing', self.config, output)
            self.assertFalse(output.exists())
            prepare(self.catalog, 'P1-splash', self.config, output, True)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            with self.assertRaises(ValueError):
                prepare(self.catalog, 'P1-splash', self.config, output, False)
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_project_relative_cli_works_without_kit_runtime(self):
        with test_directory() as temp:
            project = Path(temp)
            for dest, source in (
                ('scripts/prepare_page_layout.py', ROOT / 'scripts/prepare_page_layout.py'),
                ('config/page-layout.json', TEMPLATE / 'config/page-layout.json'),
                ('templates/panel-templates/catalog.json', TEMPLATE / 'templates/panel-templates/catalog.json'),
            ):
                target = project / dest
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            result = subprocess.run([sys.executable, '-X', 'utf8', 'scripts/prepare_page_layout.py',
                                     '--template', 'P1-splash', '--canvas', '1024', '1536',
                                     '--output', 'output/layout/page-001'],
                                    cwd=project, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads((project / 'output/layout/page-001/layout.json').read_text(encoding='utf-8'))
            self.assertEqual(record['files'], {'frames': 'frames.svg', 'guide': None})
            self.assertEqual(record['dimensions']['working'], {'width': 1024, 'height': 1536})
            self.assertAlmostEqual(record['page']['basicFrame']['left'], 61.44)
            self.assertNotIn(str(ROOT), json.dumps(record))


if __name__ == '__main__':
    unittest.main()
