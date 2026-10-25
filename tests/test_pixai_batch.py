"""PixAIの一括生成・変数・採用・組み立てを外部通信なしで検証する。"""

from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
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
sys.path.insert(0, str(ROOT / "templates" / "manga-project" / "scripts"))

import pixai_api as api
import pixai_batch as nb
import pixai_compose as compose
import pixai_edit as edit

KEY = "fixture-pixai-key"
PROMPT = "light brown short bob hair, yellow hoodie"


def request(text=PROMPT, **body):
    data = {"api": "v2", "body": {"modelVersionId": api.MODELS["tsubaki2"]["id"], "prompt": "1girl, solo, " + text, "aspectRatio": "2:3", "seed": 7}}
    data["body"].update(body)
    return data


class PixaiBatchTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "project.json").write_text("{}", encoding="utf-8")
        (self.root / "config").mkdir()
        (self.root / "config/page-layout.json").write_text(json.dumps({"generationCanvas": {"width": 832, "height": 1216}}), encoding="utf-8")
        (self.root / nb.REQUESTS_DIR).mkdir(parents=True)
        for rid in ("p01-01", "p01-02", "p02-01", "chara-mio"):
            self.save(rid, request())
        (self.root / ".env").write_text(f"PIXAI_API_KEY={KEY}\nNOVELAI_CHAR_MIO=\"novelai\"\n", encoding="utf-8")
        (self.root / ".env.pixai").write_text(f"PIXAI_CHAR_MIO=\"{PROMPT}\"\nPIXAI_LORA_MIO=\"1234567890123\"\n", encoding="utf-8")
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()

    def save(self, rid, data):
        (self.root / nb.REQUESTS_DIR / f"{rid}.json").write_text(json.dumps(data), encoding="utf-8")

    def gen_args(self, **extra):
        base = dict(page=None, ids=None, all=False, seed="auto", batch_size="auto", interval=0, max=30, timeout=5, execute=False, accept_warnings=False,
                    confirm_credits=False, allow_unverified=False, cost_note=None)
        base.update(extra)
        return Namespace(**base)

    def test_variables_only_from_env_pixai_and_lora_ids_expand(self):
        variables = nb.read_variables(self.root)
        self.assertEqual(set(variables), {"PIXAI_CHAR_MIO", "PIXAI_LORA_MIO"})
        self.assertEqual(variables["PIXAI_CHAR_MIO"], (PROMPT, ".env.pixai"))
        self.save("p01-01", request(text="${PIXAI_CHAR_MIO}", loras=[{"modelId": "${PIXAI_LORA_MIO}", "weight": 0.8}]))
        resolved, used = nb.resolved_request(self.root, "p01-01", variables)
        self.assertEqual(used, {"PIXAI_CHAR_MIO", "PIXAI_LORA_MIO"})
        self.assertEqual(resolved["body"]["loras"][0]["modelId"], "1234567890123")
        v1 = {"api": "v1", "parameters": {"prompts": "x", "lora": {"${PIXAI_LORA_MIO}": 0.5}}}
        self.assertEqual(nb.expand(v1, variables, set())["parameters"]["lora"], {"1234567890123": 0.5})
        for name in ("PIXAI_API_KEY", "NOVELAI_CHAR_MIO", "PIXAI_OTHER_X"):
            with self.subTest(name=name), self.assertRaises(nb.BatchError):
                nb.expand("${" + name + "}", variables, set())
        with patch.dict(os.environ, {"PIXAI_CHAR_MIO": "dup"}), self.assertRaises(nb.BatchError):
            nb.read_variables(self.root)

    def test_env_set_writes_only_env_pixai_and_validates_lora(self):
        self.assertEqual(nb.env_set(self.root, "PIXAI_STYLE_MAIN", "clean lineart, soft colors"), "追加")
        self.assertEqual(nb.env_set(self.root, "PIXAI_CHAR_MIO", "1girl, red hoodie"), "更新")
        self.assertEqual((self.root / ".env").read_text(encoding="utf-8"), f"PIXAI_API_KEY={KEY}\nNOVELAI_CHAR_MIO=\"novelai\"\n")
        for name, value in (("PIXAI_LORA_X", "not-an-id"), ("PIXAI_API_KEY", "x"), ("pixai_char_x", "x")):
            with self.subTest(name=name), self.assertRaises(nb.BatchError):
                nb.env_set(self.root, name, value)
        self.assertEqual(nb.templatize(self.root, "PIXAI_STYLE_MAIN", True), {})
        self.save("p01-02", request(text="clean lineart, soft colors"))
        self.assertEqual(nb.templatize(self.root, "PIXAI_STYLE_MAIN", False), {"p01-02": 1})
        self.assertIn("${PIXAI_STYLE_MAIN}", (self.root / nb.REQUESTS_DIR / "p01-02.json").read_text(encoding="utf-8"))

    def test_settings_reader_allowlist(self):
        (self.root / ".env.pixai").write_text('PIXAI_MODEL="haruka2"\n', encoding="utf-8")
        self.assertEqual(nb.read_setting(self.root, "PIXAI_MODEL"), "haruka2")
        self.assertIsNone(nb.read_setting(self.root, "PIXAI_QUALITY_TAGS"))
        with self.assertRaises(nb.BatchError):
            nb.read_setting(self.root, "PIXAI_API_KEY")

    def test_dry_run_and_missing_cost_never_read_key_or_send(self):
        out = StringIO()
        with redirect_stdout(out), patch.object(api, "load_key") as key, patch.object(api, "api_request") as network:
            nb.generate(self.root, self.gen_args(page=[1]))
            with self.assertRaises(api.ClientError):
                nb.generate(self.root, self.gen_args(page=[1], execute=True, cost_note="x"))
        key.assert_not_called()
        network.assert_not_called()
        self.assertIn("848×1280px", out.getvalue())
        self.assertNotIn("[1/2]", out.getvalue())  # 費用確認は１件目の前に全件で確かめる

    def test_prompt_lint_for_pixai_syntax(self):
        lint = lambda text, **body: nb.lint_prompt(request(text=text, **body))
        self.assertEqual(lint("standing, (smile:1.2), upper body"), [])
        self.assertTrue(any("角括弧" in w for w in lint("[smile], {blush}")))
        self.assertTrue(any("NovelAI形式" in w for w in lint("1.2::smile::")))
        self.assertTrue(any("否定語" in w for w in lint("not smiling")))
        self.assertTrue(any("2人" in w for w in nb.lint_prompt({"api": "v2", "body": {"prompt": "1girl, 1boy, side by side"}})))
        self.assertTrue(any("promptHelper" in w for w in lint("standing", promptHelper="enable")))

    def test_generate_numbers_batches_and_blocks_unknown(self):
        def fake(root, req, output, args, unverified, log=print):
            first = api.project_path(root, output)
            first.parent.mkdir(parents=True, exist_ok=True)
            paths = api.candidate_paths(first, api.batch_size(req))
            for path in paths:
                Image.new("RGB", (8, 8)).save(path)
            api.write_record(api.record_path_for(first), {"reservedOutputs": [api.Path(p).relative_to(root).as_posix() for p in paths]})
            return paths
        self.save("p01-01", request(batchSize=4))
        with redirect_stdout(StringIO()), patch.object(api, "execute_generation", side_effect=fake):
            nb.generate(self.root, self.gen_args(ids=["p01-01"], execute=True, confirm_credits=True, cost_note="許可"))
        self.assertEqual([p.name for p in nb.candidates(self.root, "p01-01")], ["r001.png", "r002.png", "r003.png", "r004.png"])
        self.assertEqual(nb.next_candidate(self.root, "p01-01"), 5)
        folder = self.root / nb.CANDIDATES_DIR / "p01-01"
        (folder / "r005.pixai.json").write_text(json.dumps({"taskId": "9", "reservedOutputs": []}), encoding="utf-8")
        with self.assertRaises(nb.BatchError) as raised:
            nb.next_candidate(self.root, "p01-01")
        self.assertIn("fetch", str(raised.exception))
        self.assertEqual(nb.move_unknown(self.root, ["p01-01"], None, False, ""), [("p01-01", 5, None)])
        nb.move_unknown(self.root, ["p01-01"], None, True, "PixAI側で画像なしを確認")
        self.assertEqual(nb.next_candidate(self.root, "p01-01"), 5)

    def test_partial_batch_is_fetchable_and_cannot_move_saved_image(self):
        folder = self.root / nb.CANDIDATES_DIR / "p01-01"
        folder.mkdir(parents=True)
        image = folder / "r001.png"
        Image.new("RGB", (8, 8)).save(image)
        record = folder / "r001.pixai.json"
        api.write_record(record, {"taskId": "9", "missingOutputs": ["r002.png: temporary failure"]})
        self.assertEqual(nb.unknown_records(self.root, "p01-01"), [record])
        with self.assertRaises(nb.BatchError):
            nb.next_candidate(self.root, "p01-01")
        with self.assertRaises(nb.BatchError):
            nb.move_unknown(self.root, ["p01-01"], 1, True, "checked")
        self.assertTrue(image.is_file())
        with patch.object(api, "fetch", return_value=[image]) as fetch, redirect_stdout(StringIO()):
            nb.fetch_unknown(self.root, ["p01-01"])
        fetch.assert_called_once()

    def test_adopt_and_build_lookup_use_pixai_records(self):
        folder = self.root / nb.CANDIDATES_DIR / "p01-02"
        folder.mkdir(parents=True)
        Image.new("RGB", (8, 8)).save(folder / "r002.png")
        nb.adopt(self.root, "p01-02", 2, None)
        data = json.loads((self.root / nb.ADOPTED).read_text(encoding="utf-8"))
        self.assertEqual(data["adopted"]["p01-02"]["path"], "output/pixai/candidates/p01-02/r002.png")
        with self.assertRaises(nb.BatchError):
            nb.adopt_latest(self.root, ["p01-01", "p01-02"], False)
        self.assertEqual(json.loads((self.root / nb.ADOPTED).read_text(encoding="utf-8")), data)

    def test_placement_matches_cover_fit(self):
        affine, notes = nb.placement([0, 0, 100, 200], (848, 1280), [0.5, 0.5], 1.0, 0)
        self.assertAlmostEqual(affine[0], 6.4)
        self.assertEqual(notes, [])

    def test_compose_builds_v2_and_v1_requests_without_network(self):
        Image.new("RGB", (32, 32)).save(self.root / "ref.png")
        with patch.object(compose, "__file__", str(self.root / "scripts/pixai_compose.py")), redirect_stdout(StringIO()):
            code = compose.main(["--id", "p03-01", "--char1-appearance", PROMPT, "--scene", "upper body", "--style-preset", "moe-pastel",
                                 "--lora", "${PIXAI_LORA_MIO}:0.7", "--seed", "3", "--no-check"])
        self.assertEqual(code, 0)
        body = json.loads((self.root / nb.REQUESTS_DIR / "p03-01.json").read_text(encoding="utf-8"))["body"]
        self.assertEqual(body["prompt"], f"1girl, solo, {PROMPT}, upper body, masterpiece, best quality")
        self.assertEqual((body["mode"], body["style"]["key"], body["aspectRatio"], body["promptHelper"]), ("standard", "moe-pastel", "2:3", "disable"))
        self.assertEqual(body["loras"], [{"modelId": "${PIXAI_LORA_MIO}", "weight": 0.7}])
        with patch.object(compose, "__file__", str(self.root / "scripts/pixai_compose.py")), redirect_stdout(StringIO()):
            compose.main(["--id", "p03-02", "--model", "haruka2", "--char1-appearance", "a", "--char2-type", "boy", "--char2-appearance", "b",
                          "--reference", "ref.png", "--adetailer", "--lora", "1234567:0.5:mio_tag", "--no-check"])
        params = json.loads((self.root / nb.REQUESTS_DIR / "p03-02.json").read_text(encoding="utf-8"))["parameters"]
        self.assertTrue(params["prompts"].startswith("1girl, 1boy, girl, a, boy, b, mio_tag"))
        self.assertEqual((params["width"], params["height"], params["lora"]), (848, 1280, {"1234567": 0.5}))
        self.assertNotIn("inferenceProfile", params)
        with patch.object(compose, "__file__", str(self.root / "scripts/pixai_compose.py")), redirect_stdout(StringIO()):
            self.assertEqual(compose.main(["--id", "p03-03", "--model", "haruka2", "--char1-appearance", "a", "--mode", "pro"]), 1)

    def test_compose_layout_negative_default_and_tsubaki3_mode(self):
        with patch.object(compose, "__file__", str(self.root / "scripts/pixai_compose.py")), redirect_stdout(StringIO()):
            code = compose.main(["--id", "p03-04", "--model", "tsubaki3", "--layout", "girl on the right, boy on the left",
                                 "--char1-appearance", "a", "--char2-type", "boy", "--char2-appearance", "b", "--no-check"])
        self.assertEqual(code, 0)
        data = json.loads((self.root / nb.REQUESTS_DIR / "p03-04.json").read_text(encoding="utf-8"))
        body = data["body"]
        self.assertTrue(body["prompt"].startswith("1girl, 1boy, girl on the right, boy on the left, girl, a, boy, b"))
        self.assertEqual((body["mode"], body["negativePrompt"]), ("pro", compose.DEFAULT_NEGATIVE))
        self.assertEqual(body["batchSize"], 4)  # ２人以上のコマは4枚から選ぶ
        self.assertFalse(any("2人" in w for w in nb.lint_prompt(data)))
        with patch.object(compose, "__file__", str(self.root / "scripts/pixai_compose.py")), redirect_stdout(StringIO()):
            compose.main(["--id", "p03-05", "--char1-appearance", "a", "--negative-base", "", "--no-check"])
        body = json.loads((self.root / nb.REQUESTS_DIR / "p03-05.json").read_text(encoding="utf-8"))["body"]
        self.assertNotIn("negativePrompt", body)
        self.assertEqual(body["batchSize"], 1)
        with patch.object(compose, "__file__", str(self.root / "scripts/pixai_compose.py")), redirect_stdout(StringIO()):
            compose.main(["--id", "p03-06", "--model", "haruka2", "--char1-appearance", "a", "--adetailer", "--no-check"])
        self.assertNotIn("negativePrompts", json.loads((self.root / nb.REQUESTS_DIR / "p03-06.json").read_text(encoding="utf-8"))["parameters"])

    def test_batch_size_defaults_for_rework_and_inpaint(self):
        folder = self.root / nb.CANDIDATES_DIR / "p01-01"
        folder.mkdir(parents=True)
        Image.new("RGB", (848, 1280)).save(folder / "r001.png")
        sent = []
        fake = lambda root, req, output, args, unverified, log=print: sent.append(api.batch_size(req)) or []
        with redirect_stdout(StringIO()), patch.object(api, "execute_generation", side_effect=fake):
            nb.generate(self.root, self.gen_args(ids=["p01-01", "p01-02"], execute=True, confirm_credits=True, cost_note="許可"))
            nb.generate(self.root, self.gen_args(ids=["p01-01"], batch_size="1", execute=True, confirm_credits=True, cost_note="許可"))
        self.assertEqual(sent, [4, 1, 1])  # 作り直しは4枚、初回は要求のまま、指定があれば指定どおり
        Image.new("L", (848, 1280)).save(self.root / "mask.png")
        with patch.object(compose, "__file__", str(self.root / "scripts/pixai_compose.py")), redirect_stdout(StringIO()):
            code = compose.main(["--id", "p01-01b", "--model", "tsubaki3", "--char1-appearance", "a", "--i2i", "output/pixai/candidates/p01-01/r001.png",
                                 "--mask", "mask.png", "--strength", "0.75", "--no-check"])
        self.assertEqual(code, 0)
        params = json.loads((self.root / nb.REQUESTS_DIR / "p01-01b.json").read_text(encoding="utf-8"))["parameters"]
        self.assertEqual((params["maskMediaFile"], params["width"], params["height"], params["batchSize"]), ("mask.png", 848, 1280, 4))
        Image.new("L", (100, 100)).save(self.root / "small.png")
        with patch.object(compose, "__file__", str(self.root / "scripts/pixai_compose.py")), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(compose.main(["--id", "p01-01c", "--char1-appearance", "a", "--i2i", "output/pixai/candidates/p01-01/r001.png",
                                           "--mask", "small.png", "--no-check"]), 1)  # マスクと元画像の寸法が違う

    def test_edit_inherits_request_and_switches_model_for_inpaint(self):
        self.save("p01-01", request(style={"type": "preset", "key": "flat-anime-pastel"}, negativePrompt="text, halo"))
        folder = self.root / nb.CANDIDATES_DIR / "p01-01"
        folder.mkdir(parents=True)
        Image.new("RGB", (848, 1280)).save(folder / "r001.png")
        run = lambda *args: edit.main(list(args))
        with patch.object(edit, "__file__", str(self.root / "scripts/pixai_edit.py")), redirect_stdout(StringIO()):
            self.assertEqual(run("inpaint", "p01-01", "--add", "girl wearing a red beret", "--ellipse", "300,40,260,180", "--negative", "halo"), 0)
            self.assertEqual(run("i2i", "p01-01", "--add", "snow", "--no-style", "--batch-size", "1"), 0)
        params = json.loads((self.root / nb.REQUESTS_DIR / "p01-01b.json").read_text(encoding="utf-8"))["parameters"]
        self.assertTrue(params["prompts"].startswith("girl wearing a red beret, 1girl, solo, "))
        self.assertEqual((params["modelId"], params["inferenceProfile"], params["batchSize"], params["seed"]),
                         (api.MODELS["tsubaki3"]["id"], "pro", 4, 7))  # Tsubaki.2 はインペイント非対応なので Tsubaki.3 で直す
        self.assertEqual((params["width"], params["height"], params["negativePrompts"]), (848, 1280, "text, halo"))
        self.assertEqual(params["modelStyle"], {"type": "key", "keyId": "flat-anime-pastel"})
        self.assertTrue((self.root / params["maskMediaFile"]).is_file())
        params = json.loads((self.root / nb.REQUESTS_DIR / "p01-01c.json").read_text(encoding="utf-8"))["parameters"]
        self.assertEqual((params["modelId"], params["batchSize"], params["strength"]), (api.MODELS["tsubaki2"]["id"], 1, 0.6))
        self.assertNotIn("modelStyle", params)
        self.assertNotIn("maskMediaFile", params)

    def test_edit_refusal_preserves_existing_mask_and_request(self):
        folder = self.root / nb.CANDIDATES_DIR / "p01-01"
        folder.mkdir(parents=True)
        Image.new("RGB", (848, 1280)).save(folder / "r001.png")
        with patch.object(edit, "__file__", str(self.root / "scripts/pixai_edit.py")), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            args = ["inpaint", "p01-01", "--id", "p01-01b", "--add", "red hat", "--ellipse", "300,40,260,180"]
            self.assertEqual(edit.main(args), 0)
            paths = [self.root / nb.REQUESTS_DIR / "p01-01b.json", self.root / "input/pixai/masks/p01-01b.png",
                     self.root / "input/pixai/masks/p01-01b.preview.png"]
            before = [p.read_bytes() for p in paths]
            self.assertEqual(edit.main(args[:-1] + ["0,0,50,50"]), 1)
            self.assertEqual([p.read_bytes() for p in paths], before)

    def test_edit_rejects_path_ids_before_writing(self):
        with patch.object(edit, "__file__", str(self.root / "scripts/pixai_edit.py")), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            for source_id, target_id in [("../p01-01", "p01-01b"), ("p01-01", "../../outside")]:
                with self.subTest(source_id=source_id, target_id=target_id), patch.object(edit.mask_tool, "make_mask") as mask:
                    self.assertEqual(edit.main(["inpaint", source_id, "--id", target_id, "--add", "hat", "--ellipse", "0,0,50,50"]), 1)
                    mask.assert_not_called()

    def test_edit_preserves_and_validates_prompt_and_lora_variables(self):
        self.save("p01-01", request("${PIXAI_CHAR_MIO}", loras=[{"modelId": "${PIXAI_LORA_MIO}", "weight": 0.8}]))
        folder = self.root / nb.CANDIDATES_DIR / "p01-01"
        folder.mkdir(parents=True)
        Image.new("RGB", (848, 1280)).save(folder / "r001.png")
        with patch.object(edit, "__file__", str(self.root / "scripts/pixai_edit.py")), redirect_stdout(StringIO()):
            self.assertEqual(edit.main(["inpaint", "p01-01", "--add", "red hat", "--ellipse", "300,40,260,180"]), 0)
        saved = json.loads((self.root / nb.REQUESTS_DIR / "p01-01b.json").read_text(encoding="utf-8"))
        self.assertIn("${PIXAI_CHAR_MIO}", saved["parameters"]["prompts"])
        self.assertEqual(saved["parameters"]["lora"], {"${PIXAI_LORA_MIO}": 0.8})
        resolved, _ = nb.resolved_request(self.root, "p01-01b", nb.read_variables(self.root))
        api.prepare_request_data(self.root, resolved)

    def test_body_part_lint_accepts_crowd_count_tags(self):
        self.assertFalse(any("体の部分" in w for w in nb.lint_prompt({"api": "v2", "body": {"prompt": "multiple girls, multiple boys, hands up"}})))
        self.assertTrue(any("体の部分" in w for w in nb.lint_prompt({"api": "v2", "body": {"prompt": "hands focus, close-up"}})))


if __name__ == "__main__":
    unittest.main()
