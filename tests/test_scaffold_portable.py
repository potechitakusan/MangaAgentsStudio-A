"""Linux入口の限定検証。外部通信・画像生成・公開処理は実行しない。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from new_manga_project import create_project


class PortableScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='manga portable ')
        self.parent = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_dry_run_no_writes(self):
        result = create_project('星渡り Test', self.parent, what_if=True)
        self.assertTrue(result['WhatIf'])
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_full_scaffold_snapshot_and_defaults(self):
        result = create_project('星渡り Test', self.parent)
        project = Path(result['AbsolutePath'])
        data = json.loads((project / 'project.json').read_text())
        self.assertEqual(data['name'], '星渡り Test')
        self.assertEqual((project / data['sourceKitRelativePath']).resolve(), ROOT)
        self.assertFalse((project / 'CLAUDE.md').exists())
        self.assertEqual(data['agentMode'], 'Codex')
        self.assertFalse((project / 'GEMINI.md').exists())
        self.assertFalse((project / 'AGENT-MODE.md').exists())
        self.assertFalse((project / 'agent-modes').exists())
        self.assertEqual(len(list((project / '.agents/skills').iterdir())), 10)
        snapshot = json.loads((project / 'docs/distribution-snapshot.json').read_text())
        self.assertEqual(len(snapshot['files']), result['CopiedFiles'])
        for item in snapshot['files']:
            path = project / item['path']
            self.assertFalse(Path(item['path']).is_absolute())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item['sha256'], item['path'])
        for shell in ('Resolve-ReviewProfile.sh', 'Initialize-OptionalSkills.sh'):
            self.assertTrue(os.access(project / 'scripts' / shell, os.X_OK))
            # WindowsではPython入口を使い、POSIXシェルの検証と分ける。
            entry = shell if os.name != 'nt' else {'Resolve-ReviewProfile.sh': 'resolve_review_profile.py', 'Initialize-OptionalSkills.sh': 'initialize_optional_skills.py'}[shell]
            command = ['bash', str(project / 'scripts' / entry)] if os.name != 'nt' else [sys.executable, '-X', 'utf8', str(project / 'scripts' / entry)]
            run = subprocess.run(command, cwd=self.parent, text=True, capture_output=True, encoding='utf-8')
            self.assertEqual(run.returncode, 0, run.stderr)
            output = json.loads(run.stdout)
            if shell.startswith('Initialize'):
                self.assertEqual(output['status'], 'disabled')
        self.assertFalse((project / '.work/optional-skills').exists())
        manifest = json.loads((project / 'docs/knowledge/supervision/distribution.json').read_text())
        files = list((project / 'docs/knowledge/supervision').rglob('*'))
        self.assertEqual(sum(f.is_file() for f in files), len(manifest['files']) + 1)
        catalog = json.loads((project / 'templates/panel-templates/catalog.json').read_text())
        self.assertEqual(catalog['templateCount'], 79)
        for template in catalog['templates']:
            for asset in template['assets'].values():
                self.assertTrue((project / 'templates/panel-templates' / asset).is_file())

    def test_claude_and_explicit_empty_inheritance(self):
        first = Path(create_project('前作', self.parent)['AbsolutePath'])
        second = Path(create_project('続編', self.parent, first, 'Claude')['AbsolutePath'])
        self.assertTrue((second / 'CLAUDE.md').is_file())
        self.assertTrue((second / 'AGENT-MODE.md').is_file())
        self.assertFalse((second / 'GEMINI.md').exists())
        self.assertFalse((second / '.codex/hooks.json').exists())
        self.assertEqual(json.loads((second / 'project.json').read_text())['processRequirementsSourceRelativePath'], '../前作')

    def test_antigravity_only_adds_mode_files_and_records_hashes(self):
        codex = Path(create_project('既定作品', self.parent)['AbsolutePath'])
        result = create_project('Gemini作品', self.parent, agent_mode='Antigravity')
        project = Path(result['AbsolutePath'])
        self.assertEqual(result['AgentMode'], 'Antigravity')
        self.assertEqual(json.loads((project / 'project.json').read_text(encoding='utf-8'))['agentMode'], 'Antigravity')
        self.assertFalse((project / 'CLAUDE.md').exists())
        self.assertFalse((project / 'agent-modes').exists())
        baseline = json.loads((codex / 'docs/distribution-snapshot.json').read_text(encoding='utf-8'))
        snapshot = json.loads((project / 'docs/distribution-snapshot.json').read_text(encoding='utf-8'))
        original = {entry['path']: entry['sha256'] for entry in baseline['files']}
        current = {entry['path']: entry['sha256'] for entry in snapshot['files']}
        self.assertEqual(set(current) - set(original), {'GEMINI.md', 'AGENT-MODE.md'})
        self.assertEqual({name: current[name] for name in original}, original)
        self.assertEqual(len(current), result['CopiedFiles'])
        for name in ('GEMINI.md', 'AGENT-MODE.md'):
            self.assertEqual(current[name], hashlib.sha256((project / name).read_bytes()).hexdigest())
        self.assertIn('@[Antigravity用の読み替え](AGENT-MODE.md)', (project / 'GEMINI.md').read_text(encoding='utf-8'))
        self.assertFalse((project / '.work/optional-skills').exists())

    def test_antigravity_cli_dry_run_and_unknown_mode(self):
        command = [sys.executable, '-X', 'utf8', str(ROOT / 'scripts/new_manga_project.py'),
                   '--project-name', '確認のみ', '--destination-parent', str(self.parent), '--what-if', '--agent-mode']
        run = subprocess.run([*command, 'Antigravity'], text=True, capture_output=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['AgentMode'], 'Antigravity')
        self.assertNotIn('開き直してください', run.stderr)
        self.assertEqual(list(self.parent.iterdir()), [])
        run = subprocess.run([*command, 'Gemini'], text=True, capture_output=True, encoding='utf-8')
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_inheritance_only_carries_selected_rules_and_rehashes(self):
        from process_checker import save_registry
        first = Path(create_project('前作', self.parent)['AbsolutePath'])
        rule = {
            'id': 'proc-review', 'level': '強く指示', 'instruction': '人物の目的と行動をレビューする',
            'checkpoint': 'script-complete', 'scope': 'project',
            'condition': '字コンテを変更したとき', 'completionCriteria': 'レビューがある',
            'carryForward': True, 'enforcement': 'agents',
            'decision': '相談済み', 'decisionNote': 'テスト用の指示',
        }
        save_registry(first, {'schemaVersion': 1, 'requirements': [rule, {**rule, 'id': 'proc-local', 'carryForward': False}]})
        second = Path(create_project('続編', self.parent, first)['AbsolutePath'])
        data = json.loads((second / 'config/process-requirements.json').read_text())
        self.assertEqual([r['id'] for r in data['requirements']], ['proc-review'])
        self.assertIn(rule['instruction'], (second / 'AGENTS.md').read_text())
        snapshot = json.loads((second / 'docs/distribution-snapshot.json').read_text())
        for entry in snapshot['files']:
            if entry['path'] in ('AGENTS.md', 'config/process-requirements.json'):
                self.assertEqual(entry['sha256'], hashlib.sha256((second / entry['path']).read_bytes()).hexdigest())
        self.assertFalse((second / '.codex/hooks.json').exists())
        self.assertFalse((second / '.work/process-checker/state.json').exists())

    @unittest.skipIf(os.name == 'nt', 'POSIXシェルとシンボリックリンク用の確認')
    def test_every_wrapper_honors_python_override(self):
        interpreter = self.parent / 'python with spaces'
        interpreter.symlink_to(sys.executable)
        for name in ('New-MangaProject.sh', 'Resolve-ReviewProfile.sh', 'Initialize-OptionalSkills.sh'):
            run = subprocess.run(['bash', str(ROOT / 'scripts' / name), '--help'], env={**os.environ, 'PYTHON': str(interpreter)}, text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('usage:', run.stdout)

    def test_existing_no_overwrite(self):
        target = self.parent / '既存'
        target.mkdir()
        (target / 'keep').write_text('保持')
        with self.assertRaises(ValueError):
            create_project('既存', self.parent)
        self.assertEqual((target / 'keep').read_text(), '保持')

    def test_invalid_names(self):
        for name in ('', '../外', '/絶対', '末尾 ', 'CON', 'lpt¹', '_先頭', 'a.b', 'あ' * 65):
            with self.subTest(name=name), self.assertRaises(ValueError):
                create_project(name, self.parent)

    def test_symlink_parent_rejected(self):
        alias = self.parent / 'alias'
        try:
            alias.symlink_to(self.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('この環境ではシンボリックリンクを作成できません。')
        with self.assertRaises(ValueError):
            create_project('リンク', alias)
        self.assertFalse((self.parent / 'リンク').exists())

    def test_missing_parent_rejected(self):
        with self.assertRaises(ValueError):
            create_project('作品', self.parent / 'missing')

    @unittest.skipIf(os.name == 'nt', 'POSIXシェル用の確認')
    def test_bash_cli_outside_checkout(self):
        run = subprocess.run(['bash', str(ROOT / 'scripts/New-MangaProject.sh'), '-ProjectName', '外から 空白', '-DestinationParent', '.', '-WhatIf'], cwd=self.parent, text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['AbsolutePath'], str(self.parent / '外から 空白'))
        self.assertEqual(list(self.parent.iterdir()), [])

    @unittest.skipIf(os.name == 'nt', 'POSIXシェル用の確認')
    def test_cdpath_does_not_corrupt_script_location(self):
        for name in ('New-MangaProject.sh', 'Resolve-ReviewProfile.sh', 'Initialize-OptionalSkills.sh'):
            run = subprocess.run(['bash', 'scripts/' + name, '--help'], cwd=ROOT, env={**os.environ, 'CDPATH': '.'}, text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('usage:', run.stdout)

    @unittest.skipIf(os.name == 'nt', 'POSIXシェル用の確認')
    def test_invalid_python_override(self):
        run = subprocess.run(['bash', str(ROOT / 'scripts/New-MangaProject.sh'), '--help'], env={**os.environ, 'PYTHON': '/no/such/python'}, text=True, capture_output=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('Python 3.10', run.stderr)


if __name__ == '__main__':
    unittest.main()
