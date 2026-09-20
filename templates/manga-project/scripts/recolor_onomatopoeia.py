"""透過モノクロ素材の明度を2色へ補間する。依存はPillowのみ。"""

from __future__ import annotations

import argparse
from io import BytesIO
import os
from pathlib import Path
import re
import tempfile
from typing import Sequence

from PIL import Image, ImageChops


def parse_color(value: str) -> tuple[int, int, int]:
    """#RRGGBBだけを受け付ける。色名、短縮形、alpha指定は不可。"""
    if not isinstance(value, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        raise ValueError("色は #RRGGBB 形式の半角16進数6桁で指定してください。")
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def _colors(
    ink_color: str | None, white_color: str | None, monochrome: bool
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    ink = (0, 0, 0) if ink_color is None else parse_color(ink_color)
    white = (255, 255, 255) if white_color is None else parse_color(white_color)
    # モノクロ指定を優先するが、不正な色指定を黙って受理しない。
    return ((0, 0, 0), (255, 255, 255)) if monochrome else (ink, white)


def recolor_image(
    image: Image.Image,
    *,
    ink_color: str | None = None,
    white_color: str | None = None,
    monochrome: bool = False,
) -> Image.Image:
    """新しいRGBA画像を返す。入力画像は変更せず、メタデータは引き継がない。

    可視画素（alpha > 0）は厳密にR=G=Bであることを要求する。
    全面不透明・複数フレーム・8bit RGBAへ無損失で変換できないモードは拒否。
    各RGB成分は round((ink * (255-L) + white * L) / 255) に相当する。
    全画素のalphaと、完全透明画素のRGBはそのまま保持する。
    """
    ink, white = _colors(ink_color, white_color, monochrome)
    if getattr(image, "n_frames", 1) != 1:
        raise ValueError("複数フレームの画像は対象外です。静止画1枚を指定してください。")
    if image.mode not in {"1", "L", "LA", "P", "PA", "RGB", "RGBA"}:
        raise ValueError("入力は8bitのRGB・グレースケール・パレット画像にしてください。")
    converted = image.convert("RGBA")
    # EXIFのキャッシュを含め、入力側の属性を新画像へ持ち込まない。
    rgba = Image.frombytes("RGBA", converted.size, converted.tobytes())
    red, green, blue, alpha = rgba.split()
    if alpha.getextrema()[0] == 255:
        raise ValueError("全面不透明の素材は対象外です。背景を透過した素材を指定してください。")
    visible = alpha.point([0] + [255] * 255)
    difference = ImageChops.lighter(
        ImageChops.difference(red, green), ImageChops.difference(red, blue)
    )
    if ImageChops.multiply(difference, visible).getbbox() is not None:
        raise ValueError("可視画素に非モノクロ色があります。R=G=Bの素材を指定してください。")
    if ink == (0, 0, 0) and white == (255, 255, 255):
        return rgba
    channels = [
        red.point([(start * (255 - level) + end * level + 127) // 255
                   for level in range(256)])
        for start, end in zip(ink, white)
    ]
    result = Image.merge("RGBA", (*channels, alpha))
    # 透明部分の隠れたRGBは補間対象から外し、元の値を保持する。
    result.paste(rgba, (0, 0), ImageChops.invert(visible))
    return result


def _check_output(source: Path, target: Path, overwrite: bool) -> None:
    if source.resolve() == target.resolve() or (
        target.exists() and source.samefile(target)
    ):
        raise ValueError("入力と同じファイルには出力できません（リンク経由も不可）。")
    if target.exists() and not target.is_file():
        raise ValueError("出力先にはファイル名を指定してください。")
    if os.path.lexists(target) and not overwrite:
        raise FileExistsError("出力先が既に存在します。上書きする場合は --overwrite を指定してください。")


def recolor_file(
    input_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str] | None = None,
    *,
    ink_color: str | None = None,
    white_color: str | None = None,
    monochrome: bool = False,
    overwrite: bool = False,
) -> Path:
    """検証・色替えし、保存先を返す。無変更かつ出力先なしなら入力の絶対パス。

    出力はPNGか可逆WebPのみ。入力と出力の同一ファイル指定は常に拒否する。
    無変更出力でも画素から再保存するので、入力メタデータはコピーしない。
    """
    _colors(ink_color, white_color, monochrome)
    source = Path(input_path).resolve(strict=True)
    target = Path(output_path).absolute() if output_path is not None else None
    if target is None and not monochrome and (ink_color is not None or white_color is not None):
        raise ValueError("色替えする場合は --output を指定してください。")
    if target is not None:
        if target.suffix.lower() not in {".png", ".webp"}:
            raise ValueError("出力形式は .png または .webp のみです。")
        _check_output(source, target, overwrite)
    with Image.open(source) as image:
        result = recolor_image(
            image, ink_color=ink_color, white_color=white_color, monochrome=monochrome
        )
    if target is None:
        return source

    # エンコードに失敗した場合、既存出力や出力フォルダへ触れない。
    with BytesIO() as buffer:
        if target.suffix.lower() == ".png":
            result.save(buffer, format="PNG")
        else:
            result.save(buffer, format="WEBP", lossless=True, exact=True, method=6)
        encoded = buffer.getvalue()
    _check_output(source, target, overwrite)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        # 排他的作成で、事前確認後に出現した既存ファイルも保護する。
        with target.open("xb") as stream:
            stream.write(encoded)
    else:
        # 上書き時も、書き込み成功後に置換して既存出力を保護する。
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".recolor-", delete=False) as stream:
                temporary_path = Path(stream.name)
                stream.write(encoded)
            _check_output(source, target, overwrite)
            os.replace(temporary_path, target)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    return target.resolve()


def main(argv: Sequence[str] | None = None) -> int:
    """CLI。成功は0、入力・保存のエラーは2。"""
    parser = argparse.ArgumentParser(
        description="透過モノクロ素材を2色で色替えし、PNGまたは可逆WebPへ保存します。",
        epilog="可視画素はR=G=B必須。全面不透明・複数フレームは不可。色名・alpha付き色は不可。",
    )
    parser.add_argument("--input", required=True, type=Path, help="入力の透過モノクロ画像")
    parser.add_argument("--output", type=Path, help="派生出力の.png/.webp。無変更なら省略可")
    parser.add_argument("--ink-color", metavar="#RRGGBB", help="黒部分の色。省略時は黒")
    parser.add_argument("--white-color", metavar="#RRGGBB", help="白部分の色。省略時は白")
    parser.add_argument("--monochrome", action="store_true", help="色指定より優先して元の画素を保持")
    parser.add_argument("--overwrite", action="store_true", help="既存の派生出力の上書きを許可")
    args = parser.parse_args(argv)
    try:
        path = recolor_file(
            args.input, args.output, ink_color=args.ink_color, white_color=args.white_color,
            monochrome=args.monochrome, overwrite=args.overwrite,
        )
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        parser.exit(2, f"エラー: {exc}\n")
    print(f"保存先: {path}" if args.output is not None else f"元素材を使用: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
