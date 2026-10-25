"""PixAIのキー読込・要求の検証・送信と記録を、外部通信なしで検証する。"""

from argparse import Namespace
from io import BytesIO
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

KEY = "fixture-pixai-key"


def png(size=(848, 1280), fmt="PNG"):
    out = BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(out, format=fmt)
    return out.getvalue()


def v2(**body):
    base = {"modelVersionId": api.MODELS["tsubaki2"]["id"], "prompt": "1girl, solo, standing", "aspectRatio": "2:3", "seed": 7}
    base.update(body)
    return {"api": "v2", "body": base}


class FakeApi:
    """作成・照会・アップロードの応答を返す。呼び出しを記録する。"""

    def __init__(self, status="completed", reject=False):
        self.calls, self.status, self.reject = [], status, reject

    def __call__(self, key, method, endpoint, *, payload=None, content_type="application/json", timeout=60):
        self.calls.append((method, endpoint, payload))
        if endpoint in ("/v2/image/create", "/v1/task"):
            if self.reject:
                raise api.RejectedError("HTTP 400: [入力エラー] テスト")
            body = json.loads(payload)
            self.count = body.get("batchSize") or body.get("parameters", {}).get("batchSize") or 1
            return 200, b'{"id": "123", "status": "waiting"}'
        if endpoint.startswith("/v1/task/"):
            urls = [f"https://cdn.example/{i}.webp" for i in range(self.count)]
            return 200, json.dumps({"id": "123", "status": self.status,
                                    "outputs": {"mediaIds": [str(i) for i in range(self.count)], "mediaUrls": urls}}).encode()
        if endpoint == "/v1/media/upload":
            return 200, b'{"id": "777", "type": "IMAGE"}'
        raise AssertionError(endpoint)


class PixaiApiTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "project.json").write_text("{}", encoding="utf-8")
        (self.root / "config").mkdir()
        (self.root / "config/page-layout.json").write_text(json.dumps({"generationCanvas": {"width": 832, "height": 1216}}), encoding="utf-8")
        (self.root / ".env").write_text(f"NOVELAI_API_KEY=other\nPIXAI_API_KEY={KEY}\n", encoding="utf-8")
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()
        patch.object(api.time, "sleep").start()

    def args(self, **extra):
        base = dict(confirm_credits=True, allow_unverified=False, cost_note="利用者が1枚を許可", timeout=30)
        base.update(extra)
        return Namespace(**base)

    def test_key_order_and_errors_hide_values(self):
        self.assertEqual(api.load_key(self.root), (KEY, ".env"))
        (self.root / ".secrets").mkdir()
        (self.root / ".secrets/pixai.env").write_text("PIXAI_API_KEY=fixture-secret-file\n", encoding="utf-8")
        self.assertEqual(api.load_key(self.root)[1], ".secrets/pixai.env")
        with patch.dict(os.environ, {"PIXAI_API_KEY": "fixture-env"}):
            self.assertEqual(api.load_key(self.root), ("fixture-env", "環境変数 PIXAI_API_KEY"))
        (self.root / ".secrets/pixai.env").write_text("PIXAI_API_KEY=bad value with space\n", encoding="utf-8")
        with self.assertRaises(api.ClientError) as raised:
            api.load_key(self.root)
        self.assertNotIn("bad value", str(raised.exception))

    def test_v2_defaults_and_validation(self):
        request, notes, unverified = api.prepare_request_data(self.root, {"api": "v2", "body": {
            "modelVersionId": api.MODELS["tsubaki2"]["id"], "prompt": "1girl"}})
        body = request["body"]
        self.assertEqual((body["aspectRatio"], body["size"], body["batchSize"], body["promptHelper"]), ("2:3", "1k", 1, "disable"))
        self.assertEqual(api.output_size(body), (848, 1280))
        self.assertIsInstance(body["seed"], int)
        self.assertEqual(unverified, [])
        bad = [{"modelId": "1"}, {"callbackUrl": "https://example.com"}, {"aspectRatio": "2:5"}, {"batchSize": 2},
               {"loras": [{"modelId": "123456", "weight": 1.5}]}, {"loras": [{"modelId": "123456"}] * 6},
               {"style": {"type": "preset", "key": "unknown"}}, {"sampling": {"steps": 0}}]
        for extra in bad:
            with self.subTest(extra=extra), self.assertRaises(api.ClientError):
                api.prepare_request_data(self.root, v2(**extra))
        with self.assertRaises(api.ClientError):  # SDXLでは mode が公式に拒否される
            api.prepare_request_data(self.root, v2(modelVersionId=api.MODELS["haruka2"]["id"], mode="pro"))
        _, notes, _ = api.prepare_request_data(self.root, v2(modelVersionId=api.MODELS["haruka2"]["id"], style={"type": "preset", "key": "chibi"}))
        self.assertTrue(any("無視" in n for n in notes))

    def test_tsubaki3_modes_and_unknown_dit_note(self):
        tsubaki3 = api.MODELS["tsubaki3"]["id"]
        with self.assertRaises(api.ClientError):  # 実生成で 422 unknown inferenceProfile を確認済み
            api.prepare_request_data(self.root, v2(modelVersionId=tsubaki3, mode="standard"))
        _, notes, _ = api.prepare_request_data(self.root, v2(modelVersionId=tsubaki3, mode="pro"))
        self.assertFalse(any("mode" in n for n in notes))
        _, notes, _ = api.prepare_request_data(self.root, v2(modelVersionId=tsubaki3, mode="ultra"))
        self.assertFalse(any("mode" in n for n in notes))  # ultra も受理を確認済み
        with self.assertRaises(api.ClientError):  # lite は 422 を確認済み
            api.prepare_request_data(self.root, v2(modelVersionId=tsubaki3, mode="lite"))
        _, notes, _ = api.prepare_request_data(self.root, v2(modelVersionId=api.MODELS["tsubaki3-flash"]["id"], mode="standard"))
        self.assertTrue(any("未確認" in n for n in notes))
        request = {"api": "v2", "model_type": "dit", "body": {"modelVersionId": "1234567890", "prompt": "1girl", "aspectRatio": "2:3",
                                                              "seed": 7, "mode": "standard"}}
        _, notes, _ = api.prepare_request_data(self.root, request)
        self.assertTrue(any("使える mode は未確認" in n for n in notes))

    def test_v1_marks_unverified_and_requires_flag(self):
        Image.new("RGB", (32, 32)).save(self.root / "ref.png")
        request = {"api": "v1", "parameters": {"prompts": "1girl", "modelId": api.MODELS["haruka2"]["id"], "width": 848, "height": 1280,
                                               "upscale": 1.5, "enableADetailer": True, "ipAdapter": {"referenceFiles": ["ref.png"]}}}
        request, notes, unverified = api.prepare_request_data(self.root, request)
        self.assertEqual(unverified, ["ipAdapter"])
        with self.assertRaises(api.ClientError):
            api.check_cost(self.args(), request, unverified)
        api.check_cost(self.args(allow_unverified=True), request, unverified)
        with self.assertRaises(api.ClientError):
            api.check_cost(self.args(confirm_credits=False, allow_unverified=True), request, unverified)
        for extra in ({"width": 1536}, {"lora": {"1234567": 0.5, "2345678": 0.5, "3456789": 0.5, "4567890": 0.5}},
                      {"workflow": {}}, {"controlNets": [{"type": "pose", "mediaId": "1"}]}):
            with self.subTest(extra=extra), self.assertRaises(api.ClientError):
                data = json.loads(json.dumps(request))
                data["parameters"].update(extra)
                api.prepare_request_data(self.root, data)

    def test_generation_saves_pngs_records_and_never_sends_key_elsewhere(self):
        fake = FakeApi()
        request, _, _ = api.prepare_request_data(self.root, v2(batchSize=4))
        with patch.object(api, "api_request", side_effect=fake), patch.object(api, "download", return_value=png(fmt="WEBP")) as download:
            saved = api.execute_generation(self.root, request, "output/pixai/c/r001.png", self.args(), [], log=lambda _: None)
        self.assertEqual([p.name for p in saved], ["r001.png", "r002.png", "r003.png", "r004.png"])
        for path in saved:
            self.assertEqual(api.png_size(path.read_bytes()), (848, 1280))
        record = json.loads((self.root / "output/pixai/c/r001.pixai.json").read_text(encoding="utf-8"))
        self.assertEqual((record["status"], record["taskId"], record["actualCreditCost"]), ("PNG保存済み", "123", None))
        self.assertEqual(len(record["outputs"]), 4)
        text = "".join(p.read_text(encoding="utf-8") for p in (self.root / "output").rglob("*.json"))
        self.assertNotIn(KEY, text)
        download.assert_called_with("https://cdn.example/3.webp")
        self.assertEqual([c[1] for c in fake.calls], ["/v2/image/create", "/v1/task/123"])

    def test_rejection_and_failed_task_move_records_to_failed(self):
        request, _, _ = api.prepare_request_data(self.root, v2())
        with patch.object(api, "api_request", side_effect=FakeApi(reject=True)):
            with self.assertRaises(api.RejectedError):
                api.execute_generation(self.root, request, "output/pixai/c/r001.png", self.args(), [], log=lambda _: None)
        folder = self.root / "output/pixai/c"
        self.assertFalse((folder / "r001.pixai.json").exists())
        self.assertEqual(len(list((folder / "failed").iterdir())), 1)
        with patch.object(api, "api_request", side_effect=FakeApi(status="failed")):
            with self.assertRaises(api.ClientError):
                api.execute_generation(self.root, request, "output/pixai/c/r001.png", self.args(), [], log=lambda _: None)
        self.assertFalse((folder / "r001.pixai.json").exists())
        self.assertEqual(len(list((folder / "failed").iterdir())), 2)

    def test_timeout_keeps_task_id_and_fetch_recovers_without_resending(self):
        request, _, _ = api.prepare_request_data(self.root, v2())
        fake = FakeApi(status="running")
        with patch.object(api, "api_request", side_effect=fake), patch.object(api, "download", return_value=png()):
            with self.assertRaises(api.ClientError):
                api.execute_generation(self.root, request, "output/pixai/c/r001.png", self.args(timeout=0), [], log=lambda _: None)
            record = json.loads((self.root / "output/pixai/c/r001.pixai.json").read_text(encoding="utf-8"))
            self.assertEqual(record["taskId"], "123")
            fake.status = "completed"
            saved = api.fetch(self.root, "output/pixai/c/r001.pixai.json", log=lambda _: None)
        self.assertEqual([p.name for p in saved], ["r001.png"])
        self.assertEqual(sum(c[1] == "/v2/image/create" for c in fake.calls), 1)

    def test_partial_batch_stops_and_fetch_keeps_saved_images(self):
        request, _, _ = api.prepare_request_data(self.root, v2(batchSize=4))
        fake = FakeApi()
        image = png()
        with patch.object(api, "api_request", side_effect=fake), patch.object(api, "download", side_effect=[image, api.ClientError("temporary failure"), image, image]):
            with self.assertRaisesRegex(api.ClientError, "fetch"):
                api.execute_generation(self.root, request, "output/pixai/c/r001.png", self.args(), [], log=lambda _: None)
        first = self.root / "output/pixai/c/r001.png"
        self.assertEqual(first.read_bytes(), image)
        with patch.object(api, "api_request", side_effect=fake), patch.object(api, "download", return_value=image) as download:
            saved = api.fetch(self.root, "output/pixai/c/r001.pixai.json", log=lambda _: None)
        self.assertEqual(len(saved), 4)
        self.assertEqual(download.call_count, 1)
        self.assertEqual(first.read_bytes(), image)
        self.assertEqual(sum(c[0] == "POST" for c in fake.calls), 1)

    def test_v1_uploads_local_images_and_reuses_media_ids(self):
        Image.new("RGB", (32, 32)).save(self.root / "ref.png")
        request, _, unverified = api.prepare_request_data(self.root, {"api": "v1", "parameters": {
            "prompts": "1girl", "modelId": api.MODELS["haruka2"]["id"], "width": 848, "height": 1280, "mediaFile": "ref.png", "strength": 0.5,
            "controlNets": [{"type": "openpose", "mediaFile": "ref.png"}], "ipAdapter": {"referenceFiles": ["ref.png"]}}})
        fake = FakeApi()
        with patch.object(api, "api_request", side_effect=fake), patch.object(api, "download", return_value=png()):
            api.execute_generation(self.root, request, "output/pixai/c/r001.png", self.args(allow_unverified=True), unverified, log=lambda _: None)
        sent = json.loads((self.root / "output/pixai/c/r001.request-body.json").read_text(encoding="utf-8"))["parameters"]
        self.assertEqual((sent["mediaId"], sent["controlNets"][0]["mediaId"], sent["ipAdapter"]["referenceImages"]), ("777", "777", ["777"]))
        self.assertNotIn("mediaFile", sent)
        self.assertEqual(sum(c[1] == "/v1/media/upload" for c in fake.calls), 1)

    def test_auth_check_reads_404_as_authenticated(self):
        with patch.object(api, "api_request", side_effect=api.ClientError("HTTP 404: [見つからない]")):
            self.assertIn("認証成功", api.auth_check(KEY))
        with patch.object(api, "api_request", side_effect=api.ClientError("HTTP 401: [認証失敗]")):
            with self.assertRaises(api.ClientError):
                api.auth_check(KEY)

    def test_endpoint_allowlist_and_download_scheme(self):
        with self.assertRaises(api.ClientError):
            api.api_request(KEY, "GET", "/v1/user")
        with self.assertRaises(api.ClientError):
            api.download("http://cdn.example/a.png")


if __name__ == "__main__":
    unittest.main()
