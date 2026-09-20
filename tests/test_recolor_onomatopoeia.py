"""色替えの画素保持、入力検証、保存の安全性を確認する。"""

from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid

from PIL import Image, PngImagePlugin, features

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_SCRIPTS = ROOT / "templates" / "manga-project" / "scripts"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

from recolor_onomatopoeia import main, parse_color, recolor_file, recolor_image


def sample_image():
    image = Image.new("RGBA", (7, 1))
    image.putdata([
        (0, 0, 0, 255), (128, 128, 128, 255), (255, 255, 255, 255),
        (20, 40, 60, 0), (0, 0, 0, 128), (128, 128, 128, 1), (255, 255, 255, 254),
    ])
    return image


class ColorTests(unittest.TestCase):
    def test_strict_colors(self):
        self.assertEqual(parse_color("#Aa09fF"), (170, 9, 255))
        for value in ("red", "#fff", "FFFFFF", "#12345678", "#12345g", " #123456",
                      "#123456\n", "#１２３４５６", "rgb(0,0,0)", "", None, 123, (0, 0, 0)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_color(value)

    def test_black_gray_white_and_alpha(self):
        source = sample_image()
        original = source.tobytes()
        result = recolor_image(source, ink_color="#204060", white_color="#E0C0A0")
        self.assertEqual(result.mode, "RGBA")
        self.assertEqual(result.size, source.size)
        self.assertEqual(result.getpixel((0, 0)), (32, 64, 96, 255))
        self.assertEqual(result.getpixel((1, 0)), (128, 128, 128, 255))
        self.assertEqual(result.getpixel((2, 0)), (224, 192, 160, 255))
        self.assertEqual(result.getpixel((3, 0)), (20, 40, 60, 0))
        self.assertEqual(result.getpixel((4, 0)), (32, 64, 96, 128))
        self.assertEqual(result.getpixel((5, 0)), (128, 128, 128, 1))
        self.assertEqual(result.getpixel((6, 0)), (224, 192, 160, 254))
        self.assertEqual(result.getchannel("A").tobytes(), source.getchannel("A").tobytes())
        self.assertEqual(source.tobytes(), original)

    def test_all_256_levels_and_alpha_values(self):
        source = Image.new("RGBA", (256, 256))
        source.putdata([(level, level, level, alpha) for alpha in range(256) for level in range(256)])
        result = recolor_image(source, ink_color="#FF0000", white_color="#00FF00")
        expected = Image.new("RGBA", source.size)
        expected.putdata([
            (255 - level, level, 0, alpha) if alpha else (level, level, level, 0)
            for alpha in range(256) for level in range(256)
        ])
        self.assertEqual(result.tobytes(), expected.tobytes())

    def test_no_change_and_monochrome_priority(self):
        source = sample_image()
        source.info["comment"] = "合成テスト用の非公開文字列"
        for options in ({}, {"monochrome": True}, {"ink_color": "#000000", "white_color": "#FFFFFF"},
                        {"monochrome": True, "ink_color": "#FF0000", "white_color": "#00FF00"}):
            with self.subTest(options=options):
                result = recolor_image(source, **options)
                self.assertIsNot(result, source)
                self.assertEqual(result.tobytes(), source.tobytes())
                self.assertEqual(result.info, {})
        self.assertIn("comment", source.info)

    def test_one_color_leaves_other_endpoint(self):
        source = sample_image()
        self.assertEqual(recolor_image(source, ink_color="#112233").getpixel((2, 0)), (255, 255, 255, 255))
        self.assertEqual(recolor_image(source, white_color="#112233").getpixel((0, 0)), (0, 0, 0, 255))

    def test_invalid_color_even_in_monochrome(self):
        for options in ({"ink_color": "#xyz123"}, {"white_color": ""},
                        {"monochrome": True, "ink_color": "red"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                recolor_image(sample_image(), **options)

    def test_reject_visible_color_including_alpha_one(self):
        for alpha in (1, 128, 255):
            source = sample_image()
            source.putpixel((1, 0), (128, 129, 128, alpha))
            for options in ({}, {"ink_color": "#FF0000"}, {"monochrome": True}):
                with self.subTest(alpha=alpha, options=options), self.assertRaisesRegex(ValueError, "非モノクロ"):
                    recolor_image(source, **options)

    def test_reject_opaque_even_with_alpha_channel(self):
        for mode, color in (("RGBA", (255, 255, 255, 255)), ("RGB", (0, 0, 0)), ("L", 128)):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "全面不透明"):
                recolor_image(Image.new(mode, (2, 2), color))

    def test_fully_transparent_image_is_unchanged(self):
        source = Image.new("RGBA", (2, 2), (12, 34, 56, 0))
        self.assertEqual(recolor_image(source, ink_color="#FF0000").tobytes(), source.tobytes())

    def test_la_and_palette_transparency(self):
        source = Image.new("LA", (3, 1))
        source.putdata([(0, 128), (255, 255), (128, 0)])
        result = recolor_image(source, ink_color="#FF0000")
        self.assertEqual(result.getpixel((0, 0)), (255, 0, 0, 128))
        palette = Image.new("P", (3, 1))
        palette.putpalette([0, 0, 0, 128, 128, 128, 255, 255, 255] + [0] * 759)
        palette.putdata([0, 1, 2])
        palette.info["transparency"] = bytes([255, 128, 0])
        self.assertEqual(recolor_image(palette).tobytes(), palette.convert("RGBA").tobytes())

    def test_reject_high_bit_depth(self):
        with self.assertRaisesRegex(ValueError, "8bit"):
            recolor_image(Image.new("I;16", (2, 2)))


class FileTests(unittest.TestCase):
    def setUp(self):
        # Windowsの制限トークンでも使える通常権限。削除対象は今回作った子だけ。
        temporary_root = ROOT / "tmp"
        temporary_root.mkdir(exist_ok=True)
        self.directory = temporary_root / f"recolor-tests-{uuid.uuid4().hex}"
        self.directory.mkdir(mode=0o777)
        self.addCleanup(shutil.rmtree, self.directory)
        self.source = self.directory / "元画像.png"
        sample_image().save(self.source)

    def read_rgba(self, path):
        with Image.open(path) as image:
            return image.convert("RGBA").tobytes()

    def test_reuse_source_without_writing(self):
        original = self.source.read_bytes()
        for options in ({}, {"monochrome": True}, {"monochrome": True, "ink_color": "#FF0000"}):
            self.assertEqual(recolor_file(self.source, **options), self.source.resolve())
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(list(self.directory.iterdir()), [self.source])

    def test_png_roundtrip_and_unchanged_outputs(self):
        expected = recolor_image(sample_image(), ink_color="#123456", white_color="#FEDCBA")
        target = self.directory / "派生" / "色版.PNG"
        self.assertEqual(recolor_file(self.source, target, ink_color="#123456", white_color="#FEDCBA"), target)
        self.assertEqual(self.read_rgba(target), expected.tobytes())
        for index, options in enumerate(({}, {"monochrome": True, "ink_color": "#FF0000"})):
            unchanged = self.directory / f"無変更{index}.png"
            recolor_file(self.source, unchanged, **options)
            self.assertEqual(self.read_rgba(unchanged), sample_image().tobytes())

    @unittest.skipUnless(features.check("webp"), "PillowにWebP対応がありません")
    def test_lossless_webp_roundtrip_including_hidden_rgb(self):
        webp_source = self.directory / "元画像.webp"
        sample_image().save(webp_source, lossless=True, exact=True)
        for input_path in (self.source, webp_source):
            for suffix in (".png", ".webp"):
                for changed in (False, True):
                    with self.subTest(input=input_path.suffix, output=suffix, changed=changed):
                        target = self.directory / f"派生-{input_path.suffix}-{changed}{suffix}"
                        options = {"ink_color": "#205080", "white_color": "#E0C0A0"} if changed else {}
                        recolor_file(input_path, target, **options)
                        self.assertEqual(self.read_rgba(target), recolor_image(sample_image(), **options).tobytes())
                        if suffix == ".webp":
                            self.assertIn(b"VP8L", target.read_bytes())

    def test_strip_input_metadata_including_no_change(self):
        image = sample_image()
        marker = "synthetic-private-test-marker"
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("comment", marker)
        exif = Image.Exif()
        exif[270] = marker
        image.save(self.source, pnginfo=metadata, exif=exif, icc_profile=marker.encode())
        source_bytes = self.source.read_bytes()
        self.assertIn(marker.encode(), source_bytes)
        suffixes = [".png"] + ([".webp"] if features.check("webp") else [])
        for suffix in suffixes:
            for changed in (False, True):
                with self.subTest(suffix=suffix, changed=changed):
                    target = self.directory / f"metadata-{changed}{suffix}"
                    recolor_file(self.source, target, **({"ink_color": "#FF0000"} if changed else {}))
                    with Image.open(target) as result:
                        for key in ("exif", "icc_profile", "xmp", "comment"):
                            self.assertNotIn(key, result.info)
                        self.assertEqual(dict(result.getexif()), {})
                    self.assertNotIn(marker.encode(), target.read_bytes())
        self.assertEqual(self.source.read_bytes(), source_bytes)

    def test_reject_same_file_even_with_overwrite_or_no_change(self):
        original = self.source.read_bytes()
        alias = self.directory / "同じ実体.png"
        os.link(self.source, alias)
        for target in (self.source, self.directory / "." / self.source.name, alias):
            for overwrite in (False, True):
                with self.subTest(target=target, overwrite=overwrite), self.assertRaisesRegex(ValueError, "同じファイル"):
                    recolor_file(self.source, target, overwrite=overwrite)
        self.assertEqual(self.source.read_bytes(), original)

    def test_reject_source_symlink_alias(self):
        alias = self.directory / "リンク.png"
        try:
            alias.symlink_to(self.source)
        except OSError as exc:
            self.skipTest(f"この環境ではシンボリックリンクを作成できません: {exc}")
        with self.assertRaisesRegex(ValueError, "同じファイル"):
            recolor_file(self.source, alias, overwrite=True)

    def test_existing_output_protection_and_overwrite(self):
        target = self.directory / "既存.png"
        target.write_bytes(b"existing-output")
        with self.assertRaises(FileExistsError):
            recolor_file(self.source, target, ink_color="#FF0000")
        self.assertEqual(target.read_bytes(), b"existing-output")
        recolor_file(self.source, target, ink_color="#FF0000", overwrite=True)
        self.assertEqual(self.read_rgba(target), recolor_image(sample_image(), ink_color="#FF0000").tobytes())
        self.assertEqual(list(self.directory.glob(".recolor-*")), [])

    def test_encoding_failure_keeps_existing_output(self):
        target = self.directory / "既存.png"
        target.write_bytes(b"existing-output")
        with patch.object(Image.Image, "save", side_effect=OSError("エンコード失敗")):
            with self.assertRaises(OSError):
                recolor_file(self.source, target, overwrite=True)
        self.assertEqual(target.read_bytes(), b"existing-output")

    def test_rejected_input_does_not_create_output(self):
        target = self.directory / "作らない" / "色版.png"
        for options in ({"ink_color": "red"}, {"white_color": "#123"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                recolor_file(self.source, target, **options)
        for image in (Image.new("RGB", (2, 2), "white"), Image.new("RGBA", (2, 2), (1, 2, 3, 128))):
            image.save(self.source)
            with self.assertRaises(ValueError):
                recolor_file(self.source, target)
        self.source.write_bytes(b"not-an-image")
        with self.assertRaises(OSError):
            recolor_file(self.source, target)
        self.assertFalse(target.parent.exists())

    def test_invalid_paths_and_output_formats(self):
        with self.assertRaises(FileNotFoundError):
            recolor_file(self.directory / "missing.png")
        with self.assertRaisesRegex(ValueError, "--output"):
            recolor_file(self.source, ink_color="#FF0000")
        for suffix in (".jpg", ".gif", ".tiff", ""):
            target = self.directory / f"invalid{suffix}"
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, "出力形式"):
                recolor_file(self.source, target)
            self.assertFalse(target.exists())
        target = self.directory / "directory.png"
        target.mkdir()
        with self.assertRaisesRegex(ValueError, "ファイル名"):
            recolor_file(self.source, target, overwrite=True)

    def test_reject_multiple_frames(self):
        target = self.directory / "アニメ.png"
        with BytesIO() as buffer:
            sample_image().save(buffer, format="PNG", save_all=True,
                                append_images=[Image.new("RGBA", (7, 1), (255, 255, 255, 128))])
            self.source.write_bytes(buffer.getvalue())
        with self.assertRaisesRegex(ValueError, "複数フレーム"):
            recolor_file(self.source, target)
        self.assertFalse(target.exists())

    def test_cli_reuse_monochrome_and_error(self):
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--input", str(self.source)]), 0)
            self.assertEqual(main(["--input", str(self.source), "--monochrome", "--ink-color", "#FF0000"]), 0)
        self.assertIn("元素材を使用", output.getvalue())
        errors = StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit) as caught:
            main(["--input", str(self.source), "--ink-color", "#wrong"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("#RRGGBB", errors.getvalue())

    def test_cli_script_from_another_directory(self):
        target = self.directory / "CLI色版.png"
        result = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(TEMPLATE_SCRIPTS / "recolor_onomatopoeia.py"),
             "--input", str(self.source), "--output", str(target),
             "--ink-color", "#204060", "--white-color", "#E0C0A0"],
            cwd=self.directory, capture_output=True, text=True, encoding="utf-8", check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("保存先", result.stdout)
        self.assertEqual(self.read_rgba(target), recolor_image(sample_image(), ink_color="#204060", white_color="#E0C0A0").tobytes())


if __name__ == "__main__":
    unittest.main()
