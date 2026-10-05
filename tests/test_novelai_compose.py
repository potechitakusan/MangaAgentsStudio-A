"""novelai_compose.py の要求の組み立てを外部通信なしで検証する。"""

from argparse import Namespace
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "templates" / "manga-project" / "scripts"))

import novelai_api as api
import novelai_batch as batch
import novelai_compose as nc

CHARS = [{"appearance": "black twintails", "action": "smile", "pos": "0.3,0.5"},
         {"appearance": "short blue hair", "action": "looking aside", "pos": "0.7,0.5"}]


def options(argv):
    return nc.parse_args(argv).parse_args(argv)


class ComposeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "config").mkdir()
        (self.root / "config/page-layout.json").write_text(json.dumps({"generationCanvas": None}), encoding="utf-8")
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()

    def build(self, extra=(), chars=CHARS, model=None):
        argv = ["--id", "p01-01", "--scene", "upper body", "--style", "bold lineart", "--seed", "5", *extra]
        if model:
            argv += ["--model", model]
        opts = options(argv)
        profile = nc.MODELS[opts.model]
        quality, _ = nc.resolve_quality(self.root, opts, profile)
        uc, _ = nc.resolve_uc(self.root, opts, profile)
        nc.resolve_size(self.root, opts)
        return nc.compose(opts, [dict(c) for c in chars], quality, uc)

    def test_default_model_is_v5_curated_and_v45_needs_explicit_model(self):
        request, _ = self.build()
        self.assertEqual(request["model"], "nai-diffusion-5-curated")
        self.assertEqual(request["parameters"]["steps"], 23)
        request45, _ = self.build(model="nai-diffusion-4-5-curated")
        self.assertEqual(request45["parameters"]["steps"], 28)
        with self.assertRaises(SystemExit), patch("sys.stderr"):
            options(["--id", "p01-01", "--model", "nai-diffusion-4-full"])

    def test_prompt_order_character_captions_and_quality_tags(self):
        request, _ = self.build()
        self.assertEqual(request["input"], "2girls, upper body, bold lineart, very aesthetic, masterpiece, no text")
        captions = request["parameters"]["v4_prompt"]["caption"]["char_captions"]
        self.assertEqual(captions[0]["char_caption"], "girl, black twintails, smile")
        self.assertTrue(request["parameters"]["v4_prompt"]["use_coords"])
        self.assertEqual(captions[1]["centers"], [{"x": 0.7, "y": 0.5}])
        text, added, skipped = nc.merge_quality(nc.MODELS[nc.DEFAULT_MODEL]["quality"], ["masterpiece, upper body"], False)
        self.assertEqual(skipped, ["masterpiece"])
        self.assertNotIn("masterpiece", text)
        self.assertEqual(added, ["very aesthetic", "no text"])

    def test_pins_are_all_or_nothing_and_unpinned_centers_are_still_sent(self):
        with self.assertRaises(nc.ComposeError):
            self.build(chars=[CHARS[0], {"appearance": "short blue hair"}])
        request, _ = self.build(chars=[{"appearance": "girl, a"}, {"appearance": "girl, b"}])
        prompt = request["parameters"]["v4_prompt"]
        self.assertFalse(prompt["use_coords"])
        self.assertEqual(prompt["caption"]["char_captions"][0]["centers"], [{"x": 0.5, "y": 0.5}])
        request, _ = self.build(("--coords", "off"))
        prompt = request["parameters"]["v4_prompt"]
        self.assertFalse(prompt["use_coords"])
        self.assertEqual(prompt["caption"]["char_captions"][0]["centers"], [{"x": 0.3, "y": 0.5}])

    def test_v45_snaps_pins_to_grid_and_limits_characters(self):
        request, _ = self.build(model="nai-diffusion-4-5-curated")
        centers = request["parameters"]["v4_prompt"]["caption"]["char_captions"][0]["centers"][0]
        self.assertEqual((centers["x"], centers["y"]), (0.3, 0.5))
        self.assertEqual(nc.snap(0.35, 5), 0.3)
        with self.assertRaises(nc.ComposeError):
            self.build(chars=[{"appearance": "girl, a"}] * 7, model="nai-diffusion-4-5-curated")

    def test_variables_are_rejected_and_size_follows_page_layout(self):
        with self.assertRaises(nc.ComposeError):
            self.build(("--background", "${NOVELAI_BACKGROUND_X}"))
        opts = options(["--id", "p01-01"])
        nc.resolve_size(self.root, opts)
        self.assertEqual((opts.width, opts.height), (832, 1216))
        (self.root / "config/page-layout.json").write_text(
            json.dumps({"generationCanvas": {"width": 1024, "height": 1024}}), encoding="utf-8")
        opts = options(["--id", "p01-01"])
        nc.resolve_size(self.root, opts)
        self.assertEqual((opts.width, opts.height), (1024, 1024))
        with self.assertRaises(nc.ComposeError):
            nc.resolve_size(self.root, options(["--id", "p01-01", "--width", "1000", "--height", "1000"]))
        with self.assertRaises(nc.ComposeError):
            nc.resolve_size(self.root, options(["--id", "p01-01", "--width", "832"]))

    def test_composed_request_is_accepted_by_the_api_validator(self):
        request, _ = self.build()
        prepared, _ = api.prepare_request_data(self.root, request)
        # 無消費扱いの費用確認も、composeが送る controlnet_strength=1.0 では止まらない（他の未確認パラメーターは止まる）
        args = Namespace(cost_note="確認用の架空条件", confirm_zero_anlas=True, allow_anlas=False, confirm_v5_allowance=True)
        api.check_cost(args, prepared)
        prepared["parameters"]["controlnet_strength"] = 0.5
        with self.assertRaises(api.ClientError):
            api.check_cost(args, prepared)
        prepared["parameters"]["controlnet_strength"] = 1.0
        prepared["parameters"]["unknown_feature"] = 1
        with self.assertRaises(api.ClientError):
            api.check_cost(args, prepared)
        self.assertEqual(prepared["parameters"]["n_samples"], 1)
        self.assertEqual(batch.positive_texts(request)[0], request["input"])


if __name__ == "__main__":
    unittest.main()
