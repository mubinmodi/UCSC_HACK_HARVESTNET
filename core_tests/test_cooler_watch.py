"""#23 deployed trigger: a food bank's own watcher proposes after its cooler reading fails.

Real local HTTP servers for the core, Lane C's systems service (with its demo switch) and
Lane C's approval bridge, as in test_cooler_failure_join. No network beyond 127.0.0.1, no paid
APIs. The watcher polls once per ``tick()`` here instead of on a timer. All data is synthetic.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import URLError

from harvestnet_core import changes

import test_cooler_failure_join as join_test
from test_cooler_failure_join import DEMO, EVENTS, LOT, TOKENS, call


@unittest.skipUnless(os.environ.get('HARVESTNET_PLATFORM_SOURCE'), 'pinned platform package not configured')
class CoolerWatch(unittest.TestCase):
    # The join test's real servers, reused as they are.
    serve = join_test.CoolerFailureJoin.serve
    flip_switch = join_test.CoolerFailureJoin.flip_switch
    human = join_test.CoolerFailureJoin.human

    def tearDown(self):
        join_test.CoolerFailureJoin.tearDown(self)
        self.tmp.cleanup()

    def watcher(self, organization='city', state=True):
        from harvestnet_core.cooler_watch import CoolerWatcher
        if not hasattr(self, 'tmp'):
            self.tmp = tempfile.TemporaryDirectory()
        return CoolerWatcher(food_bank_id=organization, systems_url=self.systems_url, core_url=self.core_url,
                             approvals_url=self.approvals_url, core_token=TOKENS[organization], events_token=EVENTS,
                             directory=self.directory, state_path=Path(self.tmp.name) / f'{organization}.json' if state else None)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        join_test.CoolerFailureJoin.setUp(self)
        self.issued = []
        real = self.join.request_approvals

        self.outage = False

        def spy(approvals_url, token, approval_request):
            if self.outage:
                raise URLError('approvals down')
            result = real(approvals_url, token, approval_request)
            self.issued.append((approval_request, result))
            return result
        patcher = mock.patch.object(self.join, 'request_approvals', side_effect=spy)
        self.request = patcher.start()
        self.addCleanup(patcher.stop)

    def set_switch(self, failed):
        status, _ = call('POST', self.systems_url + '/demo/city/cooler', {'failed': failed}, DEMO)
        self.assertEqual(status, 200)

    def proposals(self):
        return changes.changes_for(self.engine.records, LOT)

    def test_working_cooler_does_nothing(self):
        watcher = self.watcher()
        self.assertEqual(watcher.tick()['status'], 'working')
        self.assertEqual(self.proposals(), [])
        self.request.assert_not_called()
        self.assertIsNone(self.engine.records.get('bank', 'city').get('cooler'))

    def test_failure_proposes_once_and_requests_review_emails_without_committing(self):
        watcher = self.watcher()
        self.flip_switch()
        result = watcher.tick()
        self.assertEqual((result['status'], result['synthetic']), ('failed', True))
        self.assertEqual(result['lots'][LOT]['status'], 'requested')
        [change] = self.proposals()
        self.assertEqual((change['version'], change['status'], change['proposer_id']), (self.new, 'awaiting_approvals', 'city'))
        self.assertEqual(sorted(change['organizations']), ['city', 'eastside'])
        self.assertEqual(self.engine.records.get('bank', 'city')['cooler']['status'], 'failed')
        # The approval bridge got exactly this version's request and issued a link per organization.
        self.request.assert_called_once()
        [(sent, issued)] = self.issued
        self.assertEqual((sent['lot_id'], sent['version'], sorted(sent['organizations'])), (LOT, self.new, ['city', 'eastside']))
        self.assertEqual(sorted(r['organization_id'] for r in issued['requests']), ['city', 'eastside'])
        # Never auto-commits: the plan is still on the committed version and nobody has decided.
        lot = self.engine.records.get('lot', LOT)
        self.assertNotIn('change_version', lot)
        self.assertEqual(change['approvals'], {})
        # The review links are the humans' capabilities: not returned, not kept.
        kept = json.dumps(result) + Path(self.tmp.name, 'city.json').read_text()
        self.assertNotIn('token=', kept)
        self.assertNotIn('decision_url', kept)

    def test_repeated_polls_and_restarts_do_not_propose_again(self):
        watcher = self.watcher()
        self.flip_switch()
        watcher.tick()
        for _ in range(3):
            self.assertEqual(watcher.tick()['lots'][LOT]['status'], 'requested')
        # A restart in the middle of the same failure reads the saved episode.
        self.assertEqual(self.watcher().tick()['lots'][LOT]['status'], 'requested')
        self.assertEqual(len(self.proposals()), 1)
        self.request.assert_called_once()

    def test_lost_state_cannot_duplicate_the_proposal_or_the_emails(self):
        self.flip_switch()
        self.watcher().tick()
        result = self.watcher(state=False).tick()  # a fresh watcher with no saved episode
        self.assertEqual(result['lots'][LOT]['status'], 'conflict')  # the core refuses a second awaiting change
        self.assertEqual(len(self.proposals()), 1)
        self.request.assert_called_once()

    def test_reset_to_working_closes_the_episode_and_a_new_failure_can_propose_again(self):
        watcher = self.watcher()
        self.flip_switch()
        watcher.tick()
        self.set_switch(False)
        self.assertEqual(watcher.tick()['status'], 'recovered')
        self.assertEqual(self.engine.records.get('bank', 'city')['cooler']['status'], 'working')
        self.assertEqual(watcher.tick()['status'], 'working')
        # Failing again while the first change still awaits approvals: the core refuses a second.
        self.set_switch(True)
        self.assertEqual(watcher.tick()['lots'][LOT]['status'], 'conflict')
        self.assertEqual(len(self.proposals()), 1)
        # Both humans approve the first change; it commits as the new committed version.
        links = {link['organization_id']: link for link in self.issued[0][1]['requests']}
        self.human(links['eastside'], 'approve', '2026-10-13T15:35:00-07:00')
        status, decided = self.human(links['city'], 'approve', '2026-10-13T15:40:00-07:00')
        self.assertTrue(decided['committed'])
        committed = self.engine.records.get('lot', LOT)['change_version']
        self.assertEqual(committed, self.new)
        # Reset and fail once more: a new episode runs against the new committed version.
        self.set_switch(False)
        self.assertEqual(watcher.tick()['status'], 'recovered')
        self.set_switch(True)
        result = watcher.tick()
        self.assertEqual(result['status'], 'failed')
        entry = result['lots'][LOT]
        if entry['status'] == 'requested':
            self.assertEqual(entry['version'], committed + 1)
            self.assertEqual(len(self.proposals()), 2)
            self.assertEqual(self.request.call_count, 2)
        else:  # nothing left that a new version could move: no proposal, nothing duplicated
            self.assertIn(entry['status'], ('nothing_held', 'no_change', 'conflict'))
            self.assertEqual(len(self.proposals()), 1)

    def test_approval_bridge_outage_is_retried_without_proposing_again(self):
        watcher = self.watcher()
        self.flip_switch()
        self.outage = True
        result = watcher.tick()
        self.assertEqual(result['lots'][LOT]['status'], 'proposed')
        self.assertEqual(len(self.proposals()), 1)
        self.assertEqual(self.issued, [])
        self.outage = False
        self.assertEqual(watcher.tick()['lots'][LOT]['status'], 'requested')
        self.assertEqual(len(self.proposals()), 1)
        self.assertEqual(len(self.issued), 1)

    def test_a_food_bank_with_nothing_cold_to_move_proposes_nothing(self):
        # Rural holds no cold-dependent produce of the committed lot: its cooler failing proposes no change.
        watcher = self.watcher('rural')
        self.assertEqual(watcher.tick()['status'], 'working')
        call('POST', self.systems_url + '/demo/rural/cooler', {'failed': True}, DEMO)
        result = watcher.tick()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual({e['status'] for e in result['lots'].values()} - {'no_change', 'nothing_held'}, set())
        self.assertEqual(self.proposals(), [])
        self.request.assert_not_called()

    def test_only_the_failing_food_banks_own_watcher_acts(self):
        # City's cooler fails; the other food banks' watchers see their own working coolers and do nothing.
        self.flip_switch()
        for other in ('rural', 'eastside'):
            self.assertEqual(self.watcher(other).tick()['status'], 'working')
        self.assertEqual(self.proposals(), [])
        self.request.assert_not_called()


    def test_a_declined_version_is_not_proposed_again_with_links_nobody_can_use(self):
        watcher = self.watcher()
        self.flip_switch()
        watcher.tick()
        links = {link['organization_id']: link for link in self.issued[0][1]['requests']}
        status, decided = self.human(links['eastside'], 'decline', '2026-10-13T15:35:00-07:00')
        self.assertEqual((status, decided['change_status']), (200, 'declined'))
        self.set_switch(False)
        self.assertEqual(watcher.tick()['status'], 'recovered')
        self.set_switch(True)
        self.assertEqual(watcher.tick()['lots'][LOT]['status'], 'declined_earlier')
        self.assertEqual([(c['version'], c['status']) for c in self.proposals()], [(self.new, 'declined')])
        self.request.assert_called_once()


class WatcherFromEnv(unittest.TestCase):
    def test_a_host_starts_its_watcher_only_when_asked(self):
        import sys
        sys.path.insert(0, os.environ.get('HARVESTNET_PLATFORM_SOURCE', '.'))
        from harvestnet_platform import transport
        # Test placeholder: a host refuses to start without its own verification keys.
        keys = {'TRANSPORT_VERIFY_KEYS': json.dumps({'core': '0' * 64})}
        with mock.patch.dict(os.environ, {'TRANSPORT_VERIFY_KEYS': ''}), \
                mock.patch.object(sys, 'argv', ['transport', '--organization', 'city']), \
                mock.patch.object(transport, 'serve') as serve, self.assertRaises(ValueError):
            transport.main()
        for env, started in (({'COOLER_WATCH': '1'}, True), ({}, False), ({'COOLER_WATCH': '0'}, False)):
            with self.subTest(env=env), mock.patch.dict(os.environ, {**env, **keys}), \
                    mock.patch.object(sys, 'argv', ['transport', '--organization', 'city']), \
                    mock.patch.object(transport, 'serve') as serve, \
                    mock.patch('harvestnet_core.cooler_watch.start_from_env') as start:
                if not env:
                    os.environ.pop('COOLER_WATCH', None)
                transport.main()
                serve.assert_called_once()
                self.assertEqual(start.call_args_list, [mock.call('city')] if started else [])


    ENV = {'HARVESTNET_STAFF_TOKENS': json.dumps({'city': 'city-own', 'rural': 'rural-own'}), 'API_EVENTS_TOKEN': 'events',
           'SYSTEMS_URL': 'http://systems:8010', 'COOLER_WATCH_STATE': '/nonexistent/state.json'}

    def setUp(self):
        import sys
        sys.path.insert(0, os.environ.get('HARVESTNET_PLATFORM_SOURCE', '.'))

    def test_keeps_only_its_own_organizations_core_token(self):
        from harvestnet_core.cooler_watch import watcher_from_env
        watcher = watcher_from_env('city', self.ENV)
        self.assertEqual((watcher.food_bank_id, watcher.core_token, watcher.events_token), ('city', 'city-own', 'events'))
        self.assertEqual((watcher.core_url, watcher.approvals_url), ('http://core:8000', 'http://approvals:8030'))
        self.assertNotIn('rural-own', repr(vars(watcher)))

    def test_the_deployed_host_gets_only_its_own_single_token(self):
        from harvestnet_core.cooler_watch import watcher_from_env
        env = {k: v for k, v in self.ENV.items() if k != 'HARVESTNET_STAFF_TOKENS'}
        watcher = watcher_from_env('rural', {**env, 'HARVESTNET_STAFF_TOKEN': 'rural-own'})
        self.assertEqual(watcher.core_token, 'rural-own')
        self.assertIsNone(watcher_from_env('rural', env))

    def test_fallback_directory_reports_the_mode_of_whichever_answered(self):
        from harvestnet_core.cooler_watch import FallbackDirectory

        class Primary:
            mode, down = 'agntcy_directory', False

            def search(self, **query):
                if self.down:
                    raise ConnectionError('directory down')
                return {'mode': self.mode, 'records': []}

        class Local:
            mode = 'local_directory_fallback'

            def search(self, **query):
                return {'mode': self.mode, 'records': []}

        primary = Primary()
        directory = FallbackDirectory(primary, Local())
        self.assertEqual(directory.mode, 'agntcy_directory')
        primary.down = True
        self.assertEqual(directory.search()['agntcy_unreachable'], 'ConnectionError')
        self.assertEqual(directory.mode, 'local_directory_fallback')
        primary.down = False
        directory.search()
        self.assertEqual(directory.mode, 'agntcy_directory')

    def test_not_started_without_its_configuration_or_for_a_non_food_bank(self):
        from harvestnet_core.cooler_watch import watcher_from_env
        self.assertIsNone(watcher_from_env('market', self.ENV))
        self.assertIsNone(watcher_from_env('eastside', self.ENV))  # no core token for eastside in the map
        for missing in ('HARVESTNET_STAFF_TOKENS', 'API_EVENTS_TOKEN', 'SYSTEMS_URL'):
            self.assertIsNone(watcher_from_env('city', {k: v for k, v in self.ENV.items() if k != missing}))


if __name__ == '__main__':
    unittest.main()

