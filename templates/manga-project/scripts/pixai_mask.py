"""PixAIのインペイント用マスク（白＝描き直す、黒＝元のまま）を、元画像と同じ寸法で作る。通信しない。

  python -X utf8 scripts/pixai_mask.py --image output/pixai/candidates/p04-01/r001.png --ellipse 300,40,260,180 \
      --out input/pixai/masks/p04-01-ears.png

--ellipse・--rect は 左,上,幅,高さ（px）で、繰り返し指定できる。--blur で境界をぼかす（既定10px）。
確認用に、元画像へマスクを赤く重ねた <out>.preview.png も作る。送信前に開いて範囲を確かめる。
描き足す物が入る空き（例：耳なら頭の上の背景）を広く含め、描き直したくない大きな形は外す。
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pixai_api as api  # noqa: E402


def box(value: str) -> tuple[int, int, int, int]:
    parts = [int(v) for v in value.split(",")]
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
        raise argparse.ArgumentTypeError("左,上,幅,高さ の4つの整数にしてください。")
    return parts[0], parts[1], parts[0] + parts[2], parts[1] + parts[3]


def make_mask(size: tuple[int, int], ellipses, rects, blur: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for shape in ellipses:
        draw.ellipse(shape, fill=255)
    for shape in rects:
        draw.rectangle(shape, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur)) if blur > 0 else mask


def preview(source: Image.Image, mask: Image.Image) -> Image.Image:
    red = Image.new("RGB", source.size, (255, 0, 0))
    return Image.composite(red, source.convert("RGB"), mask.point(lambda v: v * 55 // 100))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="インペイント用マスクを作る（白＝描き直す）")
    parser.add_argument("--image", required=True, help="元画像（作品内の相対パス）")
    parser.add_argument("--ellipse", type=box, action="append", default=[], help="左,上,幅,高さ")
    parser.add_argument("--rect", type=box, action="append", default=[], help="左,上,幅,高さ")
    parser.add_argument("--blur", type=int, default=10, help="境界のぼかし半径（px）")
    parser.add_argument("--out", required=True, help="保存先のPNG（作品内の相対パス）")
    parser.add_argument("--force", action="store_true", help="同名のファイルを上書きする")
    opts = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        if not opts.ellipse and not opts.rect:
            raise api.ClientError("--ellipse か --rect を１つ以上指定してください。")
        out = api.project_path(root, opts.out)
        if out.suffix.lower() != ".png":
            raise api.ClientError("--out は .png にしてください。")
        check = out.with_name(out.stem + ".preview.png")
        if not opts.force and (out.exists() or check.exists()):
            raise api.ClientError(f"{opts.out} か確認用の画像が既にあります。上書きするなら --force を付けてください。")
        with Image.open(api.project_path(root, opts.image)) as source:
            source.load()
            mask = make_mask(source.size, opts.ellipse, opts.rect, opts.blur)
            out.parent.mkdir(parents=True, exist_ok=True)
            mask.save(out)
            preview(source, mask).save(check)
        share = sum(mask.histogram()[128:]) / (mask.width * mask.height)
        print(f"マスク: {opts.out}（{mask.width}×{mask.height}px、白の割合 {share:.0%}）")
        print(f"確認用: {check.relative_to(root).as_posix()}（赤い範囲が描き直される）")
        return 0
    except (api.ClientError, OSError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
