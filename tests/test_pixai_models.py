"""PixAIのモデルの一覧の読込と、モデルページからの登録を、外部通信なしで検証する。"""

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "templates" / "manga-project" / "scripts"))

import pixai_api as api
import pixai_models as pm


def page(model: dict, version: dict | None = None) -> str:
    """turbo-stream（番号で参照し合う配列）でモデルページの埋め込みデータを作る。"""
    flat = []

    def put(value):
        index = len(flat)
        flat.append(None)
        if isinstance(value, dict):
            item = {}
            for key, child in value.items():
                key_index = len(flat)
                flat.append(key)
                item[f"_{key_index}"] = put(child)
            flat[index] = item
        elif isinstance(value, list):
            flat[index] = [put(child) for child in value]
        else:
            flat[index] = value
        return index

    route = {"generationModel": model}
    if version is not None:
        route["generationModelVersion"] = version
    put({"loaderData": {"routes/_app.model": route}})
    return f"<script>window.__reactRouterContext.streamController.enqueue({json.dumps(json.dumps(flat))});</script>"


def model(kind="MMDIT26B_MODEL", use="COMMERCIAL", version_id="2024383379556065549", **extra):
    return {"id": "2024383378759147749", "title": "Sample", "type": kind, "permittedUse": use, "isNsfw": False,
            "extra": {"permissions": {"commercialUses": use == "COMMERCIAL", "shareImagesOnline": True}},
            "latestAvailableVersion": {"id": version_id, "name": "v1", "status": "available", "extra": {}}, **extra}


class PixaiModelsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "project.json").write_text("{}", encoding="utf-8")

    def test_bundled_catalog_has_official_models(self):
        self.assertEqual(api.MODELS["tsubaki2"]["id"], "1983308862240288769")
        self.assertEqual(api.MODELS["tsubaki3"]["default_mode"], "pro")
        self.assertTrue(all(m["commercialUse"] for m in api.MODELS.values()))
        self.assertFalse(api.supports(api.MODELS["tsubaki"]["id"], "dit", "mode"))  # 公式に mode は Tsubaki.2・Tsubaki.3 系だけ
        self.assertTrue(api.supports("1234567890", "dit", "mode"))  # 一覧にないDiTは種類で判断する
        self.assertFalse(api.supports(api.MODELS["tsubaki2"]["id"], "dit", "controlnet"))  # 403 を確認済み
        self.assertTrue(api.supports(api.MODELS["haruka2"]["id"], "sdxl", "controlnet"))
        self.assertFalse(api.supports(api.MODELS["tsubaki2"]["id"], "dit", "inpaint"))  # 400 を確認済み
        self.assertTrue(api.supports(api.MODELS["tsubaki3"]["id"], "dit", "inpaint"))
        with self.assertRaises(api.ClientError):  # 拒否を確認済みの mode
            api.prepare_request_data(self.root, {"api": "v2", "body": {"modelVersionId": api.MODELS["tsubaki3"]["id"], "prompt": "1girl",
                                                                       "aspectRatio": "2:3", "mode": "lite"}})
        with self.assertRaises(api.ClientError):
            api.prepare_request_data(self.root, {"api": "v2", "body": {"modelVersionId": api.MODELS["tsubaki"]["id"], "prompt": "1girl",
                                                                       "aspectRatio": "2:3", "mode": "standard"}})

    def test_parse_url_forms(self):
        self.assertEqual(pm.parse_url("https://pixai.art/ja/model/2024383378759147749/2024383379556065549"),
                         ("2024383378759147749", "2024383379556065549"))
        self.assertEqual(pm.parse_url("https://pixai.art/model/1884107375027888751-Tsubaki"), ("1884107375027888751", None))
        self.assertEqual(pm.parse_url("2024383378759147749"), ("2024383378759147749", None))
        with self.assertRaises(pm.ModelError):
            pm.parse_url("https://example.com/model/2024383378759147749")

    def test_entry_from_page_by_kind(self):
        info = pm.model_info(page(model()), None)
        self.assertEqual((info["id"], info["pixaiType"]), ("2024383379556065549", "MMDIT26B_MODEL"))
        entry = pm.catalog_entry(info)
        self.assertEqual((entry["type"], entry["mode"], entry["style"], entry["commercialUse"], entry["api"]), ("dit", True, True, True, "未検証"))
        entry = pm.catalog_entry(pm.model_info(page(model("SDXL_MODEL", "PERSONAL")), None))
        self.assertEqual((entry["type"], entry["mode"], entry["commercialUse"]), ("sdxl", False, False))
        self.assertFalse(pm.catalog_entry(pm.model_info(page(model("DIT7B_MODEL")), None))["mode"])
        with self.assertRaises(pm.ModelError):  # LoRA はモデルとして登録しない
            pm.catalog_entry(pm.model_info(page(model("LORA")), None))
        version = {"id": "2024383379556065549", "name": "v1", "status": "available", "extra": {"compatibility": {"negativePrompt": False}}}
        info = pm.model_info(page(model(), version), "2024383379556065549")
        self.assertFalse(pm.catalog_entry(info)["negativePrompt"])
        with self.assertRaises(pm.ModelError):  # URLの版がページにない
            pm.model_info(page(model()), "2024383379556065549")
        with self.assertRaises(pm.ModelError):
            pm.model_info("<html></html>", None)

    def test_add_writes_project_catalog_and_main_never_fetches_for_list(self):
        info = pm.model_info(page(model(version_id="9999999999")), None)
        pm.add(self.root, "sample", info, False)
        catalog = json.loads((self.root / api.MODELS_FILE).read_text(encoding="utf-8"))
        self.assertEqual(catalog["models"]["sample"]["id"], "9999999999")
        with self.assertRaises(pm.ModelError):
            pm.add(self.root, "sample", info, False)
        with self.assertRaises(pm.ModelError):  # 同じバージョンIDを別名で重ねない
            pm.add(self.root, "sample2", info, False)
        with self.assertRaises(pm.ModelError):
            pm.add(self.root, "Bad Name", info, False)
        self.assertEqual(api.load_models(self.root / api.MODELS_FILE)["sample"]["type"], "dit")
        with patch.object(pm, "fetch_page") as fetch:
            self.assertEqual(pm.main(["list"]), 0)
        fetch.assert_not_called()


class PixaiLoraRecordTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "project.json").write_text("{}", encoding="utf-8")

    def lora_page(self, base_type, version_id="5555555555", use="PERSONAL"):
        version = {"id": version_id, "name": "v1", "status": "available", "extra": {"triggerWords": "mio"}, "loraBaseModelType": base_type}
        return page(model("LORA", use, version_id), version)

    def test_records_once_and_checks_base_model(self):
        fetch = Mock(return_value=self.lora_page("MMDIT26A_MODEL"))
        version_id, record, fetched = pm.lora(self.root, "https://pixai.art/model/2024383378759147749/5555555555", False, fetch)
        self.assertEqual((version_id, record["baseModelType"], record["commercialUse"], fetched), ("5555555555", "MMDIT26A_MODEL", False, True))
        _, _, fetched = pm.lora(self.root, "https://pixai.art/model/2024383378759147749/5555555555", False, fetch)
        self.assertFalse(fetched)  # 記録済みは取り直さない
        self.assertEqual(fetch.call_count, 1)
        notes = api.lora_notes(self.root, api.MODELS["tsubaki3"]["id"], ["5555555555"])
        self.assertTrue(any("種類 MMDIT26A_MODEL" in n for n in notes))  # Tsubaki.2 系のLoRAを Tsubaki.3 に付けた
        self.assertTrue(any("商用利用" in n for n in notes))
        self.assertFalse(any("種類" in n for n in api.lora_notes(self.root, api.MODELS["tsubaki2"]["id"], ["5555555555"])))
        self.assertTrue(any("未確認" in n for n in api.lora_notes(self.root, api.MODELS["tsubaki2"]["id"], ["6666666666"])))
        with self.assertRaises(pm.ModelError):  # モデルのページはLoRAとして記録しない
            pm.lora(self.root, "https://pixai.art/model/2024383378759147749/7777777777", False,
                    Mock(return_value=page(model(version_id="7777777777"), {"id": "7777777777", "name": "v1", "extra": {}})))


class PixaiMaskTests(unittest.TestCase):
    def test_mask_is_white_inside_and_same_size(self):
        import pixai_mask
        mask = pixai_mask.make_mask((100, 80), [(10, 10, 50, 40)], [], 0)
        self.assertEqual((mask.size, mask.getpixel((30, 25)), mask.getpixel((90, 70))), ((100, 80), 255, 0))


if __name__ == "__main__":
    unittest.main()
