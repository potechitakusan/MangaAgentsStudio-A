#!/usr/bin/env python3
"""作品内の任意スキルを、固定版・明示承諾を確認して導入する。"""

import argparse
from datetime import datetime
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import uuid
import zipfile


def assert_optional_path(root, relative):
    """作品外への移動と、親も含むリンク経由の読み書きを拒否する。"""
    root = Path(os.path.abspath(root))
    relative = str(relative)
    if ntpath.isabs(relative) or ntpath.splitdrive(relative)[0] or '..' in re.split(r'[\\/]', relative):
        raise ValueError('作品外のパスは使用できません。')
    path = Path(os.path.abspath(root / relative.replace('\\', '/')))
    if path == root or root not in path.parents:
        raise ValueError('作品内のパスを指定してください。')
    for current in (path, *path.parents):
        if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
            raise ValueError('リンクを経由する導入先は使用できません。')
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_optional_json(value, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def get_optional_selection(root):
    path = assert_optional_path(root, 'OPTION.md')
    if not path.exists():
        return 'none'
    rows = re.findall(r'^\|\s*日本語推敲スキル\s*\|\s*([^|]*)\|', path.read_text(encoding='utf-8-sig'), re.MULTILINE)
    if not rows:
        return 'none'
    if len(rows) != 1:
        raise ValueError('日本語推敲スキルの設定行が重複しています。')
    value = rows[0].strip().lower()
    if value in ('', '使用しない', '無効', 'none'):
        return 'none'
    if value in ('使用する', '有効', 'humanizer-jp'):
        return 'humanizer-jp'
    if re.fullmatch(r'japanese-natural-writing(?:[（(]gemini[）)])?', value):
        return 'japanese-natural-writing'
    raise ValueError('日本語推敲スキルには使用しない・humanizer-jp・japanese-natural-writingを指定してください。')


def find_optional_git():
    return shutil.which('git')


def invoke_optional_git(git, arguments):
    environment = os.environ.copy()
    environment['GIT_TERMINAL_PROMPT'] = '0'
    result = subprocess.run([git, *map(str, arguments)], env=environment, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', check=False)
    if result.returncode:
        raise ValueError('Git処理に失敗しました: ' + result.stdout)
    return result.stdout.strip()


def get_optional_archive(source, work, git):
    archive = work / 'source.zip'
    if source['method'] == 'git':
        if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git', source['repository']) or not re.fullmatch(r'[a-f0-9]{40}', source['revision']):
            raise ValueError('Gitの取得先または固定版が不正です。')
        repo, hooks = work / 'repo', work / 'empty-hooks'
        hooks.mkdir()
        invoke_optional_git(git, ['-c', f'core.hooksPath={hooks}', 'init', '--quiet', repo])
        invoke_optional_git(git, ['-C', repo, '-c', f'core.hooksPath={hooks}', '-c', 'credential.helper=', 'fetch', '--quiet', '--depth=1', source['repository'], source['revision']])
        head = invoke_optional_git(git, ['-C', repo, 'rev-parse', 'FETCH_HEAD'])
        if head != source['revision']:
            raise ValueError('取得したGitの版が一致しません。')
        names = list(source['files'])
        tree = invoke_optional_git(git, ['-C', repo, 'ls-tree', '-r', head, '--', *names])
        if re.search(r'^(120000|160000) ', tree, re.MULTILINE):
            raise ValueError('スキル内のリンクやサブモジュールは導入しません。')
        invoke_optional_git(git, ['-C', repo, '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'archive', '--format=zip', f'--output={archive}', head, '--', *names])
    elif source['method'] == 'zip':
        if not re.fullmatch(r'https://note\.com/api/v2/attachments/download/[a-f0-9]+', source['url']) or not re.fullmatch(r'[a-f0-9]{64}', source['revision']):
            raise ValueError('ZIPの取得先または固定版が不正です。')
        with urllib.request.urlopen(source['url'], timeout=60) as response, archive.open('wb') as output:
            shutil.copyfileobj(response, output)
        if file_hash(archive) != source['revision']:
            raise ValueError('ZIPの内容が確認済みの版から変わっています。')
    else:
        raise ValueError('未対応の取得方法です。')
    return archive


def expand_optional_archive(archive, source, stage):
    expected = {}
    for name, digest in source['files'].items():
        if not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', name) or '..' in name.split('/') or not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise ValueError('取得対象のファイル指定が不正です。')
        expected[source['prefix'] + name] = (name, digest)
    seen = set()
    with zipfile.ZipFile(archive) as zipped:
        for entry in zipped.infolist():
            if entry.is_dir():
                continue
            if entry.filename not in expected or entry.filename in seen:
                raise ValueError('ZIPに想定外または重複するファイルがあります。')
            if (entry.external_attr >> 16) & 0xF000 == 0xA000:
                raise ValueError('ZIP内のリンクは導入しません。')
            name, digest = expected[entry.filename]
            path = assert_optional_path(stage, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(entry) as incoming, path.open('xb') as output:
                shutil.copyfileobj(incoming, output)
            if file_hash(path) != digest:
                raise ValueError('スキルのファイル内容が確認済みの版と一致しません。')
            seen.add(entry.filename)
    if len(seen) != len(expected):
        raise ValueError('スキルの必要ファイルが不足しています。')


def initialize_optional_skills(project_root, provider='', gemini_consent='Unspecified', consent_note=''):
    root = Path(os.path.abspath(project_root))
    if not (root / 'project.json').is_file():
        raise ValueError('配布先の作品プロジェクトで実行してください。')
    provider = provider or get_optional_selection(root)
    def result(status, message, **extra):
        return dict(status=status, provider=provider, **extra, message=message)
    if provider == 'none':
        return result('disabled', '推敲スキルは無効です。外部取得・Git確認・Gemini呼び出しは行いません。')
    if provider not in ('humanizer-jp', 'japanese-natural-writing'):
        raise ValueError('未対応の推敲スキルです。')
    manifest = read_json(assert_optional_path(root, 'config/optional-skills.json'))
    if manifest['schemaVersion'] != 1:
        raise ValueError('推敲スキルの配布設定が不正です。')
    source = manifest['providers'][provider]
    target_relative = '.agents/skills/' + provider
    target = assert_optional_path(root, target_relative)
    state_relative = '.work/optional-skills/' + provider
    receipt_path = assert_optional_path(root, state_relative + '-installed.json')
    consent_path = assert_optional_path(root, state_relative + '-consent.json')
    # 環境検出・有効化設定を、利用枠の消費許可に置き換えない。
    if provider == 'japanese-natural-writing' or source['requiresGeminiConsent']:
        if gemini_consent not in ('Unspecified', 'Granted', 'Denied'):
            raise ValueError('Geminiの回答状態が不正です。')
        if gemini_consent != 'Unspecified':
            if not consent_note.strip():
                raise ValueError('ユーザーの明示回答と許可範囲の記録が必要です。')
            write_optional_json(dict(provider=provider, revision=source['revision'], decision=gemini_consent,
                                     note=consent_note, recordedAt=datetime.now().astimezone().isoformat()), consent_path)
        consent = read_json(consent_path) if consent_path.exists() else None
        if not consent or consent.get('provider') != provider or consent.get('revision') != source['revision'] or not str(consent.get('note') or '').strip():
            return result('needs_gemini_consent', 'この作品の選択した文章をGeminiへ送り、利用枠を消費して推敲してよいか、導入前にユーザーへ確認してください。')
        if consent.get('decision') != 'Granted':
            return result('gemini_declined', 'Geminiの許可がありません。取得・導入・呼び出しを行わず、通常の制作を続けてください。')
    if target.exists():
        if not receipt_path.exists():
            raise ValueError('同名の既存スキルを上書きしません。導入記録との照合が必要です。')
        receipt = read_json(receipt_path)
        if receipt['provider'] != provider or receipt['path'] != target_relative or receipt['revision'] != source['revision']:
            raise ValueError('導入済み版・配置先が異なります。更新は別途扱ってください。')
        if set(source['files']) | {'agents/openai.yaml'} != set(receipt['files']):
            raise ValueError('導入記録のファイル一覧が一致しません。')
        for name, digest in receipt['files'].items():
            path = assert_optional_path(target, name)
            if not path.is_file() or file_hash(path) != digest:
                raise ValueError('導入済みのスキルに変更・欠落があります。自動で上書きしません。')
        return result('ready', '導入済みです。外部から再取得しません。', path=target_relative)
    git = find_optional_git() if source['method'] == 'git' else None
    if source['method'] == 'git' and not git:
        return result('needs_git_consent', 'Gitがありません。Gitをインストールしてよいかユーザーへ確認し、許可を得てから導入してください。')
    work = assert_optional_path(root, '.work/optional-skills/download-' + uuid.uuid4().hex)
    stage = work / 'skill'
    stage.mkdir(parents=True)
    archive = get_optional_archive(source, work, git)
    expand_optional_archive(archive, source, stage)
    if not (stage / 'SKILL.md').is_file():
        raise ValueError('SKILL.mdがありません。')
    # 原文・権利表示を保持し、明示適用の方針だけを追記する。
    policy_path = stage / 'agents/openai.yaml'
    policy = ''
    if policy_path.exists():
        with policy_path.open(encoding='utf-8-sig', newline='') as stream:
            policy = stream.read()
    if re.search(r'^policy\s*:', policy, re.MULTILINE | re.IGNORECASE):
        raise ValueError('呼び出し方針が変わっています。確認してから導入してください。')
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(policy.rstrip() + '\npolicy:\n  allow_implicit_invocation: false\n', encoding='utf-8', newline='')
    names = dict.fromkeys([*source['files'], 'agents/openai.yaml'])
    receipt = dict(provider=provider, revision=source['revision'], path=target_relative,
                   installedAt=datetime.now().astimezone().isoformat(),
                   files={name: file_hash(stage / name) for name in names},
                   adjustment='暗黙の呼び出しを無効化。選択した対象だけへ明示適用。')
    target.parent.mkdir(parents=True, exist_ok=True)
    # 移動直前にリンクと同名の導入先を再確認する。失敗した取得物は保持する。
    assert_optional_path(root, stage.relative_to(root))
    assert_optional_path(root, target_relative)
    if target.exists():
        raise ValueError('導入先が作成されたため、上書きせず停止します。')
    stage.rename(target)
    write_optional_json(receipt, receipt_path)
    return result('installed', '作品内へ導入しました。認識されない場合だけCodexを開き直してください。', path=target_relative)


def main(argv=None):
    if sys.version_info < (3, 10):
        print('Python 3.10以上が必要です。', file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', '-ProjectRoot', default=str(Path(__file__).absolute().parent.parent), help='作品プロジェクトの場所')
    parser.add_argument('--provider', '-Provider', default='', choices=('', 'none', 'humanizer-jp', 'japanese-natural-writing'), help='会話で採用した実効設定')
    parser.add_argument('--gemini-consent', '-GeminiConsent', default='Unspecified', choices=('Unspecified', 'Granted', 'Denied'), help='実際のユーザー回答')
    parser.add_argument('--consent-note', '-ConsentNote', default='', help='実際の回答と許可対象の範囲')
    args = parser.parse_args(argv)
    try:
        value = initialize_optional_skills(args.project_root, args.provider, args.gemini_consent, args.consent_note)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print('エラー: ' + str(error), file=sys.stderr)
        return 1
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
