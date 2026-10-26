"""One terms hash: ``sha256:`` plus the hex digest of canonical JSON (README decision 8).

The canonical function lives in ``harvestnet_agents.terms``. The platform ships alone (its image
and CI do not carry the agents package), so ``harvestnet_platform.transport.terms_hash`` restates
the same two lines; this test holds the two equal.
"""
import sys
import os
import unittest

sys.path.insert(0, os.environ.get('HARVESTNET_PLATFORM_SOURCE', '.'))

from harvestnet_agents import cooler_failure_flow, scenario_runner
from harvestnet_agents.terms import terms_hash
from harvestnet_core import protocol
from harvestnet_platform import transport

SAMPLES = [
    {},
    {'version': 3, 'items': [{'produce_id': 'apples', 'pounds': 12.5}], 'names': {'market': 'Farmers market'}},
    {'b': 1, 'a': [True, None, 'ünïcode ☃', 0.1, -2]},
    [1, 2, 3],
]


class OneTermsHash(unittest.TestCase):
    def test_the_hash_is_prefixed_hex_of_canonical_json(self):
        digest = terms_hash({'b': 1, 'a': 2})
        self.assertRegex(digest, r'^sha256:[0-9a-f]{64}$')
        self.assertEqual(digest, terms_hash({'a': 2, 'b': 1}))  # key order never matters
        self.assertNotEqual(digest, terms_hash({'a': 2, 'b': 2}))

    def test_core_agents_and_platform_agree(self):
        for terms in SAMPLES:
            self.assertEqual(protocol.terms_hash(terms), terms_hash(terms))
            self.assertEqual(cooler_failure_flow.terms_hash(terms), terms_hash(terms))
            self.assertEqual(scenario_runner.terms_hash(terms), terms_hash(terms))
            self.assertEqual(transport.terms_hash(terms), terms_hash(terms), terms)

    def test_not_a_number_is_refused_not_hashed(self):
        with self.assertRaises(ValueError):
            terms_hash({'pounds': float('nan')})


if __name__ == '__main__':
    unittest.main()
