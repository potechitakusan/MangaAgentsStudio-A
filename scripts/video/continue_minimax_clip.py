"""Clone a tested I2V API graph for the next cut without changing model settings."""
import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .paths import relative_path
else:
    from paths import relative_path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--upload-record', type=Path, required=True)
    p.add_argument('--prompt-file', type=Path, required=True)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--prefix', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() or a.output.with_suffix('.continuation.json').exists():
        p.error('Output exists; choose a new version.')
    graph = json.loads(a.base.read_text(encoding='utf-8'))
    result = copy.deepcopy(graph)
    upload = json.loads(a.upload_record.read_text(encoding='utf-8'))
    filename = '/'.join(x for x in [upload.get('subfolder', ''), upload['name']] if x)
    replacements = {
        'LoadImage': ('image', filename),
        'MiniMaxH3ImageToVideo': ('prompt', a.prompt_file.read_text(encoding='utf-8')),
        'RandomNoise': ('noise_seed', a.seed),
        'SaveVideo': ('filename_prefix', a.prefix),
    }
    changes = []
    for kind, (key, value) in replacements.items():
        matches = [(nid, node) for nid, node in result.items() if node['class_type'] == kind]
        if len(matches) != 1:
            p.error(f'Expected exactly one {kind}; found {len(matches)}')
        nid, node = matches[0]
        node['inputs'][key] = value
        changes.append({'node': nid, 'input': key, 'value': value})
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if upload.get('local_image'):
        upload['local_image'] = relative_path(a.upload_record.parent / upload['local_image'], a.output.parent)
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'path_base': '.', 'base': relative_path(a.base, a.output.parent),
              'base_sha256': hashlib.sha256(a.base.read_bytes()).hexdigest(),
              'reference': upload, 'changes': changes}
    a.output.with_suffix('.continuation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(a.output), 'nodes': len(result), 'reference': filename}))


if __name__ == '__main__':
    main()
