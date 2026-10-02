"""任意スキルのLinux入口・承諾・固定版照合を外部通信なしで検証する。"""

import copy
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import initialize_optional_skills as optional


class OptionalSkillsPortableTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='optional-skills-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / '作品 空白'
        self.root.mkdir()
        (self.root / 'project.json').write_text('{}', encoding='utf-8')
        self.contents = {'SKILL.md': b'# fixture\n', 'LICENSE': b'test-only\n'}
        hashes = {name: hashlib.sha256(body).hexdigest() for name, body in self.contents.items()}
        self.manifest = {'schemaVersion': 1, 'providers': {
            'humanizer-jp': {'method': 'git', 'repository': 'https://github.com/test/fixture.git',
                             'revision': 'a' * 40, 'requiresGeminiConsent': False, 'prefix': '', 'files': hashes},
            'japanese-natural-writing': {'method': 'zip', 'url': 'https://note.com/api/v2/attachments/download/123abc',
                                          'revision': 'b' * 64, 'requiresGeminiConsent': True, 'prefix': '', 'files': hashes},
        }}
        self.save_manifest()
        self.archive = Path(self.temporary.name) / 'fixture.zip'
        self.make_archive(self.contents.items())
        self.fetch = patch.object(optional, 'get_optional_archive', return_value=self.archive).start()
        self.git = patch.object(optional, 'find_optional_git', return_value='dummy-git').start()
        self.addCleanup(patch.stopall)

    def save_manifest(self):
        optional.write_optional_json(self.manifest, self.root / 'config/optional-skills.json')

    def make_archive(self, entries):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.archive, 'w') as archive:
                for name, body in entries:
                    archive.writestr(name, body)

    def select(self, selection):
        (self.root / 'OPTION.md').write_text('| 日本語推敲スキル | ' + selection + ' |\n', encoding='utf-8')

    def run_initialize(self, **kwargs):
        return optional.initialize_optional_skills(self.root, **kwargs)

    def test_disabled_without_manifest_is_offline_and_creates_nothing(self):
        (self.root / 'config/optional-skills.json').unlink()
        self.assertEqual(self.run_initialize()['status'], 'disabled')
        self.fetch.assert_not_called()
        self.git.assert_not_called()
        self.assertFalse((self.root / '.work').exists())
        self.assertFalse((self.root / '.agents').exists())

    def test_selection_and_duplicate_rejection(self):
        for value, expected in [('', 'none'), ('使用しない', 'none'), ('無効', 'none'), ('NONE', 'none'), ('使用する', 'humanizer-jp'), ('有効', 'humanizer-jp'), ('japanese-natural-writing（Gemini）', 'japanese-natural-writing')]:
            self.select(value)
            self.assertEqual(optional.get_optional_selection(self.root), expected)
        self.select('unknown')
        with self.assertRaises(ValueError):
            self.run_initialize()
        self.select('none |\n| 日本語推敲スキル | humanizer-jp')
        with self.assertRaises(ValueError):
            self.run_initialize()

    def test_missing_git_requests_permission_without_installing(self):
        self.git.return_value = None
        self.assertEqual(self.run_initialize(provider='humanizer-jp')['status'], 'needs_git_consent')
        self.fetch.assert_not_called()
        self.assertFalse((self.root / '.agents').exists())

    def test_install_resume_disable_and_modified_file(self):
        self.select('humanizer-jp')
        self.assertEqual(self.run_initialize()['status'], 'installed')
        target = self.root / '.agents/skills/humanizer-jp'
        for name, body in self.contents.items():
            self.assertEqual((target / name).read_bytes(), body)
        self.assertIn('allow_implicit_invocation: false', (target / 'agents/openai.yaml').read_text())
        receipt = optional.read_json(self.root / '.work/optional-skills/humanizer-jp-installed.json')
        self.assertEqual(receipt['path'], '.agents/skills/humanizer-jp')
        self.assertNotIn(str(self.root), json.dumps(receipt))
        self.fetch.reset_mock()
        self.git.reset_mock()
        self.assertEqual(self.run_initialize()['status'], 'ready')
        self.fetch.assert_not_called()
        self.git.assert_not_called()
        self.select('none')
        self.assertEqual(self.run_initialize()['status'], 'disabled')
        self.assertTrue(target.exists())
        (target / 'SKILL.md').write_text('利用者による変更', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.run_initialize(provider='humanizer-jp')
        self.assertEqual((target / 'SKILL.md').read_text(encoding='utf-8'), '利用者による変更')

    def test_existing_unrecorded_skill_is_preserved(self):
        target = self.root / '.agents/skills/humanizer-jp'
        target.mkdir(parents=True)
        with self.assertRaises(ValueError):
            self.run_initialize(provider='humanizer-jp')
        self.fetch.assert_not_called()

    def test_gemini_consent_decline_grant_revoke_and_revision(self):
        self.select('japanese-natural-writing')
        self.assertEqual(self.run_initialize()['status'], 'needs_gemini_consent')
        self.fetch.assert_not_called()
        self.git.assert_not_called()
        with self.assertRaises(ValueError):
            self.run_initialize(gemini_consent='Granted')
        self.assertEqual(self.run_initialize(gemini_consent='Denied', consent_note='検証用の拒否回答')['status'], 'gemini_declined')
        self.assertEqual(self.run_initialize()['status'], 'gemini_declined')
        self.fetch.assert_not_called()
        # 実サービスへの許可ではなく、独自ダミー取得物の配置テスト専用。
        self.assertEqual(self.run_initialize(gemini_consent='Granted', consent_note='模擬回答・独自テスト文章のみ')['status'], 'installed')
        self.assertEqual(self.run_initialize()['status'], 'ready')
        self.git.assert_not_called()
        self.assertEqual(self.run_initialize(gemini_consent='Denied', consent_note='検証用の撤回回答')['status'], 'gemini_declined')
        self.manifest['providers']['japanese-natural-writing']['revision'] = 'c' * 64
        self.manifest['providers']['japanese-natural-writing']['requiresGeminiConsent'] = False
        self.save_manifest()
        self.assertEqual(self.run_initialize()['status'], 'needs_gemini_consent')

    def test_bad_archives_never_install_and_keep_work(self):
        valid = list(self.contents.items())
        link = zipfile.ZipInfo('SKILL.md')
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        for entries in [valid[:-1], [('SKILL.md', b'changed'), valid[1]], valid + [('../escape', b'x')], valid + [valid[0]], [(link, b'LICENSE'), valid[1]]]:
            with self.subTest(entries=entries):
                self.make_archive(entries)
                with self.assertRaises(ValueError):
                    self.run_initialize(provider='humanizer-jp')
                self.assertFalse((self.root / '.agents/skills/humanizer-jp').exists())
                self.assertTrue(list((self.root / '.work/optional-skills').glob('download-*')))

    def test_paths_and_broken_symlinks_are_rejected(self):
        for name in ['../escape', '/outside', str(PureWindowsPath('C:') / '/outside'), 'a/../../outside', '..\\outside']:
            with self.assertRaises(ValueError):
                optional.assert_optional_path(self.root, name)
        link = self.root / '.agents'
        try:
            link.symlink_to(self.root / 'missing', target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('この環境ではシンボリックリンクを作成できません。')
        with self.assertRaises(ValueError):
            self.run_initialize(provider='humanizer-jp')
        self.fetch.assert_not_called()

    def test_policy_interface_preserved_and_existing_policy_rejected(self):
        policy_name = 'agents/openai.yaml'
        policy = b'interface:\r\n  display_name: fixture\r\n'
        self.contents[policy_name] = policy
        self.manifest['providers']['humanizer-jp']['files'][policy_name] = hashlib.sha256(policy).hexdigest()
        self.save_manifest()
        self.make_archive(self.contents.items())
        self.run_initialize(provider='humanizer-jp')
        body = (self.root / '.agents/skills/humanizer-jp/agents/openai.yaml').read_bytes()
        self.assertTrue(body.startswith(policy.rstrip()))
        self.assertEqual(self.run_initialize(provider='humanizer-jp')['status'], 'ready')
        shutil.rmtree(self.root / '.agents')
        policy = b'policy:\n  allow_implicit_invocation: true\n'
        self.contents[policy_name] = policy
        self.manifest['providers']['humanizer-jp']['files'][policy_name] = hashlib.sha256(policy).hexdigest()
        self.save_manifest()
        self.make_archive(self.contents.items())
        with self.assertRaises(ValueError):
            self.run_initialize(provider='humanizer-jp')

    def test_zip_download_checks_whole_archive_hash(self):
        # 取得境界だけを差し替え、HTTP通信は一切行わない。
        source = copy.deepcopy(self.manifest['providers']['japanese-natural-writing'])
        source['revision'] = optional.file_hash(self.archive)
        work = self.root / 'zip-work'
        work.mkdir()
        with patch.object(optional.urllib.request, 'urlopen', side_effect=lambda *args, **kwargs: io.BytesIO(self.archive.read_bytes())):
            archive = REAL_GET_ARCHIVE(source, work, None)
            self.assertEqual(optional.file_hash(archive), source['revision'])
            source['revision'] = '0' * 64
            with self.assertRaises(ValueError):
                REAL_GET_ARCHIVE(source, work, None)

    def test_git_archive_flags_and_fixed_revision(self):
        source = self.manifest['providers']['humanizer-jp']
        work = self.root / 'git-work'
        work.mkdir()
        with patch.object(optional, 'invoke_optional_git', side_effect=['', '', source['revision'], '100644 blob abc\tSKILL.md', '']) as invoke:
            REAL_GET_ARCHIVE(source, work, 'dummy-git')
        calls = [call.args[1] for call in invoke.call_args_list]
        self.assertIn('credential.helper=', calls[1])
        self.assertIn('core.autocrlf=false', calls[-1])
        self.assertIn('core.eol=lf', calls[-1])
        self.assertIn('--depth=1', calls[1])

    @unittest.skipIf(os.name == 'nt', 'POSIXシェル用の確認')
    def test_shell_wrapper_accepts_spaced_paths_and_python_override(self):
        if not shutil.which('bash'):
            self.skipTest('Bashがありません。')
        environment = os.environ.copy()
        environment['PYTHON'] = sys.executable
        result = subprocess.run(['bash', str(ROOT / 'scripts/Initialize-OptionalSkills.sh'), '--project-root', str(self.root)],
                                cwd=self.temporary.name, env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'disabled')


REAL_GET_ARCHIVE = optional.get_optional_archive

if __name__ == '__main__':
    unittest.main()
