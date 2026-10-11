"""deploy/aws scripts: they parse, look before they create, tag what they create,
never print secrets, and --dry-run makes no change. No AWS account is used: a stub
`aws` on PATH answers read-only calls and records anything else as a mutation."""
import json
import os
import re
import shutil
import stat
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
AWS = ROOT / 'deploy' / 'aws'
SCRIPTS = ['lib.sh', 'setup.sh', 'teardown.sh', 'remote_deploy.sh', 'user-data.sh', 'logs.sh']
SECRET_ENV = {
    'ANTHROPIC_API_KEY': 'sk-ant-SENTINEL-anthropic',
    'ELEVENLABS_API_KEY': 'SENTINEL-elevenlabs',
    'N8N_WEBHOOK_TOKEN': 'SENTINEL-n8n-token',
    'CORE_API_TOKEN': 'SENTINEL-core-token',
    'DEMO_SWITCH_TOKEN': 'SENTINEL-demo-switch',
}
EXISTING_SECRET = {
    'TRANSPORT_TOKEN': 'SENTINEL-existing-transport', 'API_EVENTS_TOKEN': 'SENTINEL-existing-events',
    'DEMO_SWITCH_TOKEN': 'SENTINEL-existing-switch', 'CORE_API_URL': 'http://core:8000',
    'HARVESTNET_STAFF_TOKENS': json.dumps({'market': 'SENTINEL-existing-staff-market'}),
}
READ_ONLY = re.compile(r'^(describe|get|list|head)')

# A stand-in for the AWS CLI. Mode "fresh": nothing of ours exists. Mode "existing":
# everything exists. Mode "expired": credentials fail. Any non-read operation is a mutation.
STUB = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
while args and args[0] in ('--profile', '--region'):
    args = args[2:]
service, op = args[0], args[1]
query = args[args.index('--query') + 1] if '--query' in args else ''
mode = os.environ['STUB_MODE']
read_only = op.startswith(('describe', 'get', 'list', 'head'))
with open(os.environ['STUB_LOG'], 'a') as log:
    log.write(('READ ' if read_only else 'MUTATION ') + service + ' ' + op + '\n')
if not read_only:
    sys.exit(99)
def out(text):
    print(text)
    sys.exit(0)
def absent():
    sys.stderr.write('An error occurred (NotFound) when calling the operation: not found\n')
    sys.exit(254)
if service == 'sts':
    if mode == 'expired':
        sys.stderr.write('Error when retrieving token from sso: Token has expired\n')
        sys.exit(255)
    out('arn:aws:sts::649852688863:assumed-role/Test/test' if query == 'Arn' else '649852688863')
always = {
    ('ec2', 'describe-vpcs'): 'vpc-0test',
    ('ssm', 'get-parameter'): 'ami-0test',
    ('ec2', 'describe-images'): '/dev/sda1',
    ('ec2', 'describe-instance-type-offerings'): 'us-east-2a',
    ('ec2', 'describe-subnets'): 'subnet-0test',
    ('lambda', 'get-function-url-config'): 'https://skeleton.lambda-url.us-east-2.on.aws/',
    ('lambda', 'get-function'): 'harvestnet-api-skeleton',
}
if (service, op) in always:
    out(always[(service, op)])
if mode != 'existing':
    absent()
secret = os.environ['STUB_SECRET']
if (service, op) == ('ec2', 'describe-addresses'):
    if 'AssociationId' in query:
        out('eipalloc-0test\teipassoc-0test\t3.14.15.92')
    out('i-0test' if 'InstanceId' in query else 'eipalloc-0test\t3.14.15.92')
if (service, op) == ('ec2', 'describe-security-groups'):
    if 'length(' in query:
        out('1')
    out('' if 'FromPort!=' in query else 'sg-0test')
if (service, op) == ('ec2', 'describe-instances'):
    out('i-0test\trunning\tt4g.micro' if 'State.Name' in query else 'i-0test')
if (service, op) == ('secretsmanager', 'describe-secret'):
    out('arn:aws:secretsmanager:us-east-2:649852688863:secret:harvestnet/platform-AbCdEf\tNone' if 'ARN' in query else 'harvestnet/platform')
if (service, op) == ('secretsmanager', 'get-secret-value'):
    out(secret)
answers = {
    ('budgets', 'describe-budget'): 'harvestnet-monthly' if 'BudgetName' in query else '15.0',
    ('budgets', 'describe-notifications-for-budget'): '50.0\t80.0\t100.0',
    ('budgets', 'describe-subscribers-for-notification'): 'alerts@example.invalid',
    ('s3api', 'head-bucket'): '',
    ('iam', 'get-role'): 'harvestnet-ec2-role',
    ('iam', 'list-attached-role-policies'): 'arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore',
    ('iam', 'get-role-policy'): '{"Version": "2012-10-17", "Statement": []}',
    ('iam', 'get-instance-profile'): 'harvestnet-ec2-role' if 'Roles' in query else 'harvestnet-ec2-profile',
    ('iam', 'list-role-policies'): '',
    ('logs', 'describe-log-groups'): '/aws/lambda/harvestnet-api-skeleton',
}
if (service, op) in answers:
    out(answers[(service, op)])
absent()
'''


def function_bodies(text):
    """Map each top-level shell function name to its lines (heredoc-safe enough for these scripts)."""
    bodies, current = {}, None
    for line in text.splitlines():
        start = re.match(r'^([a-z_]+)\(\) \{', line)
        if start:
            current = start.group(1)
            bodies[current] = []
        elif current:
            bodies[current].append(line)
    return bodies


def commands(lines):
    """Join backslash-continued lines into whole commands."""
    joined, buffer = [], ''
    for line in lines:
        buffer += line.rstrip('\\').rstrip() + ' ' if line.rstrip().endswith('\\') else line
        if not line.rstrip().endswith('\\'):
            joined.append(buffer)
            buffer = ''
    return joined


class AwsScriptsParse(unittest.TestCase):
    def test_bash_parses_every_script(self):
        for name in SCRIPTS:
            result = subprocess.run(['bash', '-n', str(AWS / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f'{name}: {result.stderr}')

    @unittest.skipUnless(shutil.which('shellcheck'), 'shellcheck not installed')
    def test_shellcheck(self):
        result = subprocess.run(['shellcheck', '-x', '-S', 'warning', *[str(AWS / n) for n in SCRIPTS]],
                                capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_entry_scripts_are_executable(self):
        for name in ('setup.sh', 'teardown.sh', 'remote_deploy.sh', 'logs.sh'):
            self.assertTrue((AWS / name).stat().st_mode & stat.S_IXUSR, name)


class AwsScriptsStructure(unittest.TestCase):
    setup = (AWS / 'setup.sh').read_text()
    teardown = (AWS / 'teardown.sh').read_text()

    def test_every_create_is_preceded_by_a_lookup(self):
        for name, body in function_bodies(self.setup).items():
            for i, line in enumerate(body):
                if re.search(r'aws_rw(_global)? \S+ (create-|allocate-address|run-instances)', line):
                    before = '\n'.join(body[:i])
                    self.assertRegex(before, r'\b(lookup|lookup_global|aws_ro)\b',
                                     f'{name}: creates without looking first: {line.strip()}')

    def test_every_created_resource_is_tagged(self):
        not_resources = {'create-notification', 'create-subscriber'}  # parts of the budget
        tagged_later = {'create-bucket': 'put-bucket-tagging'}
        for name, body in function_bodies(self.setup).items():
            text = '\n'.join(body)
            for command in commands(body):
                found = re.search(r'aws_rw(?:_global)? \S+ (create-[a-z-]+|allocate-address|run-instances)', command)
                if not found or found.group(1) in not_resources:
                    continue
                verb = found.group(1)
                if verb in tagged_later:
                    self.assertIn(tagged_later[verb], text, f'{name}: {verb} is never tagged')
                else:
                    self.assertRegex(command, r'tag_spec|tags_kv', f'{name}: {verb} has no project tag')

    def test_all_aws_calls_go_through_the_helpers(self):
        for script in (self.setup, self.teardown, (AWS / 'logs.sh').read_text()):
            for line in script.splitlines():
                if line.lstrip().startswith('#'):
                    continue
                self.assertNotRegex(line, r'(^\s*|\$\(\s*|\|\s*)aws\s', f'raw aws call: {line.strip()}')

    def test_never_traces_or_prints_secret_variables(self):
        secret_vars = r'\$\{?(ANTHROPIC_API_KEY|ELEVENLABS_API_KEY|N8N_WEBHOOK_TOKEN|CORE_API_TOKEN|DEMO_SWITCH_TOKEN|GEN_TOKENS|generated|old_json_content)\b'
        for name in SCRIPTS:
            text = (AWS / name).read_text()
            self.assertNotRegex(text, r'set -[a-z]*x|set -o xtrace', f'{name} enables tracing')
            for line in text.splitlines():
                if re.search(secret_vars, line):
                    self.assertIn('GEN_TOKENS="$generated" jq', line, f'{name}: secret variable used in: {line.strip()}')
                if re.search(r'\b(echo|printf|info|warn|die|aws_rw|aws_rw_global)\b', line):
                    self.assertNotRegex(line, secret_vars, f'{name}: may print a secret: {line.strip()}')

    def test_secret_goes_to_aws_only_through_a_private_file(self):
        self.assertIn('--secret-string "file://$TMP_DIR/secret.json"', self.setup)
        self.assertIn('chmod 700 "$TMP_DIR"', (AWS / 'lib.sh').read_text())

    def test_instance_has_no_ssh_and_no_github_token(self):
        self.assertNotIn('FromPort=22', self.setup)
        for name in ('setup.sh', 'user-data.sh', 'remote_deploy.sh'):
            self.assertNotRegex((AWS / name).read_text(), r'GITHUB_TOKEN|GH_TOKEN|git clone', name)
        self.assertIn('HttpTokens=required', self.setup)

    def test_frontend_routes_serve_each_app_under_its_own_path(self):
        result = subprocess.run(['bash', '-c', 'RELEASE=test; source deploy/aws/setup.sh; frontend_routes results-strip household'],
                                capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('handle /results-strip/* {', result.stdout)
        self.assertIn('try_files {path} /household/index.html', result.stdout)
        self.assertIn('respond "Frontend apps: /results-strip/ /household/ " 200', result.stdout)


class AwsDryRun(unittest.TestCase):
    """setup.sh and teardown.sh --dry-run against the stub: no mutation, no secret in the output."""

    def run_script(self, mode, *args, env=None):
        with TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / 'bin'
            bin_dir.mkdir()
            stub = bin_dir / 'aws'
            stub.write_text(STUB)
            stub.chmod(0o755)
            log = Path(tmp) / 'aws.log'
            log.touch()
            run_env = {'PATH': f'{bin_dir}{os.pathsep}{os.environ["PATH"]}', 'HOME': tmp, 'TMPDIR': tmp,
                       'STUB_MODE': mode, 'STUB_LOG': str(log), 'STUB_SECRET': json.dumps(EXISTING_SECRET),
                       'NO_FETCH': '1', 'GIT_REF': 'HEAD', 'ALERT_EMAIL': 'alerts@example.invalid', **SECRET_ENV,
                       **(env or {})}
            result = subprocess.run(['bash', *args], capture_output=True, text=True, cwd=ROOT, env=run_env, timeout=120)
            return result, log.read_text().splitlines()

    def assert_safe(self, result, calls):
        output = result.stdout + result.stderr
        self.assertEqual([c for c in calls if c.startswith('MUTATION')], [], 'dry run ran a mutating AWS call')
        self.assertNotIn('SENTINEL', output, 'a secret value was printed')
        self.assertIsNone(re.search(r'\b[0-9a-f]{64}\b', output), 'a generated token was printed')

    def head_has_this_setup(self):
        probe = subprocess.run(['git', 'cat-file', '-e', 'HEAD:deploy/aws/remote_deploy.sh'], cwd=ROOT)
        if probe.returncode != 0:
            self.skipTest('HEAD does not contain deploy/aws yet (uncommitted)')

    def test_setup_dry_run_on_an_empty_account(self):
        self.head_has_this_setup()
        result, calls = self.run_script('fresh', 'deploy/aws/setup.sh', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_safe(result, calls)
        for planned in ('budgets create-budget', 's3api create-bucket', 'ec2 allocate-address',
                        'secretsmanager create-secret', 'iam create-role', 'ec2 create-security-group',
                        'ec2 run-instances', 'ssm send-command', 'Monthly cost ESTIMATE'):
            self.assertIn(planned, result.stdout + result.stderr)
        self.assertTrue(all(READ_ONLY.match(c.split()[2]) for c in calls))

    def test_setup_dry_run_when_everything_exists_updates_instead_of_creating(self):
        self.head_has_this_setup()
        result, calls = self.run_script('existing', 'deploy/aws/setup.sh', '--dry-run')
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assert_safe(result, calls)
        for created in ('create-budget', 'create-bucket', 'allocate-address', 'create-secret', 'create-role',
                        'create-instance-profile', 'create-security-group', 'run-instances', 'associate-address'):
            self.assertNotIn(f' {created} ', output)
        self.assertIn('updating keys:', output)
        self.assertIn('ssm send-command', output)

    def test_setup_requires_alert_email(self):
        result, calls = self.run_script('fresh', 'deploy/aws/setup.sh', '--dry-run', env={'ALERT_EMAIL': ''})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ALERT_EMAIL', result.stderr)

    def test_expired_credentials_point_to_aws_login(self):
        for script in ('deploy/aws/setup.sh', 'deploy/aws/teardown.sh'):
            result, calls = self.run_script('expired', script, '--dry-run')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('aws login --profile incubator', result.stderr)

    def test_secret_merge_keeps_tokens_adds_missing_ones_and_only_allowed_keys(self):
        self.head_has_this_setup()
        with TemporaryDirectory() as out:
            script = ('source deploy/aws/setup.sh; DRY_RUN=1; SHA=$(git rev-parse HEAD); DOMAIN=3-14-15-92.sslip.io; '
                      f'TMP_DIR={out}; ACCOUNT_ID=649852688863; setup_secret')
            result, calls = self.run_script('existing', '-c', script, env={'CLAUDE_RUN_CAP_USD': '2', 'CLAUDE_TOTAL_CAP_USD': '5'})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assert_safe(result, calls)
            merged = json.loads((Path(out) / 'secret.json').read_text())
        self.assertEqual(merged['TRANSPORT_TOKEN'], EXISTING_SECRET['TRANSPORT_TOKEN'])
        self.assertEqual(merged['API_EVENTS_TOKEN'], EXISTING_SECRET['API_EVENTS_TOKEN'])
        self.assertEqual(merged['DEMO_SWITCH_TOKEN'], SECRET_ENV['DEMO_SWITCH_TOKEN'])
        self.assertEqual(merged['ANTHROPIC_API_KEY'], SECRET_ENV['ANTHROPIC_API_KEY'])
        staff = json.loads(merged['HARVESTNET_STAFF_TOKENS'])
        self.assertEqual(staff['market'], 'SENTINEL-existing-staff-market')
        self.assertEqual(set(staff), {'market', 'city', 'rural', 'eastside', 'advocate'})
        self.assertEqual(len(set(staff.values())), 5)
        for org in ('city', 'rural', 'eastside', 'advocate'):
            self.assertRegex(staff[org], r'^[0-9a-f]{64}$')
        self.assertEqual(merged['HARVESTNET_ALLOWED_ORIGIN'], 'https://3-14-15-92.sslip.io')
        self.assertEqual((merged['CLAUDE_RUN_CAP_USD'], merged['CLAUDE_TOTAL_CAP_USD']), ('2', '5'))
        import importlib.util
        spec = importlib.util.spec_from_file_location('load_secrets', ROOT / 'deploy' / 'load_secrets.py')
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)
        self.assertLessEqual(set(merged), loader.ALLOWED, 'the instance loader would reject these keys')
        loader.env_file(merged)  # every value is one the loader accepts

    def test_teardown_dry_run_lists_deletes_and_keeps_the_skeleton(self):
        result, calls = self.run_script('existing', 'deploy/aws/teardown.sh', '--dry-run')
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assert_safe(result, calls)
        for planned in ('ec2 terminate-instances', 'ec2 release-address', 'ec2 delete-security-group',
                        'iam delete-instance-profile', 'iam delete-role --role-name harvestnet-ec2-role',
                        's3api delete-bucket', 'secretsmanager delete-secret', 'budgets delete-budget'):
            self.assertIn(planned, output)
        self.assertNotIn('lambda delete-function', output)
        self.assertNotIn('harvestnet-api-skeleton-role', output.split('Find HarvestNet resources')[1].split('skeleton Lambda')[0])

    def test_teardown_include_skeleton(self):
        result, calls = self.run_script('existing', 'deploy/aws/teardown.sh', '--dry-run', '--include-skeleton')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('lambda delete-function --function-name harvestnet-api-skeleton', result.stderr)


@unittest.skipUnless(shutil.which('docker') and subprocess.run(['docker', 'compose', 'version'],
                     capture_output=True).returncode == 0, 'docker compose not available')
class AwsComposeConfig(unittest.TestCase):
    def test_compose_files_merge(self):
        env = {'PATH': os.environ['PATH'], 'HOME': os.environ.get('HOME', '/tmp'), 'HARVESTNET_RELEASE': 'test',
               'TRANSPORT_TOKEN': 'x', 'API_EVENTS_TOKEN': 'x', 'DEMO_SWITCH_TOKEN': 'x',
               'APPROVAL_PUBLIC_URL': 'https://example.invalid', 'HARVESTNET_ALLOWED_ORIGIN': 'https://example.invalid',
               'HARVESTNET_STAFF_TOKENS': '{"market":"x"}', 'HARVESTNET_DOMAIN': 'example.invalid'}
        result = subprocess.run(['docker', 'compose', '-p', 'harvestnet', '-f', 'compose.platform.yaml',
                                 '-f', 'deploy/aws/compose.aws.yaml', 'config', '--format', 'json'],
                                capture_output=True, text=True, cwd=ROOT, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)['services']
        self.assertEqual(set(services), {'donor', 'city', 'rural', 'eastside', 'advocate', 'systems', 'approvals', 'core', 'gateway'})
        self.assertEqual(services['core']['environment']['HOST'], '0.0.0.0')
        self.assertEqual(services['donor']['environment']['AGENT_POLICY'], 'harvestnet_core.join_adapter:policy')
        self.assertEqual([p['published'] for p in services['gateway']['ports']], ['80', '443'])
        for name, service in services.items():
            if name != 'gateway':
                self.assertNotIn('ports', service, f'{name} must stay private')


if __name__ == '__main__':
    unittest.main()
