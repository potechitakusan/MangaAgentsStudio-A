"""NovelAIの一括生成・採用・組み直しを外部通信なしで検証する。"""

from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "manga-project"
sys.path.insert(0, str(TEMPLATE / "scripts"))

import novelai_api as api
import novelai_batch as nb

KEY = "fixture-secret-token"
PROMPT = "1girl, light brown short bob hair, yellow hoodie"


def request(width=1216, height=832, text=PROMPT):
    return {"action": "generate", "model": "nai-diffusion-4-5-full", "input": "rooftop, " + text,
            "parameters": {"seed": 7, "sampler": "k_euler_ancestral", "scale": 5, "width": width, "height": height}}


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "project.json").write_text("{}", encoding="utf-8")
        (self.root / "config").mkdir()
        (self.root / "config/page-layout.json").write_text(json.dumps({"generationCanvas": {"width": 832, "height": 1216}}), encoding="utf-8")
        (self.root / nb.REQUESTS_DIR).mkdir(parents=True)
        for rid in ("p01-01", "p01-02", "p02-01", "chara-mio"):
            self.save(rid, request())
        (self.root / ".env").write_text(f"NOVELAI_API_KEY={KEY}\nNOVELAI_CHAR_MIO=\"{PROMPT}\"\n", encoding="utf-8")
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()

    def save(self, rid, data):
        (self.root / nb.REQUESTS_DIR / f"{rid}.json").write_text(json.dumps(data), encoding="utf-8")

    def gen_args(self, **extra):
        base = dict(page=None, ids=None, all=False, seed="auto", interval=0, max=30, execute=False, accept_warnings=False,
                    confirm_zero_anlas=False, allow_anlas=False, confirm_v5_allowance=False, cost_note=None)
        base.update(extra)
        return Namespace(**base)

    def test_select_by_page_ids_all(self):
        self.assertEqual(nb.select_ids(self.root, [1], None, False), ["p01-01", "p01-02"])
        self.assertEqual(nb.select_ids(self.root, None, None, True), ["p01-01", "p01-02", "p02-01"])
        self.assertEqual(nb.select_ids(self.root, None, ["chara-mio"], False), ["chara-mio"])
        with self.assertRaises(nb.BatchError):
            nb.select_ids(self.root, None, ["p09-01"], False)

    def test_variables_never_include_api_key(self):
        variables = nb.read_variables(self.root)
        self.assertEqual(set(variables), {"NOVELAI_CHAR_MIO"})
        self.assertEqual(variables["NOVELAI_CHAR_MIO"], (PROMPT, ".env"))
        with self.assertRaises(nb.BatchError):
            nb.expand("${NOVELAI_API_KEY}", variables, set())
        with self.assertRaises(nb.BatchError):
            nb.expand("${NOVELAI_CHAR_UNKNOWN}", variables, set())

    def test_duplicate_variable_is_rejected(self):
        (self.root / ".secrets").mkdir()
        (self.root / ".secrets/novelai.env").write_text("NOVELAI_CHAR_MIO=other\n", encoding="utf-8")
        with self.assertRaises(nb.BatchError):
            nb.read_variables(self.root)

    def test_style_and_background_round_trip_keeps_key_and_resolves_nested_prompts(self):
        nb.env_set(self.root, "NOVELAI_STYLE_MAIN", "bold lineart, vivid colors")
        nb.env_set(self.root, "NOVELAI_BACKGROUND_CLASSROOM", "教室、窓から夕方の光")
        data = request(text="${NOVELAI_CHAR_MIO}, ${NOVELAI_BACKGROUND_CLASSROOM}, ${NOVELAI_STYLE_MAIN}")
        data["parameters"]["v4_prompt"] = {
            "caption": {"base_caption": data["input"], "char_captions": [
                {"char_caption": "${NOVELAI_CHAR_MIO}", "centers": [{"x": 0.3, "y": 0.5}]}]},
            "use_coords": True, "use_order": True}
        self.save("p01-01", data)
        variables = nb.read_variables(self.root)
        resolved, used = nb.resolved_request(self.root, "p01-01", variables)
        self.assertEqual(used, {"NOVELAI_CHAR_MIO", "NOVELAI_STYLE_MAIN", "NOVELAI_BACKGROUND_CLASSROOM"})
        self.assertIn("教室、窓から夕方の光", resolved["input"])
        self.assertEqual(resolved["input"], resolved["parameters"]["v4_prompt"]["caption"]["base_caption"])
        character = resolved["parameters"]["v4_prompt"]["caption"]["char_captions"][0]
        self.assertEqual(character, {"char_caption": PROMPT, "centers": [{"x": 0.3, "y": 0.5}]})
        self.assertIn(f"NOVELAI_API_KEY={KEY}", (self.root / ".env").read_text(encoding="utf-8"))
        self.assertNotIn(KEY, json.dumps(resolved))
        out = StringIO()
        with redirect_stdout(out), patch.object(api, "load_key") as key, patch.object(api, "api_request") as network:
            nb.generate(self.root, self.gen_args(ids=["p01-01"]))
        key.assert_not_called()
        network.assert_not_called()
        self.assertNotIn(KEY, out.getvalue())

    def test_new_variable_types_templatize_and_reject_duplicate_sources(self):
        for name, value in (("NOVELAI_STYLE_MAIN", "soft colors, clean lineart"),
                            ("NOVELAI_BACKGROUND_CLASSROOM", "classroom, windows, daylight")):
            with self.subTest(name=name):
                nb.env_set(self.root, name, value)
                self.save("p01-01", request(text=value))
                self.assertEqual(nb.templatize(self.root, name, True), {"p01-01": 1})
                nb.templatize(self.root, name, False)
                resolved, used = nb.resolved_request(self.root, "p01-01", nb.read_variables(self.root))
                self.assertIn(value, resolved["input"])
                self.assertEqual(used, {name})
                with patch.dict(os.environ, {name: "duplicate"}):
                    with self.assertRaises(nb.BatchError):
                        nb.read_variables(self.root)

    def test_prompt_variable_allowlist_rejects_keys_and_unrelated_settings(self):
        for name in ("NOVELAI_API_KEY", "COMFYUI_URL", "NOVELAI_OTHER_MAIN", "NOVELAI_STYLE_", "NOVELAI_BACKGROUND_classroom"):
            with self.subTest(name=name):
                with self.assertRaises(nb.BatchError):
                    nb.env_set(self.root, name, "some prompt")
                with self.assertRaises(nb.BatchError):
                    nb.expand("${" + name + "}", nb.read_variables(self.root), set())

    def test_env_set_keeps_other_lines_and_templatize(self):
        self.assertEqual(nb.templatize(self.root, "NOVELAI_CHAR_MIO", True), {r: 1 for r in ("chara-mio", "p01-01", "p01-02", "p02-01")})
        nb.templatize(self.root, "NOVELAI_CHAR_MIO", False)
        self.assertIn("${NOVELAI_CHAR_MIO}", (self.root / nb.REQUESTS_DIR / "p01-01.json").read_text(encoding="utf-8"))
        self.assertEqual(nb.env_set(self.root, "NOVELAI_CHAR_MIO", "1girl, red hoodie"), "更新")
        self.assertEqual(nb.env_set(self.root, "NOVELAI_CHAR_REN", "1boy, glasses"), "追加")
        text = (self.root / ".env").read_text(encoding="utf-8")
        self.assertIn(f"NOVELAI_API_KEY={KEY}", text)
        resolved, used = nb.resolved_request(self.root, "p01-01", nb.read_variables(self.root))
        self.assertIn("red hoodie", resolved["input"])
        self.assertEqual(used, {"NOVELAI_CHAR_MIO"})
        for bad in ("NOVELAI_API_KEY", "novelai_char_x"):
            with self.assertRaises(nb.BatchError):
                nb.env_set(self.root, bad, "x")

    def test_panel_size_differs_from_page_canvas(self):
        prepared, _ = api.prepare_request_data(self.root, request(1216, 832))
        self.assertEqual((prepared["parameters"]["width"], prepared["parameters"]["height"]), (1216, 832))

    def test_dry_run_and_missing_cost_never_read_key_or_send(self):
        out = StringIO()
        with redirect_stdout(out), patch.object(api, "load_key") as key, patch.object(api, "api_request") as network:
            nb.generate(self.root, self.gen_args(page=[1]))
            with self.assertRaises(nb.BatchError):
                nb.generate(self.root, self.gen_args(page=[1], execute=True))
        key.assert_not_called()
        network.assert_not_called()
        self.assertIn("seed 7", out.getvalue())
        self.assertNotIn(KEY, out.getvalue())

    def test_seed_changes_after_first_candidate(self):
        folder = self.root / nb.CANDIDATES_DIR / "p01-01"
        folder.mkdir(parents=True)
        Image.new("RGB", (8, 8)).save(folder / "r001.png")
        out = StringIO()
        with redirect_stdout(out), patch.object(nb.secrets, "randbelow", return_value=12345):
            nb.generate(self.root, self.gen_args(ids=["p01-01"]))
        self.assertIn("seed 12345", out.getvalue())
        self.assertIn("r002.png", out.getvalue())

    def test_unknown_result_record_blocks_regeneration(self):
        folder = self.root / nb.CANDIDATES_DIR / "p01-01"
        folder.mkdir(parents=True)
        (folder / "r001.novelai.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(nb.BatchError):
            nb.next_candidate(self.root, "p01-01")

    def test_generate_stops_at_first_failure(self):
        calls = []

        def fake(root, req, payload, output, args):
            calls.append(output)
            raise api.ClientError("送信失敗")
        with redirect_stdout(StringIO()), patch.object(api, "execute_generation", side_effect=fake):
            with self.assertRaises(nb.BatchError):
                nb.generate(self.root, self.gen_args(page=[1], execute=True, confirm_zero_anlas=True, cost_note="確認"))
        self.assertEqual(len(calls), 1)

    def test_prompt_lint(self):
        lint = lambda text: nb.lint_prompt({"input": text, "parameters": {}})
        self.assertEqual(lint("1girl, solo, sitting on the floor, knees up, upper body, school rooftop"), [])
        self.assertTrue(any("否定語" in w for w in lint("1girl, solo, not smiling")))
        self.assertTrue(any("否定語" in w for w in lint("courtyard, no people")))
        self.assertEqual(lint("no humans, courtyard, paper airplane, small in frame"), [])
        self.assertTrue(any("意図" in w for w in lint("1girl, solo, about to sigh")))
        self.assertTrue(any("誰の体" in w for w in lint("close-up, dark school shoes, paper airplane")))
        self.assertTrue(any("2人" in w for w in lint("1girl, 1boy, sitting side by side, 1girl, short hair, 1boy, glasses")))
        for text in ("1girl, solo, 25 years old", "1boy, solo, 40yo", "1boy, solo, aged 30", "1girl, solo, 17歳", "1boy, solo, young man"):
            self.assertTrue(any("数値の年齢" in w for w in lint(text)), text)
        # 年代・立場の語は使ってよい
        for text in ("1boy, solo, teenage boy, glasses", "1girl, solo, high school student", "1girl, solo, adult, office"):
            self.assertFalse(any("数値の年齢" in w for w in lint(text)), text)

    def test_identity_features_per_request(self):
        characters = {"characters": {"mio": {"features": {"hair": "light brown short bob hair", "outer": "yellow hoodie over navy blazer"}}},
                      "cast": {"p01-01": {"mio": "all"}, "p01-02": {"mio": ["outer"]}}}
        full = {"input": "1girl, solo, light brown short bob hair, yellow hoodie over navy blazer", "parameters": {}}
        self.assertEqual(nb.lint_identity("p01-01", full, characters), [])
        missing = {"input": "1girl, solo, blonde hair, yellow hoodie over navy blazer", "parameters": {}}
        self.assertTrue(any("hair" in w for w in nb.lint_identity("p01-01", missing, characters)))
        # 手元のアップなど、見える特徴だけを対象にできる
        self.assertEqual(nb.lint_identity("p01-02", {"input": "1girl, hands only, yellow hoodie over navy blazer", "parameters": {}}, characters), [])
        # cast にない人物入りの要求は登録を促し、人物なしは点検しない
        self.assertTrue(nb.lint_identity("p09-01", {"input": "1boy, solo", "parameters": {}}, characters))
        self.assertEqual(nb.lint_identity("p09-02", {"input": "no humans, sky", "parameters": {}}, characters), [])
        self.assertEqual(nb.lint_identity("p01-01", missing, None), [])

    def test_identity_check_is_off_unless_enabled_and_no_text_is_not_a_negation(self):
        characters = {"characters": {"mio": {"features": {"hair": "light brown short bob hair"}}},
                      "cast": {"p01-01": {"mio": "all"}}}
        (self.root / "input/novelai").mkdir(parents=True, exist_ok=True)
        (self.root / nb.CHARACTERS).write_text(json.dumps(characters), encoding="utf-8")
        self.save("p01-01", request(text="1girl, short black hair, very aesthetic, masterpiece, no text"))
        self.assertEqual(nb.lint_prompt(request(text="1girl, masterpiece, no text")), [])
        out = StringIO()
        with redirect_stdout(out):
            nb.generate(self.root, self.gen_args(ids=["p01-01"]))
        self.assertNotIn("識別特徴", out.getvalue())
        with (self.root / ".env").open("a", encoding="utf-8") as stream:
            stream.write("NOVELAI_CHECK_IDENTITY=1\n")
        out = StringIO()
        with redirect_stdout(out):
            nb.generate(self.root, self.gen_args(ids=["p01-01"]))
        self.assertIn("識別特徴の点検: 有効", out.getvalue())
        self.assertIn("識別特徴が抜けている", out.getvalue())

    def test_setting_reader_only_reads_allowed_names(self):
        (self.root / ".env").write_text(f'NOVELAI_API_KEY={KEY}\nNOVELAI_UC_PRESET="light"\n', encoding="utf-8")
        self.assertEqual(nb.read_setting(self.root, "NOVELAI_UC_PRESET"), "light")
        self.assertIsNone(nb.read_setting(self.root, "NOVELAI_QUALITY_TAGS"))
        with patch.dict(os.environ, {"NOVELAI_QUALITY_TAGS": "masterpiece"}):
            self.assertEqual(nb.read_setting(self.root, "NOVELAI_QUALITY_TAGS"), "masterpiece")
        with self.assertRaises(nb.BatchError):
            nb.read_setting(self.root, "NOVELAI_API_KEY")

    def test_warnings_block_sending_until_accepted(self):
        self.save("p01-01", request(text="1girl, solo, not smiling"))
        with redirect_stdout(StringIO()), patch.object(api, "execute_generation") as send:
            with self.assertRaises(nb.BatchError):
                nb.generate(self.root, self.gen_args(ids=["p01-01"], execute=True, confirm_zero_anlas=True, cost_note="確認"))
            send.assert_not_called()
            nb.generate(self.root, self.gen_args(ids=["p01-01"], execute=True, confirm_zero_anlas=True, cost_note="確認",
                                                 accept_warnings=True))
            send.assert_called_once()

    def test_same_camera_three_times_is_warned(self):
        for rid in ("p01-01", "p01-02", "p01-03"):
            self.save(rid, request(text="1girl, solo, from below, face"))
        out = StringIO()
        with redirect_stdout(out):
            nb.generate(self.root, self.gen_args(page=[1]))
        self.assertIn("同じ画角（from below）が３コマ続く", out.getvalue())

    def test_camera_check_uses_whole_page_when_regenerating_some(self):
        for rid, camera in (("p01-01", "from below"), ("p01-02", "from above"), ("p01-03", "from below"), ("p01-04", "from below")):
            self.save(rid, request(text=f"1girl, solo, {camera}, face"))
        out = StringIO()
        with redirect_stdout(out):
            nb.generate(self.root, self.gen_args(ids=["p01-01", "p01-03", "p01-04"]))
        self.assertNotIn("３コマ続く", out.getvalue())

    def test_adopt_records_hash(self):
        folder = self.root / nb.CANDIDATES_DIR / "p01-02"
        folder.mkdir(parents=True)
        Image.new("RGB", (8, 8)).save(folder / "r002.png")
        nb.adopt(self.root, "p01-02", 2, None)
        data = json.loads((self.root / nb.ADOPTED).read_text(encoding="utf-8"))
        self.assertEqual(data["adopted"]["p01-02"]["path"], "output/novelai/candidates/p01-02/r002.png")
        with self.assertRaises(nb.BatchError):
            nb.adopt(self.root, "p01-02", 9, None)

    def test_adopt_latest_selects_numbers_and_preserves_other_adoptions(self):
        for rid, numbers in (("p01-01", (3, 999, 1000)), ("p01-02", (2, 5))):
            folder = self.root / nb.CANDIDATES_DIR / rid
            folder.mkdir(parents=True)
            for number in numbers:
                Image.new("RGB", (8, 8)).save(folder / f"r{number:03d}.png")
            (folder / "r9999.png").mkdir()  # ディレクトリは候補にしない
            (folder / "edited.png").write_bytes(b"not a candidate")
        other = {"path": "other.png", "sha256": "existing", "adopted_at": "previous"}
        nb.write_json(self.root / nb.ADOPTED, {"schema_version": 1, "adopted": {"p02-01": other}})
        chosen = nb.adopt_latest(self.root, nb.select_ids(self.root, [1], None, False), False)
        self.assertEqual(chosen["p01-01"].name, "r1000.png")
        self.assertEqual(chosen["p01-02"].name, "r005.png")
        saved = nb.load_adopted(self.root)["adopted"]
        self.assertEqual(saved["p02-01"], other)
        self.assertEqual(saved["p01-01"]["sha256"], nb.sha(chosen["p01-01"]))
        self.assertEqual(nb.next_candidate(self.root, "p01-01"), 1001)
        (chosen["p01-01"].parent / "r1001.novelai.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(nb.BatchError):
            nb.next_candidate(self.root, "p01-01")

    def test_adopt_latest_dry_run_and_missing_candidate_leave_record_unchanged(self):
        folder = self.root / nb.CANDIDATES_DIR / "p01-01"
        folder.mkdir(parents=True)
        Image.new("RGB", (8, 8)).save(folder / "r003.png")
        path = self.root / nb.ADOPTED
        chosen = nb.adopt_latest(self.root, ["p01-01"], True)
        self.assertEqual(chosen["p01-01"].name, "r003.png")
        self.assertFalse(path.exists())
        nb.write_json(path, {"schema_version": 1, "adopted": {"p01-01": {"path": "previous.png"}}})
        before = path.read_bytes()
        nb.adopt_latest(self.root, ["p01-01"], True)
        self.assertEqual(path.read_bytes(), before)
        for dry_run in (False, True):
            with self.assertRaises(nb.BatchError):
                nb.adopt_latest(self.root, ["p01-01", "p01-02"], dry_run)
            self.assertEqual(path.read_bytes(), before)

    def test_placement_centers_focus_and_reports_clamp(self):
        affine, notes = nb.placement([0, 0, 400, 300], (800, 600), [0.5, 0.5], 1.0, 0)
        a, b, c, d, e, f = affine
        self.assertAlmostEqual(a * 200 + b * 150 + c, 400)
        self.assertAlmostEqual(d * 200 + e * 150 + f, 300)
        self.assertEqual(notes, [])
        # 画像がコマにちょうど収まる方向（ここでは横・縦とも）は動かせないため注記しない。
        _, notes = nb.placement([0, 0, 400, 300], (800, 600), [0.0, 0.5], 1.0, 0)
        self.assertEqual(notes, [])
        # 横に余裕がある画像で左端を越えた場合だけ注記する。
        _, notes = nb.placement([0, 0, 400, 300], (1200, 600), [0.0, 0.5], 1.0, 0)
        self.assertTrue(notes)


class BuildTests(unittest.TestCase):
    def setUp(self):
        try:
            import typeset_manga
            typeset_manga.Fonts(ROOT, None)
        except FileNotFoundError:
            self.skipTest("日本語フォントがない環境")
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "project.json").write_text("{}", encoding="utf-8")
        panels = [{"id": "panel-01", "order": 1, "polygon": [[60, 60], [940, 60], [940, 700], [60, 700]]},
                  {"id": "panel-02", "order": 2, "polygon": [[60, 730], [940, 730], [940, 1440], [60, 1440]]}]
        layout = {"dimensions": {"working": {"width": 1000, "height": 1500}},
                  "page": {"frameStroke": 5, "textSafeArea": {"left": 80, "top": 80, "right": 80, "bottom": 80}},
                  "template": {"panels": panels}}
        (self.root / "output/layout").mkdir(parents=True)
        (self.root / "output/layout/layout.json").write_text(json.dumps(layout), encoding="utf-8")
        folder = self.root / nb.CANDIDATES_DIR / "p01-01"
        folder.mkdir(parents=True)
        Image.new("RGB", (1216, 832), "#88aacc").save(folder / "r001.png")
        (self.root / nb.REQUESTS_DIR).mkdir(parents=True)
        (self.root / nb.REQUESTS_DIR / "p01-01.json").write_text(json.dumps(request()), encoding="utf-8")
        (self.root / nb.PAGES_DIR).mkdir(parents=True)
        (self.root / nb.PAGES_DIR / "page-01.json").write_text(json.dumps({
            "schema_version": 1, "layout": "output/layout/layout.json",
            "panels": [{"panel": 1, "request": "p01-01", "focus": [0.5, 0.5]}, {"panel": 2}]}), encoding="utf-8")

    def test_build_requires_adoption_then_writes_versioned_png(self):
        with redirect_stdout(StringIO()):
            with self.assertRaises(nb.BatchError):
                nb.build(self.root, 1, False)
            self.assertFalse((self.root / nb.BUILD_DIR).exists())
            nb.adopt(self.root, "p01-01", 1, None)
            first = nb.build(self.root, 1, False)
            second = nb.build(self.root, 1, False)
        self.assertEqual((first.name, second.name), ("v001", "v002"))
        with Image.open(first / "page-01.png") as page:
            self.assertEqual(page.size, (1000, 1500))
            self.assertEqual(page.getpixel((10, 10))[:3], (255, 255, 255))  # コマ外は白
            self.assertNotEqual(page.getpixel((500, 400))[:3], (255, 255, 255))  # 採用画像が見える
        # 確認用の縮小画像は、原画を合成した完成ページから作る
        with Image.open(first / "page-01-display.png") as display:
            self.assertEqual(display.size, (720, 1080))
            self.assertNotEqual(display.getpixel((360, 300))[:3], (255, 255, 255))
        self.assertTrue((first / "page-01-check-overlay.png").is_file())
        record = json.loads((first / "build.json").read_text(encoding="utf-8"))
        self.assertEqual(record["review_display"], f"{nb.BUILD_DIR}/page-01/v001/page-01-display.png")
        self.assertEqual(record["panels"][0]["source"], "output/novelai/candidates/p01-01/r001.png")
        self.assertIsNone(record["psd"])

    def test_changed_adopted_image_is_rejected(self):
        with redirect_stdout(StringIO()):
            nb.adopt(self.root, "p01-01", 1, None)
            Image.new("RGB", (1216, 832), "#000000").save(self.root / nb.CANDIDATES_DIR / "p01-01" / "r001.png")
            with self.assertRaises(nb.BatchError):
                nb.build(self.root, 1, False)


if __name__ == "__main__":
    unittest.main()
