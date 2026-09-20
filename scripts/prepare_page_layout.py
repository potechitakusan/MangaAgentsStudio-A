"""作品の基本枠にコマ座標を配置する。絵や文字を変形せず、補助線を別出力にする。"""
from __future__ import annotations

import argparse
import copy
import html
import json
import math
from pathlib import Path
import struct


def number(value, name, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name}には有限の数値を指定してください。')
    if value < 0 or (positive and value == 0):
        raise ValueError(f'{name}の範囲が不正です。')
    return value


def canvas_size(value, name):
    if not isinstance(value, dict) or any(type(value.get(key)) is not int or value[key] <= 0
                                          for key in ('width', 'height')):
        raise ValueError(f'{name}の幅・高さは正の整数pxにしてください。')
    return {key: value[key] for key in ('width', 'height')}


def png_size(path):
    """PNGのIHDRに記録された実寸だけを読む。画像の変換・再保存はしない。"""
    with Path(path).open('rb') as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR':
        raise ValueError('ページ画像にはPNGを指定してください。')
    width, height = struct.unpack('>II', header[16:24])
    return canvas_size({'width': width, 'height': height}, '生成画像の実寸')


def uniform_scale(source, target, name):
    if source['width'] * target['height'] != source['height'] * target['width']:
        raise ValueError(f'{name}の縦横比が異なります。配置・余白・切り抜きの方針を決め、別工程で調整してください。')
    return target['width'] / source['width']


def resolve_config(config, canvas=None, generated_canvas=None):
    """基準寸法から毎回換算し、元設定は変更しない。版1は従来のpx指定を保持する。"""
    if not isinstance(config, dict) or type(config.get('schemaVersion')) is not int or config['schemaVersion'] not in (1, 2):
        raise ValueError('ページ設定のschemaVersionは1または2にしてください。')
    version = config['schemaVersion']
    reference = canvas_size(config['referenceCanvas'] if version == 2 else config['canvas'], '換算の基準寸法')
    requested = config.get('generationCanvas')
    if requested is not None:
        requested = canvas_size(requested, '生成時の希望寸法')
    if generated_canvas is not None:
        generated_canvas = canvas_size(generated_canvas, '生成画像の実寸')
    configured = config.get('canvas')
    if configured is not None:
        configured = canvas_size(configured, '枠配置の寸法')
    working = canvas if canvas is not None else configured
    if working is None:
        working = generated_canvas if generated_canvas is not None else requested
    if working is None:
        raise ValueError('枠配置の寸法が未確定です。生成後は--page-image、生成前やコマ別制作では--canvas 幅 高さを指定してください。')
    working = canvas_size(working, '枠配置の寸法')
    export = config.get('exportCanvas')
    export = canvas_size(export, '最終PNGの寸法') if export is not None else copy.deepcopy(working)
    export_scale = uniform_scale(working, export, '枠配置と最終PNG')
    image_scale = uniform_scale(generated_canvas, working, '生成画像と枠配置') if generated_canvas is not None else None

    # 元の基準値も検証し、不正な値を上書きで隠さない。
    base = {key: copy.deepcopy(config[key]) for key in ('basicFrame', 'textSafeArea', 'frameStroke', 'showGuide')}
    validate_config({'schemaVersion': 1, 'canvas': reference, **base})
    sx, sy = (working[key] / reference[key] for key in ('width', 'height'))
    stroke_scale = min(sx, sy)
    effective = {'schemaVersion': 1, 'canvas': working, **base}
    for name in ('basicFrame', 'textSafeArea'):
        effective[name] = {side: value * (sx if side in ('left', 'right') else sy)
                           for side, value in base[name].items()}
    effective['frameStroke'] *= stroke_scale
    fixed = config.get('fixedPixels', {})
    if not isinstance(fixed, dict) or set(fixed) - {'basicFrame', 'textSafeArea', 'frameStroke'}:
        raise ValueError('fixedPixelsには基本枠・文字安全範囲の余白または枠線だけを指定してください。')
    for name in ('basicFrame', 'textSafeArea'):
        if name in fixed:
            if not isinstance(fixed[name], dict) or set(fixed[name]) - {'left', 'top', 'right', 'bottom'}:
                raise ValueError(f'fixedPixels.{name}にはleft・top・right・bottomを指定してください。')
            effective[name].update(fixed[name])
    if 'frameStroke' in fixed:
        effective['frameStroke'] = fixed['frameStroke']
    effective['guideStroke'] = 3 * stroke_scale
    effective['guideDash'] = [16 * stroke_scale, 10 * stroke_scale]
    validate_config(effective)
    dimensions = {'generationRequested': requested, 'generationActual': generated_canvas,
                  'working': copy.deepcopy(working), 'export': export, 'reference': reference,
                  'generationToWorkingScale': image_scale, 'workingToExportScale': export_scale}
    return effective, dimensions


def validate_config(config):
    if not isinstance(config, dict) or type(config.get('schemaVersion')) is not int or config['schemaVersion'] != 1:
        raise ValueError('ページ設定のschemaVersionは1にしてください。')
    width, height = (config['canvas'][key] for key in ('width', 'height'))
    for value in (width, height):
        if type(value) is not int or value <= 0:
            raise ValueError('ページの幅・高さは正の整数pxにしてください。')
    for name in ('basicFrame', 'textSafeArea'):
        margins = config[name]
        for side in ('left', 'top', 'right', 'bottom'):
            number(margins[side], f'{name}.{side}')
        if margins['left'] + margins['right'] >= width or margins['top'] + margins['bottom'] >= height:
            raise ValueError(f'{name}の内側に正の面積が必要です。')
    number(config['frameStroke'], 'frameStroke', positive=True)
    if type(config['showGuide']) is not bool:
        raise ValueError('showGuideはtrueまたはfalseにしてください。')


def place_template(item, source_canvas, config):
    """基本枠内の比率で枠の座標だけを変換する。演出領域も同じ変換を使う。"""
    validate_config(config)
    inset = number(source_canvas['frameInset'], 'frameInset')
    source_width = number(source_canvas['width'], 'width', positive=True) - 2 * inset
    source_height = number(source_canvas['height'], 'height', positive=True) - 2 * inset
    if source_width <= 0 or source_height <= 0:
        raise ValueError('元の基本枠の面積が不正です。')
    frame = config['basicFrame']
    width = config['canvas']['width'] - frame['left'] - frame['right']
    height = config['canvas']['height'] - frame['top'] - frame['bottom']

    def transform(polygon):
        return [[round(frame['left'] + (x - inset) * width / source_width, 6),
                 round(frame['top'] + (y - inset) * height / source_height, 6)] for x, y in polygon]

    placed = copy.deepcopy(item)
    # 元素材へのリンク・元の座標系を変換後のデータに残さない。
    placed.pop('assets', None)
    placed['coordinateSystem'] = {**config['canvas'], 'origin': '左上', 'unit': 'px'}
    for panel in placed['panels']:
        panel['polygon'] = transform(panel['polygon'])
    for modifier in placed.get('modifiers', []):
        if 'region' in modifier:
            modifier['region'] = transform(modifier['region'])
    return placed


def svg_start(config, title):
    width, height = (config['canvas'][key] for key in ('width', 'height'))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><title>{html.escape(title)}</title>')


def polygon_svg(polygon, **attributes):
    points = ' '.join(f'{x:g},{y:g}' for x, y in polygon)
    attrs = ' '.join(f'{key.replace("_", "-")}="{html.escape(str(value), quote=True)}"' for key, value in attributes.items())
    return f'<polygon points="{points}" {attrs}/>'


def frames_svg(placed, config):
    parts = [svg_start(config, 'コマ枠'), '<g id="panels">']
    for panel in placed['panels']:
        parts.append(polygon_svg(panel['polygon'], id=panel['id'], fill='none', stroke='#000',
                                 stroke_width=config['frameStroke'], stroke_linejoin='miter'))
    return ''.join(parts) + '</g></svg>'


def guide_svg(placed, config):
    stroke = config.get('guideStroke', 3)
    dash = ' '.join(f'{value:g}' for value in config.get('guideDash', [16, 10]))
    parts = [svg_start(config, '確認専用の基本枠・文字安全範囲'),
             f'<g id="guides" fill="none" stroke-width="{stroke:g}" stroke-dasharray="{dash}">']
    for name, color in (('basicFrame', '#087ac1'), ('textSafeArea', '#b04490')):
        margin = config[name]
        width = config['canvas']['width'] - margin['left'] - margin['right']
        height = config['canvas']['height'] - margin['top'] - margin['bottom']
        parts.append(f'<rect id="{name}" x="{margin["left"]}" y="{margin["top"]}" width="{width}" height="{height}" stroke="{color}"/>')
    for modifier in placed.get('modifiers', []):
        if 'region' in modifier:
            parts.append(polygon_svg(modifier['region'], stroke='#a85e27'))
    return ''.join(parts) + '</g></svg>'


def prepare(catalog, template_id, config, output, show_guide=None, *, canvas=None, page_image=None):
    config, dimensions = resolve_config(config, canvas, png_size(page_image) if page_image is not None else None)
    candidates = [item for item in catalog['templates'] if item['id'] == template_id]
    if len(candidates) != 1:
        raise ValueError('テンプレートIDが見つからないか、重複しています。')
    placed = place_template(candidates[0], catalog['canvas'], config)
    enabled = config['showGuide'] if show_guide is None else show_guide
    # 既存のガイドや作業素材との混在を避けるため、毎回新しい出力先を使う。
    output = Path(output)
    if output.exists():
        raise ValueError('出力先が既にあります。新しいフォルダを指定してください。')
    record = {'schemaVersion': 2, 'page': copy.deepcopy(config), 'dimensions': dimensions, 'template': placed,
              'files': {'frames': 'frames.svg', 'guide': 'guide.svg' if enabled else None}}
    record['page']['showGuide'] = enabled
    output.mkdir(parents=True)
    (output / 'frames.svg').write_text(frames_svg(placed, config), encoding='utf-8')
    if enabled:
        (output / 'guide.svg').write_text(guide_svg(placed, config), encoding='utf-8')
    (output / 'layout.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config/page-layout.json', help='作品のページ設定')
    parser.add_argument('--catalog', default='templates/panel-templates/catalog.json', help='同梱カタログ')
    parser.add_argument('--template', required=True, help='採用するコマ枠ID')
    parser.add_argument('--output', required=True, help='新規の出力フォルダ')
    parser.add_argument('--page-image', help='１ページ全体の生成PNG。ヘッダーの実寸から枠配置寸法を決める')
    parser.add_argument('--canvas', nargs=2, type=int, metavar=('WIDTH', 'HEIGHT'),
                        help='枠配置の幅・高さ。生成前の仮配置やコマ別制作、明示的な寸法変更に使う')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--guide', action='store_true', dest='guide', help='確認用ガイドを別ファイルに出力')
    group.add_argument('--no-guide', action='store_false', dest='guide', help='ガイドを出力しない')
    parser.set_defaults(guide=None)
    args = parser.parse_args()
    try:
        config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
        catalog = json.loads(Path(args.catalog).read_text(encoding='utf-8-sig'))
        canvas = dict(zip(('width', 'height'), args.canvas)) if args.canvas is not None else None
        record = prepare(catalog, args.template, config, args.output, args.guide, canvas=canvas, page_image=args.page_image)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'ページ配置を作成できません: {error}\n')
    print(json.dumps({'template': args.template, 'dimensions': record['dimensions'], 'files': record['files']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
