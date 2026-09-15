"""コマ割りの幾何学・重なり・読み順・全派生パターンの検証スクリプト。"""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from validate_panel_plan import validate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "templates/manga-project/templates/panel-templates"
catalog = json.loads((OUT / "catalog.json").read_text(encoding="utf-8"))
policy = json.loads((ROOT / "templates/manga-project/config/panel-layout-policy.json").read_text(encoding="utf-8"))
errors = []


def cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])


def overlaps(a, b):
    for poly in (a, b):
        for i, p in enumerate(poly):
            q = poly[(i + 1) % len(poly)]
            axis = (-(q[1] - p[1]), q[0] - p[0])
            x = [v[0] * axis[0] + v[1] * axis[1] for v in a]
            y = [v[0] * axis[0] + v[1] * axis[1] for v in b]
            if max(x) <= min(y) or max(y) <= min(x):
                return False
    return True


ids = [t["id"] for t in catalog["templates"]]
if len(ids) != len(set(ids)):
    errors.append("テンプレートIDに重複があります。")

for t in catalog["templates"]:
    polygons = [p["polygon"] for p in t["panels"]]
    if len(polygons) != t["panelCount"]:
        errors.append(f'{t["id"]}: コマ数不一致')
    if [p["order"] for p in t["panels"]] != list(range(1, t["panelCount"] + 1)):
        errors.append(f'{t["id"]}: 読む順不一致')
    for i, p in enumerate(polygons):
        if not all(60 <= x <= 940 and 60 <= y <= 1440 for x, y in p):
            errors.append(f'{t["id"]}: 枠が範囲外に出ています')
        if not all(cross(p[j], p[(j + 1) % 4], p[(j + 2) % 4]) > 0 for j in range(4)):
            errors.append(f'{t["id"]}: 凸四角形になっていません')
        for q in polygons[i + 1:]:
            if overlaps(p, q):
                errors.append(f'{t["id"]}: コマ同士が重なっています')
    for key in ("svg", "guideSvg", "json", "transparentPng", "previewPng"):
        p_path = OUT / t["assets"][key]
        if not p_path.exists():
            errors.append(f'{p_path}: ファイルが存在しません')
            continue
        if key.endswith("Svg") or key == "svg":
            ET.parse(p_path)
        if key == "json" and json.loads(p_path.read_text(encoding="utf-8")) != t:
            errors.append(f'{t["id"]}: 個別JSONがカタログと一致しません')
    if t["panelCount"] == 5 and not t["extra"]:
        values = [s for n, s in zip(t["rows"], t["splitPositionsFromLeft"]) if n == 2]
        if values != [0.5, 0.5] and (values[0] - 0.5) * (values[1] - 0.5) >= 0:
            errors.append(f'{t["id"]}: ５コマの幅パターンが不正です')
    if t["panelCount"] == 6 and len(set(t["splitPositionsFromLeft"])) != 3:
        errors.append(f'{t["id"]}: ６コマの縦区切りが揃ってしまっています')

five = [t for t in catalog["templates"] if t["panelCount"] == 5 and not t["extra"]]
if len(five) != 54:
    errors.append(f"５コマ基本派生数が54種類ではなく{len(five)}種類です")

two = [t for t in catalog["templates"] if t["panelCount"] == 2]
if len(two) != 5:
    errors.append(f"２コマテンプレート数が5種類ではなく{len(two)}種類です")

# 20ページサンプル案の検証
plan_result = validate(json.loads((OUT / "plan-example-20.json").read_text(encoding="utf-8")), catalog, policy)
errors.extend(plan_result["errors"])

# 境界値テスト（横長3段の間隔と連続20ページ上限）
def sample_plan(locations, total=40):
    rows = [{"page": p, "templateId": "P5-212-equal-normal-straight"} for p in range(1, total + 1)]
    for p in locations:
        rows[p - 1]["templateId"] = "P3-horizontal-up-right" if p % 2 else "P3-horizontal-straight"
    return {"pages": rows}


cases = [
    ("p1とp5（間3ページ）は不正", [1, 5], False),
    ("p1とp6（間4ページ）は有効", [1, 6], True),
    ("連続20ページで4回は不正", [1, 6, 11, 16], False),
    ("窓をまたいで4回は不正", [17, 22, 27, 32], False),
    ("20ページ内3回は有効", [1, 6, 11], True),
    ("20ページ窓の外なら有効", [1, 6, 11, 21], True)
]
boundary = []
for label, loc, expected in cases:
    actual = validate(sample_plan(loc), catalog, policy)["valid"]
    boundary.append({"case": label, "passed": actual == expected})
    if actual != expected:
        errors.append(f"境界テスト失敗: {label}")

report = {
    "valid": not errors,
    "templateCount": len(ids),
    "twoPanelVariants": len(two),
    "fivePanelVariants": len(five),
    "geometryErrors": errors,
    "boundaryCases": boundary,
    "planExampleValid": plan_result["valid"]
}
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["valid"] else 1)
