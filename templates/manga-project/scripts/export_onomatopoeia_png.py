"""軽量テンプレートの1素材を、互換用PNGとして作品内へ書き出す。"""
from pathlib import Path
import argparse,json
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];TPL=ROOT/'templates/onomatopoeia'
ap=argparse.ArgumentParser();ap.add_argument('asset_id');ap.add_argument('--output');args=ap.parse_args()
catalog=json.loads((TPL/'catalog.json').read_text(encoding='utf-8'))
entry=next((x for x in catalog['entries'] if x['id']==args.asset_id),None)
if entry is None:raise SystemExit('該当する素材IDがありません。catalog.jsonで確認してください。')
target=(ROOT/(args.output or f'output/onomatopoeia-exports/{args.asset_id}.png')).resolve();target.relative_to(ROOT)
if target.exists():raise SystemExit('既存ファイルは上書きしません。別の出力先を指定してください。')
target.parent.mkdir(parents=True,exist_ok=True);Image.open(TPL/entry['image']['path']).convert('RGBA').save(target,optimize=True)
print(target)
