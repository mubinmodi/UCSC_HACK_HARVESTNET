"""Ticket #6: every result number on the demo slides is what the code produces now (ADR 0002).

The slides (``docs/demo/slides.html``) carry their results in one JSON block. This test runs the
same evaluation and compares. If it fails, rerun
``python -m harvestnet_core evaluate core_fixtures/*.json`` and copy the new values into the
block, keeping the "synthetic" label. All data is synthetic.
"""
import json
import re
import unittest
from pathlib import Path

import platform_source  # noqa: F401  (Lane C on the import path)

from harvestnet_core.evaluation import evaluate


SLIDES = Path('docs/demo/slides.html')
FIELDS = ('method', 'status', 'collected_by_households_lb', 'committed_to_food_banks_lb', 'produce_wasted_lb',
          'uncollected_by_scenario_households_lb', 'worst_served_coverage', 'households_reached', 'invalid_commitments')


def slide_results():
    html = SLIDES.read_text(encoding='utf-8')
    block = re.search(r'<script type="application/json" id="harvestnet-results">(.*?)</script>', html, re.S)
    return json.loads(block.group(1))


class DemoSlideNumbers(unittest.TestCase):
    def test_results_match_the_evaluation(self):
        data = slide_results()
        self.assertEqual(data['run_mode'], 'synthetic')
        for shown in data['scenarios']:
            with self.subTest(scenario=shown['scenario_id']):
                fixture = json.loads(Path(f"core_fixtures/{shown['scenario_id']}.json").read_text(encoding='utf-8'))
                actual = evaluate(fixture)
                self.assertEqual(shown['run_mode'], actual['run_mode'])
                self.assertEqual(shown['synthetic'], actual['synthetic'])
                self.assertTrue(shown['synthetic'], 'demo results must be labeled synthetic')
                expected = [{k: m.get(k) for k in FIELDS} for m in actual['methods']]
                self.assertEqual(sorted(shown['methods'], key=lambda m: m['method']), sorted(expected, key=lambda m: m['method']))

    def test_every_fixture_is_on_the_slides(self):
        shown = {s['scenario_id'] for s in slide_results()['scenarios']}
        self.assertEqual(shown, {p.stem for p in Path('core_fixtures').glob('*.json')})

    def test_fair_share_table_matches_the_calculator_table(self):
        html = SLIDES.read_text(encoding='utf-8')
        table = json.loads(Path('agents/src/harvestnet_agents/data/fair_share_table.json').read_text(encoding='utf-8'))
        rows = dict(re.findall(r'<tr><td>(\d) (?:person|people)</td><td class="num">(\d+) lb</td></tr>', html))
        self.assertEqual({k: int(v) for k, v in rows.items()}, table['pounds_by_household_size'])
        self.assertIn(f"+{table['each_additional_person_lb']} lb", html)
        self.assertIn(table['version'], html)


if __name__ == '__main__':
    unittest.main()
