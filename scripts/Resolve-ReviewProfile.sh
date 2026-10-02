#!/usr/bin/env bash
# PowerShell不要の入口。作業場所に依存せず引数をそのまま渡す。
set -euo pipefail
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ -n "${PYTHON:-}" ]]; then
    python_command="$PYTHON"
elif command -v python3 >/dev/null 2>&1; then
    python_command=python3
elif command -v python >/dev/null 2>&1; then
    python_command=python
else
    printf '%s\n' 'Python 3.10以上が必要です。python3を導入してください。' >&2
    exit 127
fi
if ! "$python_command" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    printf '%s\n' 'Python 3.10以上を指定してください。PYTHONには実行ファイルのパスを指定できます。' >&2
    exit 1
fi
exec "$python_command" -X utf8 "$SCRIPT_DIR/resolve_review_profile.py" "$@"
