import copy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from harvestnet_core.api import API
from harvestnet_core.calculators import Calculators
from harvestnet_core.engine import Engine,run_fixture
from harvestnet_core.protocol import Conflict,dt,terms_hash,named
from harvestnet_core.records import Records
from harvestnet_core.checks import rule_checks
from harvestnet_agents.calculators import HouseholdBalance,StandInCalculators
from harvestnet_agents.negotiation import StorageSlot,TimeWindow


from test_core import fixture

class VoiceJoinTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture(); self.e=Engine(self.f)
        self.now='2026-10-13T12:00:00-07:00'
        self.api=API(self.e,clock=lambda:self.now,staff_tokens={'market':'donor-test','city':'city-test'})
        self.form={k:self.f['requests'][0][k] for k in ('household_size','pickup_windows','limited_fridge','neighborhood','cant_eat','snap','language')}


    def test_voice_replay_creates_same_share_only_after_consent(self):
        data=json.loads(Path('agents/tests/fixtures/front_desk/en_complete.json').read_text())
        api=API(self.e,clock=lambda:self.now,extractor=lambda transcript:data['extractor_output'])
        status,r=api.call('POST','/voice-intake',{'transcript':data['transcript'],'call_id':'recorded'})
        self.assertEqual(status,200); self.assertTrue(r['complete']); self.assertFalse(r['saved'])
        self.assertEqual(r['fair_share_lb'],12)
        status,saved=api.call('POST','/requests',{**r['draft_request'],'consent':True,'channel':'voice'})
        self.assertEqual(status,201); self.assertEqual(saved['fair_share_lb'],12)
        self.assertEqual(self.api.call('POST','/voice-intake',{})[0],503)


