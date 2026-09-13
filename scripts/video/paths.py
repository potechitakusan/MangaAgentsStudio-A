"""記録ファイルを移動しても使える相対パスの補助。"""
from __future__ import annotations

import copy
import os
from pathlib import Path


def relative_path(path, base):
    """baseを基準にした相対パスを返す。別ドライブは保存前に拒否する。"""
    try:
        return Path(os.path.relpath(Path(path).resolve(), Path(base).resolve())).as_posix()
    except ValueError as error:
        raise ValueError('素材と記録は相対パスで参照できる同じドライブに置いてください。') from error


def portable_probe(info, base):
    result = copy.deepcopy(info)
    if 'filename' in result.get('format', {}):
        result['format']['filename'] = relative_path(result['format']['filename'], base)
    return result


def portable_command(command, base):
    """実行コマンドのファイル引数を記録の保存先基準へ変換する。"""
    result = list(command)
    executable = Path(result[0])
    if executable.is_absolute() or executable.parent != Path('.'):
        result[0] = relative_path(executable, base)
    for index, token in enumerate(command[:-1]):
        if token == '-i':
            result[index + 1] = relative_path(command[index + 1], base)
    result[-1] = relative_path(command[-1], base)
    return result
