"""NovelAIの認証情報保護・誤送信防止・応答保存を外部通信なしで検証する。"""

from argparse import Namespace
import base64
from contextlib import redirect_stdout
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "templates/manga-project/scripts"))
import novelai_api as api


def sample_png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) + chunk(b"IEND", b""))


class NovelAIClientTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / ".secrets").mkdir()
        (self.root / "config").mkdir()
        (self.root / "input").mkdir()
        (self.root / "config/page-layout.json").write_text(
            json.dumps({"generationCanvas": {"width": 832, "height": 1216}}), encoding="utf-8")
        self.request = {"action": "generate", "model": "nai-diffusion-4-5-full", "input": "cat",
                        "parameters": {"seed": 1, "sampler": "k_euler_ancestral", "scale": 5}}
        self.save_request()
        self.args = Namespace(command="generate", request="input/request.json", execute=False,
                              output="output/test.png", confirm_zero_anlas=False, allow_anlas=False,
                              cost_note=None, confirm_v5_allowance=False)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()

    def save_request(self):
        (self.root / "input/request.json").write_text(json.dumps(self.request), encoding="utf-8")

    def test_key_precedence_and_value_is_not_printed(self):
        (self.root / ".env").write_text("NOVELAI_API_KEY=fixture-root", encoding="utf-8")
        (self.root / ".secrets/novelai.env").write_text(
            '\ufeffexport NOVELAI_API_KEY="fixture-project" # 注釈\n', encoding="utf-8")
        self.assertEqual(api.load_key(self.root), ("fixture-project", ".secrets/novelai.env"))
        os.environ["NOVELAI_API_KEY"] = "fixture-process"
        output = StringIO()
        with redirect_stdout(output), patch.object(api, "api_request") as network:
            api.run(Namespace(command="key-status"), self.root)
        self.assertNotIn("fixture-", output.getvalue())
        self.assertIn("環境変数", output.getvalue())
        network.assert_not_called()

    def test_example_is_never_loaded_and_commands_are_rejected(self):
        (self.root / ".env.example").write_text("NOVELAI_API_KEY=fixture-example", encoding="utf-8")
        with self.assertRaises(api.ClientError):
            api.load_key(self.root)
        (self.root / ".env").write_text("NOVELAI_API_KEY=$(fixture-command)", encoding="utf-8")
        with self.assertRaises(api.ClientError) as caught:
            api.load_key(self.root)
        self.assertNotIn("fixture-command", str(caught.exception))

    def test_duplicate_key_and_path_escape_are_rejected(self):
        (self.root / ".env").write_text("NOVELAI_API_KEY=one\nNOVELAI_API_KEY=two", encoding="utf-8")
        with self.assertRaises(api.ClientError):
            api.load_key(self.root)
        with self.assertRaises(api.ClientError):
            api.project_path(self.root, "../outside.json")

    def test_missing_file_reports_setup_example_without_network(self):
        with patch.object(api, "api_request") as network, self.assertRaises(api.ClientError) as caught:
            api.run(Namespace(command="status"), self.root)
        message = str(caught.exception)
        self.assertIn(".secrets/novelai.env: ファイルなし", message)
        self.assertIn("NOVELAI_API_KEY=実際のトークン", message)
        self.assertIn("秘密にするのは右辺", message)
        network.assert_not_called()

    def test_config_diagnoses_do_not_echo_input(self):
        examples = (
            ("fixture-private", "設定行なし"),
            ("NOVELAI_API_KEY=", "値が空"),
            ("NOVELAI_API_KEY= # fixture-private", "値が空"),
            ('NOVELAI_API_KEY="  "', "値が空"),
            ("NOVELAI_API_KEY:fixture-private", "形式不正"),
            ('NOVELAI_API_KEY="fixture-private', "形式不正"),
            ("NOVELAI_API_KEY=Bearer fixture-private", "形式不正"),
        )
        for content, diagnosis in examples:
            with self.subTest(diagnosis=diagnosis, content=content):
                (self.root / ".secrets/novelai.env").write_text(content, encoding="utf-8")
                with self.assertRaises(api.ClientError) as caught:
                    api.load_key(self.root)
                self.assertIn("[設定不備]", str(caught.exception))
                self.assertIn(".secrets/novelai.env: " + diagnosis, str(caught.exception))
                self.assertNotIn("fixture-private", str(caught.exception))

    def test_empty_sources_still_fall_back_to_configured_file(self):
        os.environ["NOVELAI_API_KEY"] = " "
        (self.root / ".secrets/novelai.env").write_text("NOVELAI_API_KEY= # 空", encoding="utf-8")
        (self.root / ".env").write_text("NOVELAI_API_KEY=fixture-root", encoding="utf-8")
        self.assertEqual(api.load_key(self.root), ("fixture-root", ".env"))

    def test_invalid_environment_names_source_without_value(self):
        os.environ["NOVELAI_API_KEY"] = "Bearer fixture-private"
        with self.assertRaises(api.ClientError) as caught:
            api.load_key(self.root)
        self.assertIn("環境変数 NOVELAI_API_KEY: 形式不正", str(caught.exception))
        self.assertNotIn("fixture-private", str(caught.exception))

    def test_generation_preview_never_reads_key_or_calls_api(self):
        with redirect_stdout(StringIO()), patch.object(api, "load_key") as key, patch.object(api, "api_request") as network:
            api.run(self.args, self.root)
        key.assert_not_called()
        network.assert_not_called()
        self.assertFalse((self.root / "output").exists())

    def test_page_size_mismatch_and_multiple_samples_are_rejected(self):
        for parameters in ({"width": 1024}, {"n_samples": 2}, {"n_samples": True}):
            with self.subTest(parameters=parameters):
                original = self.request["parameters"].copy()
                self.request["parameters"].update(parameters)
                self.save_request()
                with self.assertRaises(api.ClientError):
                    api.prepare_request(self.root, self.args.request)
                self.request["parameters"] = original

    def test_no_cost_confirmation_stops_before_network(self):
        self.args.execute = True
        with redirect_stdout(StringIO()), patch.object(api, "api_request") as network:
            with self.assertRaises(api.ClientError):
                api.run(self.args, self.root)
        network.assert_not_called()

    def test_v5_defaults_and_free_reference_guard(self):
        self.request["model"] = "nai-diffusion-5"
        self.save_request()
        request, _ = api.prepare_request(self.root, self.args.request)
        self.assertEqual(request["parameters"]["steps"], 23)
        self.args.cost_note = "確認用の架空条件"
        self.args.confirm_zero_anlas = True
        with self.assertRaises(api.ClientError):
            api.check_cost(self.args, request)
        self.args.confirm_v5_allowance = True
        api.check_cost(self.args, request)
        request["parameters"]["director_reference_images"] = ["fixture"]
        with self.assertRaises(api.ClientError):
            api.check_cost(self.args, request)

    def test_subscription_omits_private_fields(self):
        response = {"active": True, "tier": 3, "plainTextEmail": "private",
                    "paymentProcessorData": {"private": "fixture"},
                    "usage": {"percent": 90, "isNegative": False, "private": "fixture"}}
        with patch.object(api, "api_request", return_value=(json.dumps(response).encode(), "application/json")):
            result = api.subscription("fixture-key")
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(result["usage"]["percent"], 90)

    def test_http_error_is_not_retried_or_echoed(self):
        opener = Mock()
        opener.open.side_effect = HTTPError(api.API_ROOT, 429, "fixture-private", {}, BytesIO(b"fixture-private"))
        with patch.object(api, "build_opener", return_value=opener):
            with self.assertRaises(api.ClientError) as caught:
                api.api_request("fixture-key", "/ai/generate-image", payload=b"{}")
        self.assertNotIn("fixture-", str(caught.exception))
        self.assertEqual(opener.open.call_count, 1)
        self.assertIsNone(api.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))

    def test_authentication_and_connection_errors_are_distinct(self):
        for error, expected in (
            (HTTPError(api.API_ROOT, 401, "fixture-private", {}, BytesIO()), "[認証失敗]"),
            (HTTPError(api.API_ROOT, 403, "fixture-private", {}, BytesIO()), "[アクセス拒否]"),
            (HTTPError(api.API_ROOT, 503, "fixture-private", {}, BytesIO()), "[サーバーエラー]"),
            (URLError("fixture-private"), "[通信障害]"),
            (TimeoutError("fixture-private"), "[通信障害]"),
        ):
            with self.subTest(expected=expected):
                opener = Mock()
                opener.open.side_effect = error
                with patch.object(api, "build_opener", return_value=opener), self.assertRaises(api.ClientError) as caught:
                    api.api_request("fixture-key", "/user/subscription")
                message = str(caught.exception)
                self.assertIn(expected, message)
                self.assertNotIn("fixture-", message)
                self.assertIn("画像生成は要求していません", message)
                if expected == "[通信障害]":
                    self.assertIn("キーの正誤は判定できません", message)
                    self.assertIn("接続制限", message)
                self.assertEqual(opener.open.call_count, 1)

    def test_json_and_zip_return_the_same_png_without_extracting_paths(self):
        png = sample_png()
        body = json.dumps({"images": [{"image": base64.b64encode(png).decode()}]}).encode()
        self.assertEqual(api.image_bytes(body, "application/json"), png)
        archive = BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("../../outside.png", png)
        self.assertEqual(api.image_bytes(archive.getvalue(), "application/zip"), png)
        self.assertEqual(api.png_size(png), (1, 1))
        for invalid in (png[:-12], png + b"trailing", png[:40] + b"broken" + png[46:]):
            with self.assertRaises(api.ClientError):
                api.png_size(invalid)

    def test_generation_record_has_no_key_and_prevents_resend(self):
        self.args.execute = True
        self.args.allow_anlas = True
        self.args.cost_note = "テスト用の架空の許可"
        os.environ["NOVELAI_API_KEY"] = "fixture-key"
        png = sample_png()
        response = json.dumps({"images": [{"image": base64.b64encode(png).decode()}]}).encode()
        with redirect_stdout(StringIO()), patch.object(api, "subscription", return_value={"active": True, "tier": 3}), \
                patch.object(api, "api_request", return_value=(response, "application/json")) as network:
            api.run(self.args, self.root)
            with self.assertRaises(api.ClientError):
                api.run(self.args, self.root)
        self.assertEqual(network.call_count, 1)
        record = (self.root / "output/test.novelai.json").read_text(encoding="utf-8")
        self.assertNotIn("fixture-key", record)
        self.assertIsNone(json.loads(record)["actualAnlasCost"])
        self.assertEqual((self.root / "output/test.png").read_bytes(), png)


if __name__ == "__main__":
    unittest.main()
