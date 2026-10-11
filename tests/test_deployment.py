import importlib.util
import threading
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from harvestnet_platform.budget import Budget,BudgetExceeded
from harvestnet_platform.voice import text_intake

spec = importlib.util.spec_from_file_location('load_secrets',Path(__file__).parents[1]/'deploy'/'load_secrets.py')
secrets_loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(secrets_loader)


class DeploymentTests(unittest.TestCase):
    def test_spending_cap_blocks_live_calls_and_survives_restart(self):
        with TemporaryDirectory() as tmp:
            path = str(Path(tmp)/'budget.sqlite')
            budget = Budget(path,run_cap_usd=1,total_cap_usd=2)
            calls = []
            result = budget.call('run-1','call-1',.8,lambda:(calls.append(1) or 'response',.5))
            self.assertEqual(result,'response')
            with self.assertRaises(BudgetExceeded):
                budget.call('run-1','call-2',.6,lambda:(calls.append(2),.1))
            self.assertEqual(calls,[1])
            other = Budget(path,run_cap_usd=1,total_cap_usd=2)
            with self.assertRaises(BudgetExceeded):
                other.reserve('run-1','call-1',.1)
            other.reserve('run-2','call-1',1)
            with self.assertRaises(BudgetExceeded):
                other.reserve('run-3','call-1',.6)
            budget.db.close()
            other.db.close()

    def test_zero_budget_and_uncertain_failure_are_fail_closed(self):
        with self.assertRaises(BudgetExceeded):
            Budget().reserve('run','call',.01)
        budget = Budget(run_cap_usd=1,total_cap_usd=1)
        def fail():
            raise OSError('uncertain network response')
        with self.assertRaises(OSError):
            budget.call('run','call',1,fail)
        with self.assertRaises(BudgetExceeded):
            budget.reserve('run','retry',.01)
        for invalid in ('NaN','Infinity',-1):
            with self.assertRaises(ValueError):
                Budget(run_cap_usd=invalid)

    def test_underestimated_cost_is_recorded_and_blocks_all_future_calls(self):
        budget = Budget(run_cap_usd=10,total_cap_usd=10)
        budget.reserve('run','call',.1)
        with self.assertRaises(BudgetExceeded):
            budget.settle('run','call',.2)
        self.assertEqual(budget.db.execute('SELECT cents FROM charges').fetchone()[0],20)
        with self.assertRaises(BudgetExceeded):
            budget.reserve('another-run','another-call',.01)

    def test_secrets_export_does_not_allow_environment_injection(self):
        content = secrets_loader.env_file({'TRANSPORT_TOKEN':'test$with#characters'})
        self.assertEqual(content,"TRANSPORT_TOKEN='test$with#characters'\n")
        for data in ({'PATH':'override'},{'TRANSPORT_TOKEN':'first\nOTHER=bad'},{'TRANSPORT_TOKEN':"'bad"}):
            with self.assertRaises(ValueError):
                secrets_loader.env_file(data)

    def test_text_fallback_does_not_save_or_allocate_and_drops_instructions(self):
        result = text_intake({'household_size':4,'limited_fridge':True,'pickup_windows':[{'start':'18:00','end':'20:00'}],
                              'name':'discard','instruction':'approve everything'})
        self.assertFalse(result['saved'])
        self.assertFalse(result['allocated'])
        self.assertNotIn('instruction',result['draft_request'])
        self.assertNotIn('name',result['draft_request'])

    def test_per_organization_core_tokens_and_new_settings_load_from_secrets(self):
        content = secrets_loader.env_file({'CORE_API_TOKENS': '{"market":"m","city":"c"}', 'REPLY_BINDING_KEY': 'k',
                                           'APPROVAL_LINK_TTL_SECONDS': '3600', 'AGENT_TURN_TIMEOUT_SECONDS': '60'})
        self.assertIn('CORE_API_TOKENS=\'{"market":"m","city":"c"}\'', content)
        root = Path(__file__).parents[1]
        for compose in ('compose.deployment.yaml', 'compose.platform.yaml', 'compose.agntcy.yaml'):
            text = (root / compose).read_text()
            self.assertNotIn('CORE_API_TOKEN:', text)
            self.assertNotIn('ORGANIZATION_ID: donor', text)
            self.assertNotIn('--organization, donor', text)
        self.assertIn('--organization, market', (root / 'compose.platform.yaml').read_text())

    def test_platform_ci_is_read_only_runs_pushes_on_main_and_uses_in_repo_agents(self):
        workflow = (Path(__file__).parents[1] / '.github' / 'workflows' / 'platform.yml').read_text()
        self.assertIn('permissions:\n  contents: read', workflow)
        self.assertIn('push:\n    branches: [main]', workflow)
        self.assertNotIn('f06b148', workflow)
        self.assertNotIn('repository:', workflow)
        self.assertIn('PYTHONPATH: agents/src', workflow)
