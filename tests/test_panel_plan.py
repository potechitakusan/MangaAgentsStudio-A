"""作品ごとのコマ割り設定が検査に反映されることを確認する。"""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_panel_plan import resolve_catalog_path, resolve_policy_path, validate


class PanelPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(resolve_catalog_path().read_text(encoding='utf-8'))
        cls.defaults = json.loads(resolve_policy_path().read_text(encoding='utf-8'))

    def setUp(self):
        self.policy = copy.deepcopy(self.defaults)

    def plan(self, count=20, template='P5-212-equal-normal-straight', horizontal=()):
        return {'pages': [{'page': p, 'templateId': 'P3-horizontal-straight' if p in horizontal else template}
                          for p in range(1, count + 1)]}

    def check(self, plan):
        return validate(plan, self.catalog, self.policy)

    def test_custom_most_common_count(self):
        plan = self.plan(template='P4-211')
        self.assertFalse(self.check(plan)['valid'])
        self.policy['hardRules']['mostCommonPanelCount'] = 4
        self.assertTrue(self.check(plan)['valid'])
        self.policy['hardRules']['mostCommonPanelCount'] = None
        self.assertTrue(self.check(plan)['valid'])

    def test_custom_gap_and_limit_are_used_in_messages(self):
        rule = self.policy['hardRules']['horizontalThree']
        rule.update(minimumInterveningPages=1, maximumInWindow=4)
        self.assertTrue(self.check(self.plan(horizontal=(1, 3, 5, 7)))['valid'])
        errors = self.check(self.plan(horizontal=(1, 2, 4, 6, 8)))['errors']
        self.assertTrue(any('1ページ以上' in message for message in errors))
        self.assertTrue(any('上限は4回' in message for message in errors))

    def test_restrictions_can_be_disabled(self):
        plan = self.plan(template='P3-horizontal-straight')
        self.assertFalse(self.check(plan)['valid'])
        self.policy['hardRules']['horizontalThree']['enabled'] = False
        self.policy['hardRules']['mostCommonPanelCount'] = None
        self.policy['recommended']['avoidAdjacentIdenticalTemplate'] = False
        result = self.check(plan)
        self.assertTrue(result['valid'])
        self.assertEqual(result['warnings'], [])

    def test_short_plan_does_not_require_five_panels(self):
        self.assertTrue(self.check(self.plan(count=4, template='P4-211'))['valid'])

    def test_recommended_percent_is_not_an_exact_quota(self):
        self.assertTrue(self.check(self.plan())['valid'])

    def test_horizontal_window_does_not_change_diagonal_window(self):
        self.policy['hardRules']['horizontalThree']['rollingWindowPages'] = 5
        plan = self.plan()
        for idx in (0, 10):
            plan['pages'][idx]['templateId'] = 'P5-212-equal-normal-diag-r'
        self.assertEqual(self.check(plan)['maximumDiagonalFiveIn20Pages'], 2)
        self.policy['recommended']['diagonalFiveMaximumPer20'] = 2
        self.assertFalse(any('斜め' in message for message in self.check(plan)['warnings']))

    def test_invalid_page_input_is_reported(self):
        for pages in ([{}], [{'page': True, 'templateId': 'P4-211'}],
                      [{'page': 1, 'templateId': 'missing'}],
                      [{'page': 2, 'templateId': 'P4-211'}]):
            with self.subTest(pages=pages):
                self.assertFalse(self.check({'pages': pages})['valid'])

    def test_explicit_missing_paths_do_not_fall_back(self):
        for resolver in (resolve_catalog_path, resolve_policy_path):
            with self.assertRaises(FileNotFoundError):
                resolver(ROOT / '.work' / 'missing-panel-config.json')


if __name__ == '__main__':
    unittest.main()
