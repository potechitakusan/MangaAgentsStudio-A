"""採用案のコマ数・横長３段の間隔・連続20ページ上限を検証する。"""
import argparse
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def resolve_catalog_path(explicit_path=None):
    if explicit_path is not None:
        if not Path(explicit_path).is_file():
            raise FileNotFoundError(f"指定したカタログがありません: {explicit_path}")
        return Path(explicit_path)
    candidates = [
        ROOT / "templates/manga-project/templates/panel-templates/catalog.json",
        ROOT / "templates/panel-templates/catalog.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("catalog.json が見つかりません。")


def resolve_policy_path(explicit_path=None):
    if explicit_path is not None:
        if not Path(explicit_path).is_file():
            raise FileNotFoundError(f"指定した設定がありません: {explicit_path}")
        return Path(explicit_path)
    candidates = [
        ROOT / "templates/manga-project/config/panel-layout-policy.json",
        ROOT / "config/panel-layout-policy.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("panel-layout-policy.json が見つかりません。")


def validate(plan, catalog, policy):
    templates = {t["id"]: t for t in catalog["templates"]}
    rows = plan.get("pages", [])
    errors = []
    warnings = []
    if not isinstance(rows, list) or not rows:
        return {"valid": False, "errors": ["採用ページがありません。"], "warnings": [], "counts": {}}
    if any(not isinstance(r, dict) or type(r.get("page")) is not int
           or not isinstance(r.get("templateId"), str) for r in rows):
        return {"valid": False, "errors": ["各ページに整数のpageと文字列のtemplateIdが必要です。"], "warnings": [], "counts": {}}
    numbers = [r["page"] for r in rows]
    if numbers != list(range(1, len(rows) + 1)):
        errors.append("ページ番号は1から連続し、重複がない必要があります。")
    for r in rows:
        if r["templateId"] not in templates:
            errors.append(f'p{r["page"]}：不明なテンプレート {r["templateId"]}')
    if errors:
        return {"valid": False, "errors": errors, "warnings": [], "counts": {}}

    counts = Counter(templates[r["templateId"]]["panelCount"] for r in rows)
    rule = policy["hardRules"]["horizontalThree"]
    enabled = rule.get("enabled", True)
    minimum_gap = rule["minimumInterveningPages"]
    window_size = rule["rollingWindowPages"]
    limit = rule["maximumInWindow"]
    restricted = [r["page"] for r in rows
                  if templates[r["templateId"]]["restrictionGroup"] == rule["restrictionGroup"]
                  and (rule.get("includeDiagonalVariants", True) or not templates[r["templateId"]].get("diagonal"))]
    for a, b in zip(restricted, restricted[1:]):
        if enabled and b - a - 1 < minimum_gap:
            errors.append(f"横長３段：p{a}とp{b}の間は{b - a - 1}ページ。設定では{minimum_gap}ページ以上必要です。")
    max_in_window = 0
    diagonal_max = 0
    windows = []
    for start in range(1, max(2, len(rows) - window_size + 2)):
        end = min(len(rows), start + window_size - 1)
        active = [p for p in restricted if start <= p <= end]
        max_in_window = max(max_in_window, len(active))
        if enabled and len(active) > limit:
            errors.append(f"p{start}〜{end}で横長３段が{len(active)}回。設定の上限は{limit}回です。")
        windows.append({"start": start, "end": end, "horizontalThree": active})

    diagonal_limit = policy["recommended"].get("diagonalFiveMaximumPer20")
    for start in range(1, max(2, len(rows) - 20 + 2)):
        end = min(len(rows), start + 19)
        diagonals = [
            r["page"] for r in rows
            if start <= r["page"] <= end
            and templates[r["templateId"]]["panelCount"] == 5
            and templates[r["templateId"]].get("diagonal")
        ]
        diagonal_max = max(diagonal_max, len(diagonals))
        if diagonal_limit is not None and len(diagonals) > diagonal_limit:
            warnings.append(f"p{start}〜{end}の斜め５コマは{len(diagonals)}回。設定の目安{diagonal_limit}回を超えています。")

    dominant = policy["hardRules"].get("mostCommonPanelCount")
    minimum_pages = policy["hardRules"].get("dominanceMinimumPages", 20)
    if dominant is not None and len(rows) >= minimum_pages and counts.get(dominant, 0) <= max((v for k, v in counts.items() if k != dominant), default=0):
        errors.append(f"設定で指定した{dominant}コマの採用数が単独最多になっていません。")
    for a, b in zip(rows, rows[1:]):
        if policy["recommended"].get("avoidAdjacentIdenticalTemplate", True) and a["templateId"] == b["templateId"] and not (a.get("spreadGroup") and a.get("spreadGroup") == b.get("spreadGroup")):
            warnings.append(f'p{a["page"]}〜{b["page"]}で同じテンプレートが連続しています。')

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "pageCount": len(rows),
        "counts": dict(sorted(counts.items())),
        "percent": {str(k): round(v / len(rows) * 100, 2) for k, v in sorted(counts.items())},
        "horizontalThreePages": restricted,
        "minimumInterveningPages": min((b - a - 1 for a, b in zip(restricted, restricted[1:])), default=None),
        "horizontalThreeWindowPages": window_size,
        "maximumHorizontalThreeInWindow": max_in_window,
        "maximumDiagonalFiveIn20Pages": diagonal_max,
        "windows": windows
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--catalog", type=Path, default=None)
    parser.add_argument("--policy", type=Path, default=None)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cat_path = resolve_catalog_path(args.catalog)
    pol_path = resolve_policy_path(args.policy)

    plan_data = json.loads(args.plan.read_text(encoding="utf-8"))
    catalog_data = json.loads(cat_path.read_text(encoding="utf-8"))
    policy_data = json.loads(pol_path.read_text(encoding="utf-8"))

    result = validate(plan_data, catalog_data, policy_data)
    content = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(content + "\n", encoding="utf-8")
    print(content)
    raise SystemExit(0 if result["valid"] else 1)
