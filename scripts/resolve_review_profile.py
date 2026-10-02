#!/usr/bin/env python3
"""レビュー設定を検証し、場面に適用する重みをJSONで出力する。"""

import argparse
import json
from pathlib import Path
import sys

KEYS = (
    'immersion', 'cinema', 'story', 'readability',
    'characterConsistency', 'terminology',
)
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / 'config' / 'review-profiles.json'


def _assert_object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label} はJSONオブジェクトにしてください。')


def _assert_fields(value, allowed, label):
    for key in value:
        if key not in allowed:
            raise ValueError(f'{label} に不明な項目があります: {key}')


def _assert_weights(value, label, complete=False):
    _assert_object(value, label)
    _assert_fields(value, KEYS, label)
    for key in KEYS:
        if key not in value:
            if complete:
                raise ValueError(f'{label} に重みがありません: {key}')
            continue
        # boolはintの派生型だが、重みとしては受け付けない。
        if type(value[key]) is not int or not 1 <= value[key] <= 5:
            raise ValueError(f'{label}.{key} は1から5の整数にしてください。')


def _reject_constant(value):
    raise ValueError(f'JSONでは使用できない値です: {value}')


def resolve_profile(config_path=DEFAULT_CONFIG, preset='', scene_id='') -> dict:
    """全設定を検証し、既定値、プリセット、場面の順で重みを適用する。"""
    with Path(config_path).open(encoding='utf-8-sig') as source:
        config = json.load(source, parse_constant=_reject_constant)
    _assert_object(config, 'config')
    _assert_fields(config, ('schemaVersion', 'defaults', 'presets', 'scenes'), 'config')
    if type(config.get('schemaVersion')) is not int or config['schemaVersion'] != 1:
        raise ValueError('対応していないschemaVersionです。')
    _assert_weights(config.get('defaults'), 'defaults', complete=True)
    presets = config.get('presets')
    scenes = config.get('scenes')
    _assert_object(presets, 'presets')
    _assert_object(scenes, 'scenes')
    for name, weights in presets.items():
        if not name.strip():
            raise ValueError('プリセット名を空にはできません。')
        _assert_weights(weights, f'presets.{name}')
    for name, scene in scenes.items():
        if not name.strip():
            raise ValueError('場面名を空にはできません。')
        label = f'scenes.{name}'
        _assert_object(scene, label)
        _assert_fields(scene, ('preset', 'weights', 'reason'), label)
        if 'preset' in scene:
            if not isinstance(scene['preset'], str) or scene['preset'] not in presets:
                raise ValueError(f'場面のプリセットが不明です: {name}')
        if 'reason' in scene and not isinstance(scene['reason'], str):
            raise ValueError(f'場面の理由は文字列にしてください: {name}')
        if 'weights' in scene:
            _assert_weights(scene['weights'], f'{label}.weights')
    if preset and preset not in presets:
        raise ValueError(f'不明なプリセットです: {preset}')
    selected_scene = None
    if scene_id:
        if scene_id not in scenes:
            raise ValueError(f'不明な場面です: {scene_id}')
        selected_scene = scenes[scene_id]
        if 'preset' in selected_scene:
            preset = selected_scene['preset']
    effective = {key: config['defaults'][key] for key in KEYS}
    if preset:
        effective.update(presets[preset])
    if selected_scene is not None and 'weights' in selected_scene:
        effective.update(selected_scene['weights'])
    return {'schemaVersion': 1, 'sceneId': scene_id, 'preset': preset, 'weights': effective}


def main(argv=None):
    if sys.version_info < (3, 10):
        print('Python 3.10以上が必要です。', file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-path', '-ConfigPath', type=Path, default=DEFAULT_CONFIG,
                        help='レビュー設定のJSONファイル')
    parser.add_argument('--preset', '-Preset', default='', help='使用するプリセット名')
    parser.add_argument('--scene-id', '-SceneId', default='', help='使用する場面名')
    args = parser.parse_args(argv)
    try:
        result = resolve_profile(args.config_path, args.preset, args.scene_id)
    except (OSError, ValueError) as error:
        print(f'レビュー設定を解決できません: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
