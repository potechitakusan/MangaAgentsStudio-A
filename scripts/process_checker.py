"""作品内の必須事項・照合記録・強い指示の反映を管理する（標準ライブラリのみ）。"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import tempfile
import uuid


REQUIREMENTS = 'config/process-requirements.json'
STATE = '.work/process-checker/state.json'
TURN = '.work/process-checker/turn.json'
BEGIN = '<!-- process-checker:strong:start -->'
END = '<!-- process-checker:strong:end -->'
HOOK_LABEL = 'プロセスチェッカーの必須事項確認'
CHECKPOINTS = {
    'brief-complete': '企画完了',
    'script-complete': '字コンテ完了',
    'layout-complete': 'コマ割り計画完了',
    'name-complete': 'ネーム完了',
    'before-generation': 'ページ生成前',
    'after-generation': 'ページ生成後',
    'page-complete': 'ページ完成',
    'before-preview': 'PNG提示前',
    'after-preview': 'PNG確認後',
    'before-psd': 'PSD作成前',
    'after-psd': 'PSD作成後',
    'before-handoff': '引き渡し前',
}
RANK = {key: index for index, key in enumerate(CHECKPOINTS)}
STATUSES = {'実施済み', '未実施', '未確認', 'ユーザー回答待ち', '対象外'}
FIELDS = {'id', 'level', 'instruction', 'checkpoint', 'scope', 'condition',
          'completionCriteria', 'carryForward', 'enforcement', 'decision', 'decisionNote'}


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def safe_path(root, relative):
    require(isinstance(relative, str) and relative and '\\' not in relative,
            'パスは / 区切りの作品ルート基準の相対パスにしてください。')
    path = Path(relative)
    require(not path.is_absolute() and not PureWindowsPath(relative).drive
            and '..' not in path.parts, '作品外のパスは使えません。')
    target = root / path
    for item in (target, *target.parents):
        if item.exists() or item.is_symlink():
            require(not item.is_symlink()
                    and not (getattr(item.stat(), 'st_file_attributes', 0) & 0x400),
                    'リンク経由の読み書きは行いません。')
        if item == root:
            break
    require(target.resolve().is_relative_to(root.resolve()), '作品外のパスです。')
    return target


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'JSONを読み取れません: {path.name}') from exc


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def write_json(path, value):
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def validate_registry(value):
    require(isinstance(value, dict) and set(value) == {'schemaVersion', 'requirements'}
            and type(value['schemaVersion']) is int and value['schemaVersion'] == 1
            and isinstance(value['requirements'], list), '必須事項ファイルの形式が不正です。')
    seen = set()
    for rule in value['requirements']:
        require(isinstance(rule, dict) and set(rule) == FIELDS, '必須事項の項目が不足または未対応です。')
        require(isinstance(rule['id'], str) and re.fullmatch(r'proc-[a-z0-9-]{1,60}', rule['id']),
                '必須事項のIDが不正です。')
        require(rule['id'] not in seen, '必須事項のIDが重複しています。')
        seen.add(rule['id'])
        require(rule['level'] in ('指示', '強く指示'), 'レベルは「指示」または「強く指示」です。')
        require(isinstance(rule['checkpoint'], str) and rule['checkpoint'] in CHECKPOINTS
                and rule['scope'] in ('project', 'page'),
                '確認時点または対象単位が不正です。')
        for key in ('instruction', 'condition', 'completionCriteria', 'decisionNote'):
            require(nonempty(rule[key]), f'{key}を具体的に記入してください。')
            require(BEGIN not in rule[key] and END not in rule[key], '管理区間の区切りを指示本文へ含められません。')
        require(type(rule['carryForward']) is bool, '引き継ぐかどうかを指定してください。')
        require(rule['decision'] in ('相談済み', 'おまかせ'), '相談結果または「おまかせ」の記録が必要です。')
        allowed = ('report',) if rule['level'] == '指示' else ('agents', 'agents+hooks')
        require(rule['enforcement'] in allowed, 'レベルと反映先が一致しません。')
    return value


def registry(root):
    # 空配列だけを無効扱いにする。欠落・壊れたJSONを無効扱いにはしない。
    return validate_registry(read_json(safe_path(root, REQUIREMENTS)))


def project_root(path):
    root = Path(path).absolute()
    require(safe_path(root, 'project.json').is_file(), '作品のproject.jsonが必要です。雛形では実行しません。')
    require(isinstance(read_json(root / 'project.json'), dict), 'project.jsonが不正です。')
    return root


@contextmanager
def editing(root):
    lock = safe_path(root, '.work/process-checker/edit.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError('必須事項の更新が実行中です。残存ロックは実行状況を確認してから扱ってください。') from exc
    try:
        os.close(descriptor)
        yield
    finally:
        lock.unlink()


def strong_block(data):
    rules = [r for r in data['requirements'] if r['level'] == '強く指示']
    if not rules:
        return ''
    lines = [BEGIN, '## この作品でユーザーが強く指示した工程', '',
             '正本は `config/process-requirements.json`。適用条件を満たす場合、下の時点までに実施する。',
             '未実施・根拠未確認なら関係する次工程へ進まず、不足を具体化する。回答待ちを承認扱いにしない。',
             '指定のない演出・提案の採否はメインが判断する。詳細は `docs/knowledge/process-checker.md`。', '']
    for rule in rules:
        lines.extend([f"- {rule['id']}：{rule['instruction']}",
                      f"  - 確認時点：{CHECKPOINTS[rule['checkpoint']]}／対象：{'各ページ' if rule['scope'] == 'page' else '作品全体'}",
                      f"  - 条件：{rule['condition']}", f"  - 完了条件：{rule['completionCriteria']}"])
    lines.extend(['', f'<!-- process-checker:digest:{digest(rules)} -->', END])
    return '\n'.join(lines)


def projected_agents(root, data):
    path = safe_path(root, 'AGENTS.md')
    body = path.read_text(encoding='utf-8-sig')
    require(body.count(BEGIN) == body.count(END) and body.count(BEGIN) <= 1,
            'AGENTS.mdの管理区間が壊れています。自動更新を止めました。')
    block = strong_block(data)
    if BEGIN in body:
        start, finish = body.index(BEGIN), body.index(END) + len(END)
        require(start < finish - len(END), 'AGENTS.mdの管理区間の順序が不正です。')
        return body[:start] + block + body[finish:]
    return body.rstrip() + '\n\n' + block + '\n' if block else body


def save_registry(root, data):
    validate_registry(data)
    agents = projected_agents(root, data)
    old = registry(root)
    archive = f'.work/process-checker/changes/{uuid.uuid4().hex}.json'
    write_json(safe_path(root, archive), {'at': now(), 'before': old, 'after': data})
    write_json(safe_path(root, REQUIREMENTS), data)
    write_text(safe_path(root, 'AGENTS.md'), agents)


def state(root):
    path = safe_path(root, STATE)
    if not path.exists():
        return {'schemaVersion': 1, 'items': [], 'reports': []}
    value = read_json(path)
    require(isinstance(value, dict) and value.get('schemaVersion') == 1
            and isinstance(value.get('items'), list) and isinstance(value.get('reports'), list),
            '実施記録が不正です。未実施と区別して確認してください。')
    for item in value['items']:
        require(isinstance(item, dict) and all(nonempty(item.get(key)) for key in
                ('id', 'subject', 'revision', 'ruleDigest', 'status', 'note'))
                and item['status'] in STATUSES and isinstance(item.get('evidence'), list),
                '実施記録の項目が不正です。記録を確認してください。')
        require(all(isinstance(entry, dict) and nonempty(entry.get('path'))
                    and isinstance(entry.get('sha256'), str)
                    and re.fullmatch(r'[0-9a-f]{64}', entry['sha256'])
                    for entry in item['evidence']), '実施記録の根拠が不正です。')
    return value


def evidence(root, paths):
    require(isinstance(paths, list) and all(isinstance(p, str) for p in paths), '根拠は相対パスの配列にします。')
    result = []
    for relative in dict.fromkeys(paths):
        require(not any(part in ('.git', '.secrets') for part in Path(relative).parts), '秘密情報を根拠へ登録しません。')
        path = safe_path(root, relative)
        require(path.is_file(), f'根拠ファイルがありません: {relative}')
        result.append({'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return result


def effective_items(root, data, current):
    rules = {r['id']: r for r in data['requirements']}
    items = deepcopy(current['items'])
    for item in items:
        rule = rules.get(item['id'])
        if rule is None or item.get('superseded'):
            item['status'] = '対象外'
            continue
        item['level'] = rule['level']
        stale = item['ruleDigest'] != digest(rule)
        for entry in item.get('evidence', []):
            try:
                stale = stale or evidence(root, [entry['path']])[0]['sha256'] != entry['sha256']
            except ValueError:
                stale = True
        if stale:
            item['status'] = '未確認'
            item['note'] = '指示または根拠が変更されたため再照合が必要です。'
    return items


def summary(root):
    data = registry(root)
    require(projected_agents(root, data) == safe_path(root, 'AGENTS.md').read_text(encoding='utf-8-sig'),
            '強い指示とAGENTS.mdが不一致です。内容を確認してsync-agentsを実行してください。')
    items = effective_items(root, data, state(root))
    return {'enabled': bool(data['requirements']), 'requirements': data['requirements'],
            'pending': [item for item in items if item['status'] not in ('実施済み', '対象外')],
            'note': '未報告の対象は確認済みではありません。条件・根拠の内容はSkillで照合します。'}


def report(root, value):
    data = registry(root)
    require(isinstance(value, dict), '報告はJSONオブジェクトにします。')
    if not data['requirements']:
        return {'enabled': False, 'message': '必須事項が０件のため詳細な照合は行いません。'}
    if value.get('noProgress') is True:
        require(nonempty(value.get('note')), '進捗がない理由を記入してください。')
        current = state(root)
        current['reports'].append({'at': now(), 'noProgress': True, 'note': value['note']})
        write_json(safe_path(root, STATE), current)
        mark_reported(root, data, no_progress=True)
        return {'message': '工程進捗なしを記録しました。既存の必須事項を完了扱いにはしません。'}
    checkpoint = value.get('checkpoint')
    require(isinstance(checkpoint, str) and checkpoint in CHECKPOINTS, '報告の確認時点が不正です。')
    require(value.get('scope') in ('project', 'page') and nonempty(value.get('subject'))
            and nonempty(value.get('revision')), '報告の対象単位・対象ID・版が必要です。')
    current = state(root)
    current['items'] = effective_items(root, data, current)
    due = []
    for rule in data['requirements']:
        if RANK[rule['checkpoint']] > RANK[checkpoint]:
            continue
        if rule['scope'] == 'page' and value['scope'] != 'page':
            continue
        subject = value['subject'] if rule['scope'] == 'page' else 'project'
        revision = value['revision'] if rule['scope'] == 'page' else 'project'
        matches = [i for i in current['items'] if i['id'] == rule['id'] and i['subject'] == subject
                   and i['revision'] == revision and not i.get('superseded')]
        if matches:
            item = matches[0]
        else:
            for previous in current['items']:
                if previous['id'] == rule['id'] and previous['subject'] == subject:
                    previous['superseded'] = True
            item = {'id': rule['id'], 'subject': subject, 'revision': revision, 'level': rule['level'],
                    'ruleDigest': digest(rule), 'status': '未確認', 'note': '実施の根拠が未報告です。', 'evidence': []}
            current['items'].append(item)
        due.append((rule, item))
    results = value.get('results', [])
    require(isinstance(results, list) and all(isinstance(r, dict) for r in results), '照合結果は配列にします。')
    ids = [r.get('id') for r in results]
    require(all(isinstance(i, str) for i in ids) and len(ids) == len(set(ids))
            and set(ids) <= {r['id'] for r, _ in due}, '報告IDが重複しているか、今回の確認対象外です。')
    for result in results:
        require(isinstance(result.get('status'), str) and result['status'] in STATUSES
                and nonempty(result.get('note')), '状態と照合内容が必要です。')
        proof = evidence(root, result.get('evidence', []))
        require(result['status'] != '実施済み' or proof, '実施済みには根拠ファイルが必要です。')
        rule, item = next(pair for pair in due if pair[0]['id'] == result['id'])
        item.update(status=result['status'], note=result['note'], evidence=proof,
                    ruleDigest=digest(rule), checkedAt=now())
    current['reports'].append({'at': now(), 'checkpoint': checkpoint, 'subject': value['subject'],
                               'revision': value['revision']})
    write_json(safe_path(root, STATE), current)
    mark_reported(root, data)
    return summary(root)


def mark_reported(root, data, no_progress=False):
    path = safe_path(root, TURN)
    if path.exists():
        value = read_json(path)
        value.update(reported=True, registryDigest=digest(data), noProgress=no_progress)
        write_json(path, value)


def import_requirements(root, source):
    require(not registry(root)['requirements'], '引き継ぎ先に指示があるため自動統合しません。')
    source = project_root(source)
    require(source.resolve() != root.resolve(), '同じ作品からは引き継げません。')
    data = registry(source)
    inherited = {'schemaVersion': 1, 'requirements': [deepcopy(r) for r in data['requirements'] if r['carryForward']]}
    save_registry(root, inherited)
    # 実施済み・回答待ち・旧成果物・Hooks設定や信頼の記録はコピーしない。
    return {'count': len(inherited['requirements']), 'message': '選択した作品の引継ぎ対象指示だけをコピーしました。Hooksは未導入です。'}


def hook_definitions():
    # project.jsonを目印に親へ遡る。Git未初期化の作品・サブディレクトリ起動にも対応する。
    code = ("import pathlib,runpy,sys; p=pathlib.Path.cwd(); "
            "r=next(q for q in (p,*p.parents) if (q/'project.json').is_file() "
            "and (q/'scripts/process_checker.py').is_file()); "
            "s=str(r/'scripts/process_checker.py'); sys.argv=[s,'--project',str(r),'hook']; "
            "runpy.run_path(s,run_name='__main__')")
    handler = {'type': 'command', 'command': f'python3 -X utf8 -c "{code}"',
               'commandWindows': f'python -X utf8 -c "{code}"', 'timeout': 15,
               'statusMessage': HOOK_LABEL}
    return {event: [{'hooks': [deepcopy(handler)]}] for event in ('UserPromptSubmit', 'Stop')}


def install_hooks(root, apply):
    require(any(r['enforcement'] == 'agents+hooks' for r in registry(root)['requirements']),
            'Hooksの利用を相談して登録した強い指示がありません。')
    path = safe_path(root, '.codex/hooks.json')
    old = read_json(path) if path.exists() else {}
    require(isinstance(old, dict) and isinstance(old.get('hooks', {}), dict), '既存Hooksの形式が不正です。')
    updated = deepcopy(old)
    hooks = updated.setdefault('hooks', {})
    for event, groups in hook_definitions().items():
        existing = hooks.setdefault(event, [])
        require(isinstance(existing, list), '既存Hooksの形式が不正です。')
        # 自分のコマンドだけを識別して更新し、他のハンドラーを保持する。
        for group in existing:
            require(isinstance(group, dict) and isinstance(group.get('hooks'), list), '既存Hooksの形式が不正です。')
            require(all(isinstance(h, dict) for h in group['hooks']), '既存Hooksのハンドラーが不正です。')
            group['hooks'] = [h for h in group['hooks'] if not
                              (h.get('statusMessage') == HOOK_LABEL and isinstance(h.get('command'), str)
                               and 'scripts/process_checker.py' in h['command'])]
        hooks[event] = [g for g in existing if g['hooks']] + groups
    if apply:
        write_json(safe_path(root, f'.work/process-checker/hooks-before-{uuid.uuid4().hex}.json'), old)
        write_json(path, updated)
    return {'applied': apply, 'configuration': updated,
            'message': '設定の保存と実行の信頼は別です。CodexのHooks画面でレビュー・信頼し、利用環境で動作を確認してください。'}


def hook(root, event):
    require(isinstance(event, dict), 'Hookイベントが不正です。')
    data = registry(root)
    strong = [r for r in data['requirements'] if r['enforcement'] == 'agents+hooks']
    if not strong:
        return {}
    name = event.get('hook_event_name')
    if name == 'UserPromptSubmit':
        with editing(root):
            write_json(safe_path(root, TURN), {'turnId': event.get('turn_id'), 'reported': False})
        return {'hookSpecificOutput': {'hookEventName': name, 'additionalContext':
                'この作品には強い工程指示があります。config/process-requirements.jsonを読み、'
                '工程の着手前・完了時はプロセスチェッカーを使用してください。'
                '相談だけならnoProgress報告で終了できます。待機中のユーザーへ同じ質問を繰り返さないでください。'}}
    if name != 'Stop':
        return {}
    result = summary(root)
    turn_path = safe_path(root, TURN)
    turn = read_json(turn_path) if turn_path.exists() else {}
    reported = (turn.get('turnId') == event.get('turn_id') and turn.get('reported')
                and turn.get('registryDigest') == digest(data))
    ids = {r['id'] for r in strong}
    missing = [i for i in result['pending'] if i['id'] in ids and i['status'] in ('未実施', '未確認')]
    if reported and (not missing or turn.get('noProgress') is True):
        return {}
    if event.get('stop_hook_active'):
        return {'systemMessage': '工程確認の自動継続は１回で停止しました。未確認事項を明示して引き継いでください。'}
    return {'decision': 'block', 'reason':
            'プロセスチェッカーで今回の進捗と強い指示の根拠を照合し、reportを保存してください。'
            '進捗がない相談はnoProgress報告、ユーザーの回答が必要な事項は回答待ちとして扱ってください。'
            '未確認を実施済みにせず、関係のない創作へ追加の制約を設けないでください。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', default=str(Path(__file__).resolve().parents[1]), help='作品ルート')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='登録事項と未解決の照合結果を表示')
    commands.add_parser('checkpoints', help='登録できる確認時点を表示')
    for name in ('add', 'replace'):
        command = commands.add_parser(name, help='相談済みの指示JSONを登録')
        command.add_argument('--input', required=True, help='作品内の入力JSON相対パス')
    command = commands.add_parser('remove', help='ユーザーが解除した指示を削除')
    command.add_argument('--id', required=True)
    command.add_argument('--decision-note', required=True)
    command = commands.add_parser('report', help='根拠を照合した結果を保存')
    command.add_argument('--input', required=True)
    commands.add_parser('sync-agents', help='確認した正本からAGENTS.mdの管理区間だけを更新')
    command = commands.add_parser('import', help='明示された旧作品の引継ぎ対象だけをコピー')
    command.add_argument('--from-project', required=True)
    command = commands.add_parser('validate-source', help='明示された引継ぎ元の形式だけを確認')
    command.add_argument('--from-project', required=True)
    command = commands.add_parser('install-hooks', help='Hooksの具体的な変更を提示。適用は別途指定')
    command.add_argument('--apply', action='store_true')
    commands.add_parser('hook', help='Codexから渡されるイベントを処理')
    args = parser.parse_args()
    if args.command == 'checkpoints':
        return CHECKPOINTS
    if args.command == 'validate-source':
        data = registry(project_root(args.from_project))
        return {'count': sum(r['carryForward'] for r in data['requirements'])}
    root = project_root(args.project)
    if args.command == 'status':
        return summary(root)
    if args.command == 'hook':
        return hook(root, json.load(sys.stdin))
    with editing(root):
        data = registry(root)
        if args.command in ('add', 'replace'):
            rule = read_json(safe_path(root, args.input))
            require(isinstance(rule, dict), '指示はJSONオブジェクトにします。')
            if args.command == 'add':
                rule.setdefault('id', 'proc-' + uuid.uuid4().hex[:12])
                require(rule['id'] not in [r['id'] for r in data['requirements']], '既存IDです。replaceで変更してください。')
                data['requirements'].append(rule)
            else:
                require(rule.get('id') in [r['id'] for r in data['requirements']], '変更対象IDがありません。')
                data['requirements'] = [rule if r['id'] == rule['id'] else r for r in data['requirements']]
            save_registry(root, data)
            return {'id': rule['id'], 'message': '指示を登録し、強い指示をAGENTS.mdに反映しました。Hooksは別途設定します。'}
        if args.command == 'remove':
            require(nonempty(args.decision_note), '解除のユーザー指示を記録してください。')
            require(args.id in [r['id'] for r in data['requirements']], '削除対象IDがありません。')
            data['requirements'] = [r for r in data['requirements'] if r['id'] != args.id]
            save_registry(root, data)
            write_json(safe_path(root, f'.work/process-checker/removals/{uuid.uuid4().hex}.json'),
                       {'id': args.id, 'at': now(), 'decisionNote': args.decision_note})
            return {'message': '指定した指示を解除しました。他の指示と記録は保持しています。'}
        if args.command == 'sync-agents':
            write_text(safe_path(root, 'AGENTS.md'), projected_agents(root, data))
            return {'message': 'AGENTS.mdの強い指示を同期しました。Hooksの有効化は別です。'}
        if args.command == 'report':
            return report(root, read_json(safe_path(root, args.input)))
        if args.command == 'import':
            return import_requirements(root, args.from_project)
        if args.command == 'install-hooks':
            return install_hooks(root, args.apply)
    raise ValueError('未対応の操作です。')


if __name__ == '__main__':
    try:
        print(json.dumps(main(), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as exc:
        # Hookエラーも黙って合格にしない。Stopは無限継続させず警告として返す。
        if 'hook' in sys.argv:
            print(json.dumps({'systemMessage': 'プロセスチェッカーで確認できませんでした: ' + str(exc)}, ensure_ascii=False))
        else:
            print('プロセスチェッカー: ' + str(exc), file=sys.stderr)
            sys.exit(1)
