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
from types import SimpleNamespace
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

    def test_lora_unimplemented_or_missing_check_stays_disabled(self):
        self.assertFalse(self.project.lora['ready'])
        with self.assertRaises(ValueError):
            self.project.set_lora_mode(True)
        with self.assertRaises(ValueError):
            self.project.command('lora', {'all': True})
        hook = SimpleNamespace(READY=True, NAME='fixture', apply=lambda job: None)
        with patch.object(self.project.lora_runner, 'load_hook', return_value=hook):
            self.assertFalse(self.project.lora_runner.readiness(self.root)[0])
        hook.check = lambda root: (False, '未準備')
        with patch.object(self.project.lora_runner, 'load_hook', return_value=hook):
            self.assertFalse(self.project.lora_runner.readiness(self.root)[0])
        hook.check = lambda root: (True, '準備済み')
        with patch.object(self.project.lora_runner, 'load_hook', return_value=hook):
            self.assertTrue(self.project.lora_runner.readiness(self.root)[0])

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


if __name__ == '__main__':
    unittest.main()
