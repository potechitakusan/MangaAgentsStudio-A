"""Submit and recover one local ComfyUI job without blind retries."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .paths import relative_path
else:
    from paths import relative_path


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def request(base, endpoint, data=None, headers=None, timeout=30):
    req = urllib.request.Request(base.rstrip('/') + endpoint, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'ComfyUI HTTP {exc.code}: {exc.read().decode("utf-8", "replace")}') from exc


def get_json(base, endpoint):
    return json.loads(request(base, endpoint))


def upload(args):
    path = Path(args.image)
    boundary = '----CodexManga' + uuid.uuid4().hex
    # A unique input name leaves existing ComfyUI assets intact.
    filename = 'codex-manga-' + uuid.uuid4().hex[:12] + path.suffix.lower()
    mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f'Content-Type: {mime}\r\n\r\n'
    ).encode() + path.read_bytes() + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\ninput\r\n--{boundary}--\r\n'.encode()
    result = json.loads(request(args.url, '/upload/image', body, {'Content-Type': f'multipart/form-data; boundary={boundary}'}))
    result.update(path_base='.', local_image=relative_path(path, Path(args.record).parent),
                  sha256=hashlib.sha256(path.read_bytes()).hexdigest(), uploaded_at=now())
    save(args.record, result)
    print(json.dumps(result, ensure_ascii=False))


def submit(args):
    record_path = Path(args.record)
    if record_path.exists():
        raise RuntimeError('Job record already exists. Inspect it before starting a new attempt.')
    graph_path = Path(args.prompt)
    graph_bytes = graph_path.read_bytes()
    graph = json.loads(graph_bytes.decode('utf-8-sig'))
    queue = get_json(args.url, '/queue')
    if queue.get('queue_running') or queue.get('queue_pending'):
        raise RuntimeError('ComfyUI queue is not empty. Wait for the current work; do not interrupt it.')
    client_id = 'codex-manga-' + uuid.uuid4().hex
    record = {'schema_version': 1, 'url': args.url, 'client_id': client_id, 'submitted_at': now(),
              'path_base': '.', 'prompt_file': relative_path(graph_path, record_path.parent), 'prompt_sha256': hashlib.sha256(graph_bytes).hexdigest(),
              'state': 'submission_pending', 'prompt_id': None}
    save(record_path, record)
    payload = json.dumps({'prompt': graph, 'client_id': client_id}).encode()
    try:
        response = json.loads(request(args.url, '/prompt', payload, {'Content-Type': 'application/json'}, timeout=60))
    except Exception as exc:
        record.update(state='submission_result_unknown', error=str(exc))
        save(record_path, record)
        raise
    record.update(state='queued', prompt_id=response['prompt_id'], response=response)
    save(record_path, record)
    print(json.dumps(record, ensure_ascii=False))


def inspect(args, record):
    prompt_id = record.get('prompt_id')
    if not prompt_id:
        raise RuntimeError('Submission has no confirmed prompt_id. Inspect queue/history by client_id; do not blindly resend.')
    history = get_json(record['url'], '/history/' + urllib.parse.quote(prompt_id))
    if prompt_id in history:
        item = history[prompt_id]
        status = item.get('status', {})
        record['status'] = status
        record['last_checked_at'] = now()
        if status.get('status_str') == 'error':
            record['state'] = 'failed'
        elif status.get('completed'):
            record['state'] = 'completed'
        record['history'] = item
        save(args.record, record)
        return record['state']
    queue = get_json(record['url'], '/queue')
    running = any(entry[1] == prompt_id for entry in queue.get('queue_running', []))
    pending = any(entry[1] == prompt_id for entry in queue.get('queue_pending', []))
    record.update(state='running' if running else 'queued' if pending else 'not_in_queue_or_history', last_checked_at=now())
    save(args.record, record)
    return record['state']


def status(args):
    record = json.loads(Path(args.record).read_text(encoding='utf-8-sig'))
    deadline = time.monotonic() + args.wait_seconds
    last_report = 0
    while True:
        state = inspect(args, record)
        if time.monotonic() - last_report >= 30 or state in ('completed', 'failed'):
            print(json.dumps({'prompt_id': record['prompt_id'], 'state': state, 'checked_at': now()}), flush=True)
            last_report = time.monotonic()
        if state in ('completed', 'failed') or time.monotonic() >= deadline:
            if state == 'failed':
                for kind, detail in record.get('status', {}).get('messages', []):
                    if kind in ('execution_error', 'execution_interrupted'):
                        print(json.dumps({k: detail.get(k) for k in ('node_id', 'node_type', 'exception_type', 'exception_message', 'traceback')}, ensure_ascii=False), flush=True)
                raise SystemExit(2)
            return
        if state == 'not_in_queue_or_history':
            raise RuntimeError('Job disappeared from queue/history. Inspect the server; do not automatically resubmit.')
        time.sleep(min(3, max(0, deadline - time.monotonic())))


def collect(args):
    record = json.loads(Path(args.record).read_text(encoding='utf-8-sig'))
    if inspect(args, record) != 'completed':
        raise RuntimeError('The requested job has not completed.')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    collected = []
    for node_id, node_output in record['history'].get('outputs', {}).items():
        for key in ('images', 'gifs', 'videos', 'audio'):
            for item in node_output.get(key, []):
                if not isinstance(item, dict) or not item.get('filename'):
                    continue
                name = Path(item['filename']).name
                target = output / (str(node_id) + '-' + name)
                if target.exists():
                    raise RuntimeError(f'Output exists; choose another collection directory: {target}')
                query = urllib.parse.urlencode({k: item.get(k, '') for k in ('filename', 'subfolder', 'type')})
                data = request(record['url'], '/view?' + query, timeout=120)
                target.write_bytes(data)
                collected.append({'node': node_id, 'server_file': item, 'local_file': relative_path(target, Path(args.record).parent),
                                  'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    if not collected:
        raise RuntimeError('No saved media found in this job history.')
    record['collected'] = collected
    record['collected_at'] = now()
    save(args.record, record)
    print(json.dumps(collected, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8188')
    sub = parser.add_subparsers(dest='command', required=True)
    up = sub.add_parser('upload')
    up.add_argument('--image', required=True)
    up.add_argument('--record', required=True)
    send = sub.add_parser('submit')
    send.add_argument('--prompt', required=True)
    send.add_argument('--record', required=True)
    check = sub.add_parser('status')
    check.add_argument('--record', required=True)
    check.add_argument('--wait-seconds', type=int, default=0)
    gather = sub.add_parser('collect')
    gather.add_argument('--record', required=True)
    gather.add_argument('--output', required=True)
    args = parser.parse_args()
    if urllib.parse.urlparse(args.url).hostname not in ('127.0.0.1', 'localhost', '::1'):
        parser.error('This helper is scoped to a local ComfyUI server.')
    {'upload': upload, 'submit': submit, 'status': status, 'collect': collect}[args.command](args)


if __name__ == '__main__':
    main()
