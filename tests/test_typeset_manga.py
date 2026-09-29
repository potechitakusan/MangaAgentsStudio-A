"""組版スクリプトの縦書きの字の扱い、点検、出力を確認する。"""

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_SCRIPTS = ROOT / "templates" / "manga-project" / "scripts"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

import typeset_manga as tm

PANELS = [
    {"id": "a", "order": 1, "polygon": [[510, 60], [940, 60], [940, 500], [510, 500]]},
    {"id": "b", "order": 2, "polygon": [[60, 60], [490, 60], [490, 500], [60, 500]]},
]


def spec(**extra):
    base = {"schema_version": 1, "page": {"size": [1000, 600]}, "panels": PANELS,
            "text": {"size": 28}, "no_keep_out": {"1": "試験", "2": "試験"}, "balloons": []}
    base.update(extra)
    return base


def balloon(**extra):
    base = {"id": "x", "panel": 1, "order": 1, "kind": "speech", "text": "こんにちは",
            "center": [720, 200], "tail": [720, 450]}
    base.update(extra)
    return base


def codes(problems):
    return {p["code"] for p in problems}


def run_check(s):
    page = tm.load_page(s, ROOT)
    defaults = {"size": 28.0, "max_chars": 10}
    balloons = [tm.Balloon(e, defaults, s.get("keep_out", [])) for e in s["balloons"]]
    return tm.check(s, page, balloons, None)


class CellTests(unittest.TestCase):
    def test_tate_chu_yoko_and_fullwidth(self):
        self.assertEqual(tm.to_cells("えっ!?"), ["え", "っ", "!?"])
        self.assertEqual(tm.to_cells("12月"), ["12", "月"])
        self.assertEqual(tm.to_cells("何!"), ["何", "！"])

    def test_wrap_keeps_line_start_rule(self):
        columns, wrapped = tm.wrap("あいうえおかきくけ、こ", 9)
        self.assertTrue(wrapped)
        self.assertEqual(columns[0][-1], "、")  # 句読点を行頭へ送らない
        columns, wrapped = tm.wrap("進路って\n言われても…", 10)
        self.assertFalse(wrapped)
        self.assertEqual(["".join(c) for c in columns], ["進路って", "言われても…"])

    def test_count_ignores_breaks_and_spaces(self):
        self.assertEqual(tm.count_chars("あい\nう　え"), 4)


class CheckTests(unittest.TestCase):
    def test_clean_balloon_has_no_errors(self):
        problems = run_check(spec(balloons=[balloon()]))
        self.assertFalse([p for p in problems if p["level"] == "error"], problems)

    def test_period_and_short_comma(self):
        problems = run_check(spec(balloons=[balloon(text="そう、だね。")]))
        self.assertTrue({"PUNCT_PERIOD", "PUNCT_COMMA"} <= codes(problems))

    def test_comma_counts_connected_group(self):
        first = balloon(id="p", text="あいうえおかきくけこ", group="g")
        second = balloon(id="q", order=2, text="さしすせそ、たちつてと", center=[600, 200], group="g")
        problems = run_check(spec(balloons=[first, second]))
        self.assertNotIn("PUNCT_COMMA", codes(problems))
        self.assertIn("PUNCT_COMMA_CHECK", codes(problems))

    def test_missing_tail_needs_reason(self):
        self.assertIn("NO_TAIL", codes([p for p in run_check(spec(balloons=[balloon(tail=None)])) if p["level"] == "warning"]))
        reasoned = run_check(spec(balloons=[balloon(tail=None, no_tail_reason="画面外の声")]))
        self.assertTrue(all(p["level"] == "info" for p in reasoned if p["code"] == "NO_TAIL"))

    def test_keep_out_and_tail_stops_before_face(self):
        face = {"panel": 1, "box": [650, 380, 800, 480], "label": "顔"}
        problems = run_check(spec(keep_out=[face], balloons=[balloon()]))
        self.assertNotIn("KEEP_OUT", codes(problems))
        self.assertNotIn("TAIL_INTO_KEEP_OUT", codes(problems))
        b = tm.Balloon(balloon(), {"size": 28.0, "max_chars": 10}, [face])
        self.assertLess(b.tail["tip"][1], 380)
        overlap = run_check(spec(keep_out=[{"panel": 1, "box": [680, 150, 760, 250]}], balloons=[balloon()]))
        self.assertIn("KEEP_OUT", codes(overlap))

    def test_keep_out_missing_is_warned(self):
        s = spec(balloons=[balloon()])
        s["no_keep_out"] = {}
        self.assertIn("KEEP_OUT_MISSING", codes(run_check(s)))

    def test_reading_order_and_overlap(self):
        first = balloon(id="p", center=[600, 250], tail=None, no_tail_reason="試験")
        second = balloon(id="q", order=2, center=[860, 120], tail=None, no_tail_reason="試験")
        self.assertIn("READ_ORDER", codes(run_check(spec(balloons=[first, second]))))
        close = balloon(id="r", order=2, center=[730, 220], tail=None, no_tail_reason="試験")
        self.assertIn("BALLOON_OVERLAP", codes(run_check(spec(balloons=[balloon(), close]))))

    def test_panel_and_order_errors(self):
        problems = run_check(spec(balloons=[balloon(), balloon(id="y", order=1, center=[600, 400]), balloon(id="z", panel=9)]))
        self.assertTrue({"PANEL", "ORDER"} <= codes(problems))


class RenderTests(unittest.TestCase):
    def setUp(self):
        try:
            tm.Fonts(ROOT, None)
        except FileNotFoundError:
            self.skipTest("日本語フォントがない環境")
        self.tmp = Path(tempfile.mkdtemp(dir=ROOT / "tests"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_outputs_layers_and_report(self):
        s = spec(balloons=[balloon(text="進路って\n言われても…"), balloon(id="m", panel=2, kind="monologue", text="無理ー", center=[270, 200])],
                 inserts=[{"id": "form", "panel": 2, "box": [100, 300, 400, 460], "title": "進路希望調査票", "lines": ["２年"]}])
        spec_path = self.tmp / "spec.json"
        spec_path.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
        rel = lambda p: p.relative_to(ROOT).as_posix()
        code = tm.main(["--spec", rel(spec_path), "--output", rel(self.tmp / "out"), "--root", str(ROOT)])
        self.assertEqual(code, 0)
        report = json.loads((self.tmp / "out" / "check.json").read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["error"], 0)
        for name in ("frames.png", "inserts.png", "balloons.png", "text.png", "preview.png", "preview-display.png", "check-overlay.png"):
            self.assertTrue((self.tmp / "out" / name).is_file(), name)
        with Image.open(self.tmp / "out" / "text.png") as text:
            self.assertEqual(text.size, (1000, 600))
            self.assertEqual(text.mode, "RGBA")
            self.assertIsNotNone(text.getchannel("A").getbbox())
        self.assertEqual([o["name"] for o in report["overlays_for_export_composed_psd"]],
                         ["差し込み（画中の文字）", "コマ枠", "フキダシ", "文字（画像）"])
        self.assertNotIn(":", report["font_file"])  # 絶対パスを記録しない

    def test_refuses_nonempty_output(self):
        (self.tmp / "out").mkdir()
        (self.tmp / "out" / "old.png").write_bytes(b"x")
        spec_path = self.tmp / "spec.json"
        spec_path.write_text(json.dumps(spec()), encoding="utf-8")
        rel = lambda p: p.relative_to(ROOT).as_posix()
        self.assertEqual(tm.main(["--spec", rel(spec_path), "--output", rel(self.tmp / "out"), "--root", str(ROOT)]), 2)


if __name__ == "__main__":
    unittest.main()
