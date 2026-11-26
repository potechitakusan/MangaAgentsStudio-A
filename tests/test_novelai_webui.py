"""WebUIをダミー作品とループバック通信だけで検証する。ブラウザー・外部APIは使わない。"""
import http.client
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/novelai-batch-webui'
sys.path.insert(0, str(ROOT / 'templates/manga-project/scripts'))
spec = importlib.util.spec_from_file_location('novelai_webui', SKILL / 'novelai_webui.py')
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class WebUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='webui-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'project.json').write_text('{"name":"テスト作品"}', encoding='utf-8')
        (self.root / '.env').write_text('NOVELAI_API_KEY=fixture-secret-token\n', encoding='utf-8')
        (self.root / '.env.novelai').write_text('NOVELAI_CHAR_TEST=1girl\n', encoding='utf-8')
        self.project = ui.Project(self.root)
        self.network = patch.object(self.project.batch.api, 'api_request', side_effect=AssertionError('外部通信は禁止'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def write(self, name, body=b'fixture'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path

    def server(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), ui.make_handler(self.project, 'fixture-token', 0))
        port = server.server_address[1]
        server.RequestHandlerClass = ui.make_handler(self.project, 'fixture-token', port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def close():
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        self.addCleanup(close)
        return port

    def get(self, port, path, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            conn.request('GET', path, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_authentication_host_and_secret_filter(self):
        port = self.server()
        self.assertEqual(self.get(port, '/api/state')[0], 403)
        self.assertEqual(self.get(port, '/api/state?token=wrong')[0], 403)
        self.assertEqual(self.get(port, '/api/state?token=fixture-token', {'Host': 'invalid.example'})[0], 403)
        status, data = self.get(port, '/api/state', {'X-Token': 'fixture-token'})
        self.assertEqual(status, 200)
        self.assertNotIn(b'fixture-secret-token', data)
        self.assertNotIn(b'NOVELAI_API_KEY', data)
        self.assertEqual([v['name'] for v in json.loads(data)['variables']], ['NOVELAI_CHAR_TEST'])

    def test_image_access_rejects_normalized_private_paths(self):
        self.write('output/preview.png')
        self.write('.secrets/private.png')
        port = self.server()
        def read(path):
            return self.get(port, '/file?' + urlencode({'path': path, 'token': 'fixture-token'}))[0]
        self.assertEqual(read('output/preview.png'), 200)
        for path in ('.secrets/private.png', 'output/../.secrets/private.png',
                     'input/../.secrets/private.png', 'output/..\\.secrets\\private.png', '../outside.png', '.env'):
            with self.subTest(path=path):
                self.assertNotEqual(read(path), 200)

    def test_post_requires_token_and_json(self):
        port = self.server()
        for headers in ({'Content-Type': 'application/json'}, {'X-Token': 'fixture-token', 'Content-Type': 'text/plain'}):
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            try:
                conn.request('POST', '/api/run', '{}', headers)
                result = conn.getresponse()
                self.assertEqual(result.status, 403)
                result.read()
            finally:
                conn.close()
        self.assertIsNone(self.project.job)

    def test_cost_confirmation_and_command_allowlist(self):
        body = {'ids': ['p01-01'], 'seed': 'auto', 'execute': True}
        for extra in ({}, {'confirm_zero_anlas': True}, {'cost_note': 'テスト用の確認'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.project.command('generate', {**body, **extra})
        args = self.project.command('generate', {**body, 'confirm_zero_anlas': True,
            'cost_note': 'テスト用の確認', 'confirm_v5_allowance': True, 'allow_anlas': True})
        self.assertIn('--confirm-zero-anlas', args)
        self.assertIn('--confirm-v5-allowance', args)
        self.assertNotIn('--allow-anlas', args)
        for action, data in [('shell', {}), ('env-set', {'name': 'NOVELAI_API_KEY', 'value': 'test'}),
                             ('generate', {'ids': ['../bad'], 'seed': 'auto'}),
                             ('generate', {'ids': ['p01-01'], 'seed': 'auto', 'max': 1001})]:
            with self.subTest(action=action, data=data), self.assertRaises(ValueError):
                self.project.command(action, data)

    def test_json_backup_and_invalid_request_leave_file_unchanged(self):
        data = {'input': '1girl', 'parameters': {}}
        self.project.save_request('p01-01', data)
        self.project.save_request('p01-01', {**data, 'input': '1boy'})
        history = list((self.root / 'output/webui/history').glob('*.json'))
        self.assertEqual(len(history), 1)
        self.assertEqual(json.loads(history[0].read_text(encoding='utf-8')), data)
        with self.assertRaises(ValueError):
            self.project.save_request('../outside', data)
        with self.assertRaises(ValueError):
            self.project.save_request('p01-01', {'input': 1})
        self.assertEqual(self.project.request('p01-01')['raw']['input'], '1boy')

    def reference_request(self, references=None, **parameters):
        params = {'width': 832, 'height': 1216, 'steps': 23, 'seed': 1, 'sampler': 'k_euler_ancestral', 'scale': 5, **parameters}
        if references is not None:
            params['precise_references'] = references
        return {'action': 'generate', 'input': '1girl', 'model': 'nai-diffusion-5-curated', 'parameters': params}

    MIO = {'type': 'character', 'path': 'input/novelai/references/mio-v1.png', 'strength': 1}

    def test_references_are_validated_and_listed(self):
        self.write('input/novelai/references/mio-v1.png')
        self.write('assets/characters/mio.png')
        self.project.save_request('p01-01', self.reference_request([{**self.MIO, 'path': 'input\\novelai\\references\\mio-v1.png'},
                                                                    {'type': 'outfit', 'path': 'assets/characters/mio.png'}]))
        self.project.save_request('p01-02', self.reference_request())
        saved = self.project.request('p01-01')['raw']['parameters']['precise_references']
        self.assertEqual(saved[0]['path'], 'input/novelai/references/mio-v1.png')
        state = self.project.state()
        self.assertEqual({r['id']: r['references'] for r in state['requests']}, {'p01-01': 2, 'p01-02': 0})
        self.assertEqual(state['reference']['images'], ['input/novelai/references/mio-v1.png', 'assets/characters/mio.png'])
        self.assertEqual(state['reference']['anlas'], 5)
        self.assertTrue(state['reference']['paid'])
        port = self.server()
        self.assertEqual(self.get(port, '/file?' + urlencode({'path': 'assets/characters/mio.png', 'token': 'fixture-token'}))[0], 200)
        for references in ([], [{**self.MIO, 'type': 'unknown'}], [{**self.MIO, 'strength': 6}], [{**self.MIO, 'strength': True}],
                           [{**self.MIO, 'path': ''}], [{**self.MIO, 'path': '../mio.png'}], [{**self.MIO, 'path': '.secrets/private.png'}],
                           [{**self.MIO, 'path': 'input/key.env'}], [{**self.MIO, 'extra': 1}], 'mio'):
            with self.subTest(references=references), self.assertRaises(ValueError):
                self.project.save_request('p01-01', self.reference_request(references))
        with self.assertRaises(ValueError):
            self.project.save_request('p01-01', {**self.reference_request([self.MIO]), 'model': 'nai-diffusion-4-5-full'})
        self.assertEqual(self.project.request('p01-01')['raw']['parameters']['precise_references'], saved)

    def test_reference_image_candidates_cover_input_and_assets_and_refresh_on_request(self):
        for name in ('input/novelai/references/b.png', 'input/pages/a.JPG', 'assets/characters/mio.webp', 'assets/fonts/font.ttf',
                     'input/.hidden/x.png', 'assets/.x.png', 'output/novelai/candidates/p01-01/r001.png', 'templates/onomatopoeia/a.png'):
            self.write(name)
        # ページに属さない要求（人物試作など）の採用画像は候補に加える。ページのコマの採用画像と未採用の候補は加えない
        self.write('output/novelai/candidates/chara-mio/r001.png')
        self.write('output/novelai/candidates/chara-mio/r002.png')
        for request_id in ('chara-mio', 'chara-rin', 'p01-01'):
            self.project.save_request(request_id, self.reference_request())
        self.project.batch.adopt(self.root, 'chara-mio', 1, None)
        self.project.batch.adopt(self.root, 'p01-01', 1, None)
        trial = 'output/novelai/candidates/chara-mio/r001.png'
        expected = ['input/novelai/references/b.png', 'input/pages/a.JPG', 'assets/characters/mio.webp']
        self.assertEqual(self.project.state()['reference']['images'], [*expected, trial])
        # 採用し直すと次の表示から反映する（更新ボタンは不要）
        self.project.batch.adopt(self.root, 'chara-mio', 2, None)
        trial = 'output/novelai/candidates/chara-mio/r002.png'
        self.assertEqual(self.project.state()['reference']['images'], [*expected, trial])
        # 追加したファイルは「候補画像を更新」（POST /api/reference-images）で取り直すまで出ない
        self.write('assets/references/new.png')
        self.assertEqual(self.project.state()['reference']['images'], [*expected, trial])
        port = self.server()
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            conn.request('POST', '/api/reference-images', '{}', {'X-Token': 'fixture-token', 'Content-Type': 'application/json'})
            result = conn.getresponse()
            self.assertEqual(result.status, 200)
            refreshed = json.loads(result.read())['images']
        finally:
            conn.close()
        self.assertEqual(refreshed, [*expected, 'assets/references/new.png', trial])
        self.assertEqual(self.project.state()['reference']['images'], refreshed)

    STYLE = {'path': 'input/novelai/references/style-v1.png', 'strength': 1.5}

    def test_style_default_is_added_unless_the_panel_specifies_a_style(self):
        self.project.save_request('p01-01', self.reference_request())
        self.project.save_request('p01-02', self.reference_request([{**self.MIO, 'type': 'style', 'path': 'input/novelai/references/own.png'}]))
        self.project.save_request('p01-03', self.reference_request([self.MIO]))
        self.project.save_request('p01-04', {**self.reference_request(), 'model': 'nai-diffusion-4-5-full'})
        self.project.save_request('p01-05', self.reference_request([{**self.MIO, 'type': 'character-and-style'}]))
        self.assertEqual(self.project.state()['reference']['defaults'], {'supported': True, 'style': None})
        self.project.save_reference_defaults(self.STYLE)
        saved = json.loads((self.root / 'input/novelai/reference-defaults.json').read_text(encoding='utf-8'))
        self.assertEqual(saved, {'schema_version': 1, 'style': self.STYLE})
        state = {r['id']: (r['references'], r['style']) for r in self.project.state()['requests']}
        self.assertEqual(state, {'p01-01': (1, 'default'), 'p01-02': (1, 'own'), 'p01-03': (2, 'default'), 'p01-04': (0, 'none'), 'p01-05': (1, 'own')})
        # 生成で送る内容（novelai_batch.resolved_request）にも同じ規則で足される。要求JSON自体は書き換えない
        variables = self.project.batch.read_variables(self.root)
        resolved = {i: self.project.batch.resolved_request(self.root, i, variables)[0]['parameters'].get('precise_references')
                    for i in ('p01-01', 'p01-02', 'p01-03', 'p01-04')}
        style = {'type': 'style', **self.STYLE}
        self.assertEqual(resolved['p01-01'], [style])
        self.assertEqual(resolved['p01-02'][0]['path'], 'input/novelai/references/own.png')
        self.assertEqual(resolved['p01-03'], [style, self.MIO])
        self.assertIsNone(resolved['p01-04'])
        self.assertNotIn('precise_references', self.project.request('p01-01')['raw']['parameters'])
        # 既定の絵柄を使うコマは参照付きの扱いになり、0 Anlasの生成には含められない
        zero = {'seed': 'auto', 'execute': True, 'confirm_zero_anlas': True, 'confirm_v5_allowance': True, 'cost_note': '確認'}
        with self.assertRaises(ValueError):
            self.project.command('generate', {**zero, 'ids': ['p01-01']})
        args = self.project.command('generate', {**zero, 'pages': [1], 'scope': 'plain'})
        self.assertEqual(args[args.index('--ids') + 1], 'p01-04')
        paid = {'seed': 'auto', 'execute': True, 'scope': 'reference', 'allow_reference_anlas': True, 'confirm_v5_allowance': True, 'cost_note': '許可'}
        with self.assertRaises(ValueError):  # p01-03 は既定の絵柄と合わせて2枚（10 Anlas）
            self.project.command('generate', {**paid, 'ids': ['p01-03'], 'anlas_limit': 9})
        self.project.command('generate', {**paid, 'ids': ['p01-03'], 'anlas_limit': 10})
        for style in ({**self.STYLE, 'strength': 6}, {**self.STYLE, 'path': '../style.png'}, {**self.STYLE, 'type': 'style'}, {'path': ''}, 'style'):
            with self.subTest(style=style), self.assertRaises(ValueError):
                self.project.save_reference_defaults(style)
        self.project.save_reference_defaults(None)
        self.assertEqual(self.project.state()['requests'][0]['references'], 0)
        self.assertEqual(len(list((self.root / 'output/webui/history').glob('novelai-reference-defaults-*.json'))), 1)

    def test_character_and_outfit_images_are_replaced_per_image_with_merge_confirmation(self):
        other = {**self.MIO, 'path': 'input/novelai/references/rin-v1.png'}
        wear = {'type': 'outfit', 'path': 'input/novelai/references/uniform.png', 'strength': 1}
        self.project.save_request('p01-01', self.reference_request([self.MIO, wear]))
        self.project.save_request('p01-02', self.reference_request([{**self.MIO, 'type': 'character-and-style'}, other]))
        self.project.save_request('p01-03', self.reference_request([other]))
        groups = self.project.reference_groups('character')
        self.assertEqual([(g['path'], g['types'], g['ids']) for g in groups],
                         [('input/novelai/references/mio-v1.png', ['character', 'character-and-style'], ['p01-01', 'p01-02']),
                          ('input/novelai/references/rin-v1.png', ['character'], ['p01-02', 'p01-03'])])
        self.assertEqual([g['path'] for g in self.project.reference_groups('outfit')], ['input/novelai/references/uniform.png'])
        # 置換後に別の画像と同じになる（区別がつかなくなる）場合は、確認（merge_ok）がなければ書き換えない
        merge = {'kind': 'character', 'mapping': {'input/novelai/references/mio-v1.png': 'input/novelai/references/rin-v1.png'}}
        with self.assertRaises(ValueError):
            self.project.replace_references(merge)
        self.assertEqual(self.project.request('p01-01')['raw']['parameters']['precise_references'][0], self.MIO)
        for body in ({'kind': 'style', 'mapping': {}}, {'kind': 'character', 'mapping': {'input/novelai/references/none.png': 'x.png'}},
                     {'kind': 'character', 'mapping': {'input/novelai/references/mio-v1.png': '../mio.png'}},
                     {'kind': 'character', 'mapping': {'input/novelai/references/mio-v1.png': ' '}}, {'kind': 'character', 'mapping': []}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.project.replace_references(body)
        # 入れ替え（mio → mio-v2、rin はそのまま）は確認なしで置換し、衣装は変えない
        result = self.project.replace_references({'kind': 'character', 'mapping': {'input/novelai/references/mio-v1.png': 'input\\novelai\\references\\mio-v2.png',
                                                                                   'input/novelai/references/rin-v1.png': ''}})
        self.assertEqual(result['changed'], {'p01-01': 1, 'p01-02': 1})
        refs = {i: self.project.request(i)['raw']['parameters']['precise_references'] for i in ('p01-01', 'p01-02', 'p01-03')}
        self.assertEqual(refs['p01-01'], [{**self.MIO, 'path': 'input/novelai/references/mio-v2.png'}, wear])
        self.assertEqual(refs['p01-02'], [{**self.MIO, 'type': 'character-and-style', 'path': 'input/novelai/references/mio-v2.png'}, other])
        self.assertEqual(refs['p01-03'], [other])
        result = self.project.replace_references({**merge, 'mapping': {'input/novelai/references/mio-v2.png': 'input/novelai/references/rin-v1.png'}, 'merge_ok': True})
        self.assertEqual([g['path'] for g in result['groups']], ['input/novelai/references/rin-v1.png'])
        self.project.job = {'state': 'running'}
        with self.assertRaises(ValueError):
            self.project.replace_references({'kind': 'outfit', 'mapping': {wear['path']: 'assets/wear.png'}})

    def test_scripts_without_references_keep_the_request_and_hide_the_feature(self):
        with patch.object(self.project.batch.api, 'PRECISE_REFERENCE_TYPES', {}):
            self.assertEqual(self.project.reference_spec()['types'], [])
            self.project.save_request('p01-01', self.reference_request([{'type': 'future', 'path': 'x'}]))
        self.assertEqual(self.project.request('p01-01')['raw']['parameters']['precise_references'], [{'type': 'future', 'path': 'x'}])

    def test_reference_generation_needs_explicit_range_and_limit(self):
        self.project.save_request('p01-01', self.reference_request([self.MIO, {**self.MIO, 'type': 'style'}]))
        self.project.save_request('p01-02', self.reference_request())
        self.project.save_request('p02-01', self.reference_request([self.MIO]))
        zero = {'seed': 'auto', 'execute': True, 'confirm_zero_anlas': True, 'confirm_v5_allowance': True, 'cost_note': '確認'}
        # 0 Anlasの生成には参照付きのコマを混ぜない。参照なしだけに絞れば送れる
        with self.assertRaises(ValueError):
            self.project.command('generate', {**zero, 'pages': [1]})
        args = self.project.command('generate', {**zero, 'pages': [1], 'scope': 'plain'})
        self.assertEqual(args[args.index('--ids') + 1], 'p01-02')
        self.assertNotIn('--allow-anlas', args)
        paid = {'seed': 'auto', 'execute': True, 'scope': 'reference', 'allow_reference_anlas': True, 'anlas_limit': 15,
                'confirm_v5_allowance': True, 'cost_note': '利用者が今回の3枚分を許可'}
        args = self.project.command('generate', {**paid, 'all': True})
        self.assertEqual(args[args.index('--ids') + 1], 'p01-01,p02-01')
        self.assertIn('--allow-anlas', args)
        self.assertIn('--confirm-v5-allowance', args)
        self.assertNotIn('--confirm-zero-anlas', args)
        self.assertIn('15 Anlas', args[args.index('--cost-note') + 1])
        for change in ({'allow_reference_anlas': False}, {'allow_reference_anlas': 'true'}, {'confirm_v5_allowance': False},
                       {'cost_note': ' '}, {'anlas_limit': 14}, {'anlas_limit': 0}, {'anlas_limit': '15'}, {'anlas_limit': None},
                       {'max': 1}, {'scope': 'other'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.project.command('generate', {**paid, 'all': True, **change})
        with self.assertRaises(ValueError):
            self.project.command('generate', {**paid, 'ids': ['p01-02']})
        # 送信なしの確認は、参照付きでもそのまま行える
        self.assertNotIn('--execute', self.project.command('generate', {'pages': [1], 'seed': 'auto'}))

    def test_reference_generation_rejects_other_paid_conditions_and_old_scripts(self):
        paid = {'seed': 'auto', 'execute': True, 'scope': 'reference', 'allow_reference_anlas': True, 'anlas_limit': 100,
                'confirm_v5_allowance': True, 'cost_note': '許可', 'ids': ['p01-01']}
        for parameters in ({'steps': 29}, {'width': 1216, 'height': 1216}, {'n_samples': 2}, {'image': 'fixture'},
                           {'director_reference_images': ['fixture']}):
            self.project.save_request('p01-01', self.reference_request([self.MIO], **parameters))
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                self.project.command('generate', paid)
        self.project.save_request('p01-01', self.reference_request([self.MIO]))
        self.project.command('generate', paid)
        guard = self.project.batch.api.expects_free_base
        del self.project.batch.api.expects_free_base
        try:
            with self.assertRaises(ValueError):
                self.project.command('generate', paid)
        finally:
            self.project.batch.api.expects_free_base = guard

    def test_discard_restore_two_archives_does_not_conflict_on_metadata(self):
        base = 'output/novelai/candidates/p01-01'
        for number in (1, 2):
            folder = f'{base}/discarded/archive-{number}'
            self.write(f'{folder}/r{number:03d}.png')
            self.write(f'{folder}/moved.json', b'{}')
            self.project.move({'id': 'p01-01', 'kind': 'novelai', 'action': 'restore', 'folder': folder})
        self.assertTrue((self.root / base / 'r001.png').is_file())
        self.assertTrue((self.root / base / 'r002.png').is_file())
        self.assertFalse((self.root / base / 'moved.json').exists())

    def test_same_second_moves_preserve_individual_records(self):
        base = 'output/novelai/candidates/p01-01'
        for number in (1, 2):
            self.write(f'{base}/r{number:03d}.png')
        with patch.object(ui, 'datetime') as clock:
            clock.now.return_value.strftime.return_value = 'fixed-time'
            clock.now.return_value.isoformat.return_value = 'fixed-time'
            for number in (1, 2):
                self.project.move({'id': 'p01-01', 'kind': 'novelai', 'action': 'discard', 'n': number})
        records = list((self.root / base / 'discarded').glob('*/moved.json'))
        self.assertEqual(len(records), 2)
        self.assertEqual({json.loads(p.read_text(encoding='utf-8'))['number'] for p in records}, {1, 2})

    def test_organizing_requires_idle_and_unknown_confirmation(self):
        self.write('output/novelai/candidates/p01-01/r001.novelai.json', b'{}')
        body = {'id': 'p01-01', 'kind': 'novelai', 'action': 'move-unknown', 'n': 1}
        with self.assertRaises(ValueError):
            self.project.move(body)
        self.project.job = {'state': 'running'}
        with self.assertRaises(ValueError):
            self.project.move({**body, 'confirmed': True})
        self.project.job = None
        self.project.move({**body, 'confirmed': True})
        self.assertFalse((self.root / 'output/novelai/candidates/p01-01/r001.novelai.json').exists())

    def test_lora_mode_is_removed(self):
        # NovelAIはLoRAを指定できないため、LoRA適用モードの操作・画面は持たない
        for action in ('lora', 'adopt-file'):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.project.command(action, {'all': True, 'ids': ['p01-01'], 'path': 'output/lora/p01-01/l001.png'})
        self.assertNotIn('lora', self.project.state())
        self.assertNotIn('LoRA', ui.PAGE)
        self.assertFalse((SKILL / 'lora_run.py').exists())
        self.assertFalse((SKILL / 'lora_apply.py').exists())

    @unittest.skipUnless(shutil.which('node'), 'JavaScriptの構文と保存失敗の確認にはNode.jsが必要')
    def test_javascript_syntax_and_failed_save_blocks_generation(self):
        script = ui.PAGE.split('<script>', 1)[1].split('</script>', 1)[0]
        source = self.root / 'webui.js'
        source.write_text(script, encoding='utf-8')
        result = subprocess.run(['node', '--check', str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        save = script.split('  async function save(id = ', 1)[1].split('\n', 1)[0]
        # 保存して生成ボタンに実際に設定されたコールバックを評価する。
        import re
        callback = re.search(r"h\('button', \{onclick: (async \(\) => \{[^\n]+?)\}, '保存して生成…'", script).group(1)
        scenario = """const assert = require('node:assert/strict');
let dialogs = 0, alerts = 0, failure = true;
const sel = {panel: 'p01-01'}, collect = () => ({}), refresh = async () => {};
const api = async () => { if (failure) throw new Error('fixture failure'); };
const alert = () => { alerts++; }, generateDialog = () => { dialogs++; };
""" + 'async function save(id = ' + save + '\n' + 'const click = ' + callback + ';\n' + """
(async () => { await click(); assert.equal(alerts, 1); assert.equal(dialogs, 0);
failure = false; await click(); assert.equal(dialogs, 1); })().catch(e => { console.error(e); process.exitCode = 1; });
"""
        source.write_text(scenario, encoding='utf-8')
        result = subprocess.run(['node', str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('node'), '画面の精密参照の編集と生成画面の確認にはNode.jsが必要')
    def test_javascript_edits_references_and_separates_paid_generation(self):
        self.project.save_request('p01-01', self.reference_request([self.MIO]))
        self.project.save_request('p01-02', self.reference_request())
        self.project.save_request('p02-01', self.reference_request([{**self.MIO, 'path': 'input/novelai/references/rin-v1.png'}]))
        fixture = {'state': self.project.state(), 'request': self.project.request('p01-01'), 'groups': self.project.reference_groups('character')}
        script = ui.PAGE.split('<script>', 1)[1].split('</script>', 1)[0]
        source = self.root / 'references.js'
        source.write_text(FAKE_DOM.replace('__FIXTURE__', json.dumps(fixture)) + script + SCENARIO, encoding='utf-8')
        result = subprocess.run(['node', str(source)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)


# 画面のスクリプトを、ブラウザーを使わず最小限の要素だけで動かす。
FAKE_DOM = """const assert = require('node:assert/strict');
const FIXTURE = __FIXTURE__, posts = [];
class Node {}
class El extends Node { constructor(tag) { super(); this.tag = tag; this.kids = []; this.attrs = {}; this.style = {}; this.dataset = {}; this._value = undefined; this.checked = false; this.hidden = false;
    this.classList = {toggle() {}}; this.returnValue = ''; }
  get value() { return this._value ?? (this.tag === 'option' ? this.attrs.value : ''); } set value(v) { this._value = String(v); }
  setAttribute(k, v) { this.attrs[k] = v; if (k === 'value') this._value = String(v); }
  append(...k) { for (const x of k) { if (x instanceof El) x.parent = this; this.kids.push(x); } } replaceChildren(...k) { this.kids = []; this.append(...k.filter(x => x !== null && x !== undefined)); }
  remove() { if (this.parent) this.parent.kids = this.parent.kids.filter(x => x !== this); } cloneNode() { return new El(this.tag); } showModal() { this.open = true; } close() {}
  get textContent() { return this.kids.map(k => k instanceof El ? k.textContent : k.text).join(''); } set textContent(t) { this.kids = [{text: String(t)}]; }
  all(test, found = []) { for (const k of this.kids) if (k instanceof El) { if (test(k)) found.push(k); k.all(test, found); } return found; } }
const byId = {}, fields = {}, el = id => byId[id] ||= new El(id);
for (const n of ['seed', 'max', 'confirm_zero_anlas', 'confirm_v5_allowance', 'accept_warnings', 'cost_note', 'scope', 'allow_reference_anlas', 'anlas_limit', 'remember_reference']) fields[n] = new El('input');
el('#genform').elements = {namedItem: n => fields[n]};
global.Node = Node; global.document = {createElement: t => new El(t), createTextNode: t => Object.assign(new Node(), {text: t}), querySelector: el, querySelectorAll: () => []};
const memory = {}; global.localStorage = {get length() { return Object.keys(memory).length; }, key: i => Object.keys(memory)[i], getItem: k => k in memory ? memory[k] : null,
  setItem: (k, v) => { memory[k] = String(v); }, removeItem: k => { delete memory[k]; }}; global.alert = m => { throw new Error('alert: ' + m); }; global.confirm = () => false;
global.fetch = async (url, opt = {}) => { let data = {ok: true};
  if (opt.method === 'POST') { posts.push([url.split('?')[0], JSON.parse(opt.body)]); if (url.startsWith('/api/run')) data = {action: 'generate', state: 'done', log: ''};
    if (url.startsWith('/api/reference-images')) data = {images: ['input/novelai/references/mio-v1.png', 'assets/added.png']}; }
  else if (url.startsWith('/api/references/groups')) data = FIXTURE.groups; else if (url.startsWith('/api/state')) data = FIXTURE.state; else if (url.startsWith('/api/request')) data = FIXTURE.request; else if (url.startsWith('/api/job')) data = null;
  return {ok: true, json: async () => JSON.parse(JSON.stringify(data))}; };
"""
SCENARIO = """
const settle = () => new Promise(r => setTimeout(r, 20));
(async () => { await settle(); sel.panel = 'p01-01'; await viewPanel(); const v = el('#view');
  const button = text => v.all(e => e.tag === 'button' && e.textContent === text)[0];
  assert.match(v.textContent, /参照画像1枚：１枚生成するごとに追加 5 Anlas/);
  button('参照を追加').onclick(); assert.match(v.textContent, /参照画像2枚：１枚生成するごとに追加 10 Anlas/);
  const paths = v.all(e => e.attrs.list === 'refimages'), types = v.all(e => e.tag === 'select');
  // 保存済みの参照は、そのパスを例として表示する。新しく足した行は従来の例のまま
  assert.equal(paths[0].attrs.placeholder, 'input/novelai/references/mio-v1.png'); assert.match(paths[1].attrs.placeholder, /^例 /);
  // 「候補画像を更新」は候補の一覧だけを取り直し、編集中の欄は作り直さない
  await el('#refimgs').onclick(); assert.equal(posts.pop()[0], '/api/reference-images');
  assert.deepEqual(el('#refimages').kids.map(k => k.attrs.value), ['input/novelai/references/mio-v1.png', 'assets/added.png']);
  assert.equal(el('#refimgsinfo').textContent, '候補 2件'); assert.equal(v.all(e => e.attrs.list === 'refimages')[1], paths[1]);
  paths[1].value = 'input/novelai/references/wear.png'; types[1].value = 'outfit';
  await button('保存').onclick(); await settle();
  assert.deepEqual(posts.pop()[1].data.parameters.precise_references, [{type: 'character', path: 'input/novelai/references/mio-v1.png', strength: 1},
    {type: 'outfit', path: 'input/novelai/references/wear.png', strength: 1}]);
  await viewPanel(); v.all(e => e.tag === 'button' && e.textContent === '外す').forEach(b => b.onclick());
  assert.match(v.textContent, /参照なし/); await button('保存').onclick(); await settle();
  assert.equal('precise_references' in posts.pop()[1].data.parameters, false);
  // 参照なしと参照付きが混ざるページ：既定は参照なし。参照付きを選ぶと許可と上限の欄へ切り替わる
  fields.allow_reference_anlas.checked = true; generateDialog({pages: [1]}, '1ページ');
  assert.equal(fields.allow_reference_anlas.checked, false); assert.match(el('#genrefs').textContent, /参照なし 1件／精密参照付き 1件（参照画像 のべ1枚・追加 5 Anlas/);
  assert.equal(el('#genpaid').hidden, true); assert.equal(el('#genzero').hidden, false); assert.equal(el('#genscope').hidden, false);
  fields.scope.value = 'reference'; fields.scope.onchange(); assert.equal(el('#genpaid').hidden, false); assert.equal(el('#genzero').hidden, true);
  fields.confirm_zero_anlas.checked = true; fields.confirm_v5_allowance.checked = true; fields.allow_reference_anlas.checked = true; fields.anlas_limit.value = '5'; fields.cost_note.value = '許可';
  el('#gen').returnValue = 'exec'; el('#gen').onclose(); await settle();
  const sent = posts.pop()[1]; assert.equal(sent.scope, 'reference'); assert.equal(sent.confirm_zero_anlas, false); assert.equal(sent.allow_reference_anlas, true); assert.equal(sent.anlas_limit, 5);
  generateDialog({ids: ['p01-02']}, 'p01-02'); assert.equal(el('#genscope').hidden, true); assert.equal(el('#genpaid').hidden, true);
  el('#gen').returnValue = 'exec'; el('#gen').onclose(); await settle();
  const plain = posts.pop()[1]; assert.equal(plain.scope, 'all'); assert.equal('allow_reference_anlas' in plain, false);
  // 「精密参照の入力内容を記憶」：ONで閉じると許可と上限Anlasを次回も入れておく。OFFで閉じると記憶を消す
  generateDialog({pages: [1]}, '1ページ'); assert.equal(fields.remember_reference.checked, false); assert.equal(fields.allow_reference_anlas.checked, false);
  fields.scope.value = 'reference'; fields.scope.onchange(); fields.allow_reference_anlas.checked = true; fields.anlas_limit.value = '5'; fields.remember_reference.checked = true;
  el('#gen').returnValue = 'dry'; el('#gen').onclose(); await settle(); posts.pop();
  fields.allow_reference_anlas.checked = false; fields.anlas_limit.value = ''; fields.remember_reference.checked = false;
  generateDialog({pages: [1]}, '1ページ'); assert.equal(fields.remember_reference.checked, true); assert.equal(fields.allow_reference_anlas.checked, true); assert.equal(fields.anlas_limit.value, '5');
  fields.scope.value = 'reference'; fields.remember_reference.checked = false; el('#gen').returnValue = 'exec'; el('#gen').onclose(); await settle();
  assert.equal(posts.pop()[1].allow_reference_anlas, true);
  generateDialog({pages: [1]}, '1ページ'); assert.equal(fields.remember_reference.checked, false); assert.equal(fields.allow_reference_anlas.checked, false); assert.equal(fields.anlas_limit.value, '');
  // 変数タブの下部：既定の絵柄の保存と、キャラ画像の一覧からの置換
  tab = 'vars'; render(); const w = el('#view'), wbutton = text => w.all(e => e.tag === 'button' && e.textContent === text)[0];
  const style = w.all(e => e.attrs.list === 'refimages')[0]; assert.match(style.attrs.placeholder, /^例 /);
  style.value = 'input/novelai/references/style-v1.png'; await wbutton('既定の絵柄を保存').onclick(); await settle();
  assert.deepEqual(posts.pop(), ['/api/reference-defaults', {style: {path: 'input/novelai/references/style-v1.png', strength: 1}}]);
  tab = 'vars'; render(); let asked = 0; global.confirm = () => { asked++; return true; };
  await w.all(e => e.tag === 'button' && e.textContent === 'キャラ画像一覧表示')[0].onclick();
  const target = w.all(e => e.attrs.list === 'refimages' && e.attrs.placeholder === 'input/novelai/references/mio-v1.png')[0];
  assert.match(w.textContent, /使うコマ（1件）：p02-01/);
  const warn = w.all(e => e.className === 'err' && /キャラを大きく変えた場合は/.test(e.textContent))[0]; assert.equal(warn.attrs.style, 'font-weight:bold');
  target.value = 'input/novelai/references/rin-v1.png'; await w.all(e => e.tag === 'button' && e.textContent === 'キャラの画像を置換')[0].onclick(); await settle();
  assert.equal(asked, 1); assert.deepEqual(posts.pop(), ['/api/references/replace', {kind: 'character', mapping: {'input/novelai/references/mio-v1.png': 'input/novelai/references/rin-v1.png'}, merge_ok: true}]);
  global.confirm = () => false;
})().catch(e => { console.error(e); process.exitCode = 1; });
"""


if __name__ == '__main__':
    unittest.main()
