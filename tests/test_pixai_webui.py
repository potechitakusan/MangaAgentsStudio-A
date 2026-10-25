"""PixAIのWebUIをダミー作品とループバック通信だけで検証する。ブラウザー・外部APIは使わない。"""
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
SKILL = ROOT / 'skills/pixai-batch-webui'
sys.path.insert(0, str(ROOT / 'templates/manga-project/scripts'))
spec = importlib.util.spec_from_file_location('pixai_webui', SKILL / 'pixai_webui.py')
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)

REQUEST = {'api': 'v2', 'body': {'modelVersionId': '1983308862240288769', 'prompt': '1girl, ${PIXAI_CHAR_TEST}', 'aspectRatio': '2:3'}}


class PixaiWebUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pixai-webui-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'project.json').write_text('{"name":"テスト作品"}', encoding='utf-8')
        (self.root / '.env').write_text('PIXAI_API_KEY=fixture-secret-token\n', encoding='utf-8')
        (self.root / '.env.pixai').write_text('PIXAI_CHAR_TEST="short hair"\n', encoding='utf-8')
        self.project = ui.Project(self.root)
        self.network = patch.object(self.project.api, 'api_request', side_effect=AssertionError('外部通信は禁止'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.project.save_request('p01-01', REQUEST)

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

    def test_authentication_state_and_secret_filter(self):
        port = self.server()
        self.assertEqual(self.get(port, '/api/state')[0], 403)
        self.assertEqual(self.get(port, '/api/state?token=fixture-token', {'Host': 'invalid.example'})[0], 403)
        status, data = self.get(port, '/api/state', {'X-Token': 'fixture-token'})
        self.assertEqual(status, 200)
        self.assertNotIn(b'fixture-secret-token', data)
        state = json.loads(data)
        self.assertEqual([v['name'] for v in state['variables']], ['PIXAI_CHAR_TEST'])
        self.assertEqual(state['requests'][0]['api'], 'v2')
        self.assertIn('moe-pastel', state['options']['styles'])
        detail = self.project.request('p01-01')
        self.assertEqual(detail['resolved']['body']['prompt'], '1girl, short hair')

    def test_image_access_rejects_private_paths(self):
        for name in ('output/preview.png', '.secrets/private.png'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
        port = self.server()
        read = lambda p: self.get(port, '/file?' + urlencode({'path': p, 'token': 'fixture-token'}))[0]
        self.assertEqual(read('output/preview.png'), 200)
        for path in ('.secrets/private.png', 'output/../.secrets/private.png', '../outside.png', '.env', '.env.pixai'):
            with self.subTest(path=path):
                self.assertNotEqual(read(path), 200)

    def test_credit_confirmation_and_command_allowlist(self):
        body = {'ids': ['p01-01'], 'seed': 'auto', 'execute': True}
        for extra in ({}, {'confirm_credits': True}, {'cost_note': '許可した範囲'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.project.command('generate', {**body, **extra})
        args = self.project.command('generate', {**body, 'confirm_credits': True, 'cost_note': '許可した範囲', 'allow_unverified': True})
        self.assertEqual(args[:2], ['scripts/pixai_batch.py', 'generate'])
        self.assertIn('--confirm-credits', args)
        self.assertIn('--allow-unverified', args)
        self.assertNotIn('--batch-size', args)  # 既定（自動）は引数を足さない
        args = self.project.command('generate', {**body, 'confirm_credits': True, 'cost_note': '許可した範囲', 'batch_size': '4'})
        self.assertEqual(args[args.index('--batch-size') + 1], '4')
        with self.assertRaises(ValueError):
            self.project.command('generate', {**body, 'confirm_credits': True, 'cost_note': '許可した範囲', 'batch_size': '2'})
        self.assertEqual(self.project.command('fetch', {'ids': ['p01-01']}), ['scripts/pixai_batch.py', 'fetch', '--ids', 'p01-01'])
        self.assertEqual(self.project.command('status', {}), ['scripts/pixai_api.py', 'status'])
        for action, data in [('shell', {}), ('lora', {'all': True}), ('env-set', {'name': 'PIXAI_API_KEY', 'value': 'x'}),
                             ('env-set', {'name': 'NOVELAI_CHAR_X', 'value': 'x'}), ('generate', {'ids': ['../bad'], 'seed': 'auto'})]:
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.project.command(action, data)

    def test_request_shape_validation_and_backup(self):
        self.project.save_request('p01-01', {**REQUEST, 'body': {**REQUEST['body'], 'prompt': '1boy'}})
        self.assertEqual(len(list((self.root / 'output/webui-pixai/history').glob('*.json'))), 1)
        for data in ({'input': '1girl', 'parameters': {}}, {'api': 'v2', 'body': {}}, {'api': 'v1', 'parameters': {'prompt': 'x'}}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.project.save_request('p01-01', data)
        self.project.save_request('p01-02', {'api': 'v1', 'parameters': {'prompts': 'x'}}, True)
        with self.assertRaises(ValueError):
            self.project.save_request('p01-02', {'api': 'v1', 'parameters': {'prompts': 'x'}}, True)

    def test_records_unknown_and_moves_require_confirmation(self):
        folder = self.root / 'output/pixai/candidates/p01-01'
        folder.mkdir(parents=True)
        (folder / 'r001.pixai.json').write_text(json.dumps({'status': '完了待ち', 'taskId': '42'}), encoding='utf-8')
        found = self.project.scan_unknown()
        self.assertEqual(found, [{'id': 'p01-01', 'n': 1, 'status': '完了待ち', 'taskId': '42'}])
        with self.assertRaises(ValueError):
            self.project.move({'action': 'move-unknown', 'id': 'p01-01', 'n': 1})
        self.project.move({'action': 'move-unknown', 'id': 'p01-01', 'n': 1, 'confirmed': True})
        self.assertEqual(self.project.scan_unknown(), [])
        self.assertEqual(len(list((folder / 'failed').iterdir())), 1)

    def test_partial_batch_is_shown_for_fetch(self):
        folder = self.root / 'output/pixai/candidates/p01-01'
        folder.mkdir(parents=True)
        (folder / 'r001.png').write_bytes(b'fixture')
        (folder / 'r001.pixai.json').write_text(json.dumps({'status': 'partial', 'taskId': '42', 'missingOutputs': ['r002.png']}), encoding='utf-8')
        entries = self.project.records('p01-01')['pixai']['entries']
        self.assertTrue(entries[0]['unknown'])
        self.assertEqual(self.project.scan_unknown()[0]['taskId'], '42')
        with self.assertRaises(ValueError):
            self.project.move({'action': 'move-unknown', 'id': 'p01-01', 'n': 1, 'confirmed': True})
        self.assertTrue((folder / 'r001.png').is_file())

    @unittest.skipUnless(shutil.which('node'), 'JavaScriptの構文確認にはNode.jsが必要')
    def test_javascript_syntax(self):
        source = self.root / 'webui.js'
        source.write_text(ui.PAGE.split('<script>', 1)[1].split('</script>', 1)[0], encoding='utf-8')
        result = subprocess.run(['node', '--check', str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
