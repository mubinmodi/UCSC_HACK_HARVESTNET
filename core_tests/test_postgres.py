import os
import unittest
from harvestnet_core.records import Records
from harvestnet_core.engine import run_fixture
from test_core import fixture


@unittest.skipUnless(os.environ.get('HARVESTNET_TEST_DATABASE_URL'),'dedicated test Postgres not configured')
class PostgresTests(unittest.TestCase):
    def test_event_log_commitment_rollback_and_reconnect(self):
        url=os.environ['HARVESTNET_TEST_DATABASE_URL']
        records=Records(url)
        # CI provides a fresh dedicated database, never a production DSN.
        run=run_fixture(fixture(),records=records)
        self.assertTrue(run['commitments'])
        self.assertTrue(all(run['rule_checks'].values()))
        with self.assertRaises(ValueError):
            with records.transaction():
                records.put('rollback','probe',{'value':1})
                raise ValueError('rollback')
        self.assertEqual(records.all('rollback'),[])
        before=records.events(fixture()['surplus_offers'][0]['lot_id'])
        records.close()
        records=Records(url)
        self.assertEqual(records.events(fixture()['surplus_offers'][0]['lot_id']),before)
        records.close()
