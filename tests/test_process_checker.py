"""必須工程の照合、改稿後の再確認、明示引継ぎとHooksの境界を検証する。"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import process_checker as checker


def rule(**changes):
    value = {
        'id': 'proc-review', 'level': '指示', 'instruction': '人物の目的と行動をレビューする',
        'checkpoint': 'script-complete', 'scope': 'project',
        'condition': '字コンテを作成または変更したとき',
        'completionCriteria': '対象原稿と対応方針を記したレビューがある',
        'carryForward': True, 'enforcement': 'report',
        'decision': '相談済み', 'decisionNote': 'ユーザーが文面と条件を指定した',
    }
    value.update(changes)
    return value


class ProcessCheckerTests(unittest.TestCase):
    def setUp(self):
        self.base = ROOT / '.work' / ('process-test-' + uuid.uuid4().hex)
        self.root = self.project('作品')

    def project(self, name):
        root = self.base / name
        checker.write_json(root / 'project.json', {'schemaVersion': 1, 'name': name})
        checker.write_json(root / checker.REQUIREMENTS, {'schemaVersion': 1, 'requirements': []})
        checker.write_text(root / 'AGENTS.md', '# 作品\n\n既存の約束を保持する。\n')
        return root

    def save(self, *rules, root=None):
        checker.save_registry(root or self.root, {'schemaVersion': 1, 'requirements': list(rules)})

    def report(self, results=(), **changes):
        value = {'checkpoint': 'page-complete', 'scope': 'page', 'subject': 'page-001',
                 'revision': 'v1', 'results': list(results)}
        value.update(changes)
        return checker.report(self.root, value)

    def completed(self, rule_id='proc-review'):
        checker.write_text(self.root / 'docs/script.md', '対象原稿の内容')
        checker.write_text(self.root / 'docs/review.md', '人物の目的と行動を照合した内容・対応方針')
        return {'id': rule_id, 'status': '実施済み', 'note': '原稿とレビューの対応を読んで確認',
                'evidence': ['docs/script.md', 'docs/review.md']}

    def event(self, name, **changes):
        value = {'hook_event_name': name, 'turn_id': 'turn-a', 'stop_hook_active': False}
        value.update(changes)
        return checker.hook(self.root, value)

    def test_empty_is_inactive_but_missing_or_malformed_is_an_error(self):
        self.assertFalse(checker.summary(self.root)['enabled'])
        self.assertEqual(self.event('UserPromptSubmit'), {})
        self.assertFalse(self.report()['enabled'])
        self.assertFalse((self.root / '.work').exists())
        path = self.root / checker.REQUIREMENTS
        path.unlink()
        with self.assertRaises(ValueError):
            checker.summary(self.root)
        checker.write_json(path, {})
        with self.assertRaises(ValueError):
            checker.summary(self.root)

    def test_registration_replace_and_removal_preserve_unmanaged_agents(self):
        request = '.work/process-checker/request.json'
        item = rule(level='強く指示', enforcement='agents', decision='おまかせ')
        checker.write_json(self.root / request, item)
        with patch.object(sys, 'argv', ['checker', '--project', str(self.root), 'add', '--input', request]):
            checker.main()
        agents = self.root / 'AGENTS.md'
        self.assertIn(item['instruction'], agents.read_text(encoding='utf-8'))
        with agents.open('a', encoding='utf-8') as stream:
            stream.write('\n管理区間の後ろの利用者メモ\n')
        item['instruction'] = '人物の目的と行動を再レビューする'
        checker.write_json(self.root / request, item)
        with patch.object(sys, 'argv', ['checker', '--project', str(self.root), 'replace', '--input', request]):
            checker.main()
        self.assertFalse(checker.summary(self.root)['pending'])
        with patch.object(sys, 'argv', ['checker', '--project', str(self.root), 'remove',
                                        '--id', item['id'], '--decision-note', 'ユーザーが解除を指定']):
            checker.main()
        body = agents.read_text(encoding='utf-8')
        self.assertIn('既存の約束を保持する。', body)
        self.assertIn('管理区間の後ろの利用者メモ', body)
        self.assertNotIn(checker.BEGIN, body)
        self.assertFalse(checker.registry(self.root)['requirements'])

    def test_invalid_registration_cannot_partially_write(self):
        self.save(rule())
        before = (self.root / checker.REQUIREMENTS).read_bytes()
        for bad in (rule(level='強く指示'), rule(checkpoint=[]), rule(instruction=checker.BEGIN)):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                self.save(bad)
            self.assertEqual((self.root / checker.REQUIREMENTS).read_bytes(), before)
        self.assertNotIn(checker.BEGIN, (self.root / 'AGENTS.md').read_text(encoding='utf-8'))

    def test_overdue_steps_remain_pending_and_require_real_evidence(self):
        self.save(rule(), rule(id='proc-page', checkpoint='before-generation', scope='page'),
                  rule(id='proc-later', checkpoint='before-handoff'))
        result = self.report()
        self.assertEqual({i['id'] for i in result['pending']}, {'proc-review', 'proc-page'})
        result = self.report([self.completed()])
        self.assertEqual([i['id'] for i in result['pending']], ['proc-page'])
        with self.assertRaises(ValueError):
            self.report([{'id': 'proc-page', 'status': '実施済み', 'note': '自己申告だけ', 'evidence': []}])
        with self.assertRaises(ValueError):
            self.report([{'id': 'proc-page', 'status': '実施済み', 'note': '存在しない記録',
                          'evidence': ['docs/missing.md']}])

    def test_evidence_or_rule_changes_require_recheck_after_resume(self):
        self.save(rule())
        self.report([self.completed()])
        self.assertFalse(checker.summary(self.root)['pending'])
        checker.write_text(self.root / 'docs/script.md', '改稿した新しい原稿')
        self.assertEqual(checker.summary(self.root)['pending'][0]['status'], '未確認')
        self.report([self.completed()])
        self.save(rule(completionCriteria='原稿とレビューに加え、改善の比較がある'))
        self.assertEqual(checker.summary(self.root)['pending'][0]['status'], '未確認')

    def test_each_page_and_revision_is_checked_separately(self):
        self.save(rule(scope='page'))
        self.report([self.completed()])
        result = self.report(subject='page-002')
        self.assertEqual([i['subject'] for i in result['pending']], ['page-002'])
        result = self.report(revision='v2')
        self.assertEqual({(i['subject'], i['revision']) for i in result['pending']},
                         {('page-001', 'v2'), ('page-002', 'v1')})
        self.assertTrue(any(i.get('superseded') for i in checker.state(self.root)['items']))

    def test_explicit_import_only_copies_portable_rules(self):
        source = self.project('前の作品')
        self.save(rule(level='強く指示', enforcement='agents+hooks'),
                  rule(id='proc-local', carryForward=False), root=source)
        checker.write_json(source / checker.STATE, {'private': '旧作品の実施済み記録'})
        checker.write_json(source / '.codex/hooks.json', {'private': '旧作品のHooks'})
        before = {p.relative_to(source): p.read_bytes() for p in source.rglob('*') if p.is_file()}
        result = checker.import_requirements(self.root, source)
        self.assertEqual(result['count'], 1)
        self.assertEqual(checker.registry(self.root)['requirements'][0]['enforcement'], 'agents+hooks')
        self.assertIn(checker.BEGIN, (self.root / 'AGENTS.md').read_text(encoding='utf-8'))
        self.assertFalse((self.root / checker.STATE).exists())
        self.assertFalse((self.root / '.codex').exists())
        self.assertEqual(before, {p.relative_to(source): p.read_bytes() for p in source.rglob('*') if p.is_file()})
        with self.assertRaises(ValueError):
            checker.import_requirements(self.root, source)

    def test_hooks_preview_preserves_existing_handlers_and_never_trusts(self):
        self.save(rule(level='強く指示', enforcement='agents+hooks'))
        path = self.root / '.codex/hooks.json'
        old = {'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo existing'}]}]}}
        checker.write_json(path, old)
        before = path.read_bytes()
        preview = checker.install_hooks(self.root, False)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(preview['configuration']['hooks']['Stop'][0], old['hooks']['Stop'][0])
        applied = checker.install_hooks(self.root, True)['configuration']
        self.assertEqual(checker.install_hooks(self.root, True)['configuration'], applied)
        self.assertEqual([p.name for p in path.parent.iterdir()], ['hooks.json'])

    def test_stop_hook_is_bounded_and_does_not_repeat_waiting_questions(self):
        self.save(rule(level='強く指示', enforcement='agents+hooks'))
        self.event('UserPromptSubmit')
        self.assertEqual(self.event('Stop')['decision'], 'block')
        self.assertNotIn('decision', self.event('Stop', stop_hook_active=True))
        self.report([{'id': 'proc-review', 'status': 'ユーザー回答待ち', 'note': '方針の回答待ち', 'evidence': []}])
        self.assertEqual(self.event('Stop'), {})
        self.event('UserPromptSubmit', turn_id='turn-b')
        self.assertEqual(self.event('Stop', turn_id='turn-b')['decision'], 'block')
        self.report()
        checker.report(self.root, {'noProgress': True, 'note': '制作を進めず設定の説明だけをした'})
        self.assertEqual(self.event('Stop', turn_id='turn-b'), {})
        self.assertEqual(checker.summary(self.root)['pending'][0]['status'], 'ユーザー回答待ち')

    def test_no_progress_does_not_clear_missing_work_and_lock_prevents_parallel_edits(self):
        self.save(rule(level='強く指示', enforcement='agents+hooks'))
        self.event('UserPromptSubmit')
        self.report()
        checker.report(self.root, {'noProgress': True, 'note': '説明だけで制作は進めていない'})
        self.assertEqual(checker.summary(self.root)['pending'][0]['status'], '未確認')
        self.assertEqual(self.event('Stop'), {})
        with checker.editing(self.root):
            with self.assertRaises(ValueError), checker.editing(self.root):
                pass
        with self.assertRaises(ValueError):
            checker.evidence(self.root, ['../前の作品/project.json'])


if __name__ == '__main__':
    unittest.main()
