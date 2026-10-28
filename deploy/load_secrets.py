"""Retrieve only allowed configuration from Secrets Manager, without logging it.

Besides the secret's own keys, the env file gets per-host values derived from two maps, so
compose can give each container only its own credential (deploy/aws/compose.aws.yaml):

- ``STAFF_TOKEN_<ORG>`` from ``HARVESTNET_STAFF_TOKENS`` (each food bank host's own core token);
- ``TRANSPORT_SIGNING_KEY_<SENDER>`` and ``TRANSPORT_VERIFY_KEYS_<HOST>`` from ``TRANSPORT_KEYS``
  (harvestnet_platform/transport_auth.py).

The env file stays root-only (0600) on the instance; compose reads it only to fill in each
service's own environment.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ALLOWED = {'API_EVENTS_TOKEN','DEMO_SWITCH_TOKEN','TRANSPORT_KEYS','HARVESTNET_APPROVALS_TOKEN',
           'CORE_API_TOKENS','CORE_API_TOKEN','APPROVAL_LINK_TTL_SECONDS','AGENT_TURN_TIMEOUT_SECONDS',
           'DIRECTORY_REFRESH_SECONDS','BEECEPTOR_BASE_URL','ANTHROPIC_API_KEY','CLAUDE_RUN_CAP_USD',
           'CLAUDE_TOTAL_CAP_USD','CORE_API_URL','APPROVAL_PUBLIC_URL','HARVESTNET_DOMAIN',
           'AGNTCY_DIRECTORY_ADDRESS','N8N_DECISION_WEBHOOK_URL','N8N_WEBHOOK_TOKEN',
           # deploy/aws: the core's per-organization staff tokens and browser origin, and the voice key.
           'HARVESTNET_STAFF_TOKENS','HARVESTNET_ALLOWED_ORIGIN','HARVESTNET_HOUSEHOLD_URL',
           'ELEVENLABS_API_KEY','N8N_APPROVAL_WEBHOOK_URL','N8N_PICKUP_WEBHOOK_URL',
           'N8N_RELEASE_WEBHOOK_URL','APPROVER_EMAILS_JSON','SES_SENDER_EMAIL',
           'SES_TEST_RECIPIENTS'}
# Retired settings an older secret may still hold: accepted, never written out.
# TRANSPORT_TOKEN was the one shared transport token; REPLY_BINDING_KEY, POSTGRES_PASSWORD and
# CORE_API_IMAGE belonged to the removed compose.deployment.yaml.
RETIRED = {'TRANSPORT_TOKEN','REPLY_BINDING_KEY','POSTGRES_PASSWORD','CORE_API_IMAGE'}


def _transport_auth():
    """harvestnet_platform.transport_auth from this release (stdlib only)."""
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    from harvestnet_platform import transport_auth
    return transport_auth


def derived(values):
    """Per-host values from the staff-token and transport-key maps (see the module docstring)."""
    out = {}
    if values.get('HARVESTNET_STAFF_TOKENS'):
        staff = json.loads(values['HARVESTNET_STAFF_TOKENS'])
        if not isinstance(staff,dict) or any(not isinstance(k,str) or not k.isidentifier() or not isinstance(v,str) for k,v in staff.items()):
            raise ValueError('HARVESTNET_STAFF_TOKENS must map organization IDs to tokens')
        out.update({f'STAFF_TOKEN_{org.upper()}': token for org, token in staff.items()})
    if values.get('TRANSPORT_KEYS'):
        keys = json.loads(values['TRANSPORT_KEYS'])
        out.update(_transport_auth().host_env(keys))
    return out


def env_file(values):
    if not isinstance(values,dict) or set(values)-ALLOWED-RETIRED:
        raise ValueError('Secret contains unknown configuration keys')
    values = {key: value for key, value in values.items() if key not in RETIRED}
    lines = []
    for key,value in {**values, **derived(values)}.items():
        if not isinstance(value,str) or any(c in value for c in '\r\n\x00'):
            raise ValueError('Configuration values must be single-line strings')
        # dotenv single quotes prevent Compose interpolation of $, #, and spaces.
        if "'" in value or '\\' in value:
            raise ValueError('Single quotes/backslashes are not supported in deployment values')
        lines.append(f"{key}='{value}'")
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--secret-id',required=True)
    parser.add_argument('--region',required=True)
    parser.add_argument('--output',default='runtime/deploy.env')
    args = parser.parse_args()
    import boto3
    # EC2 instance role supplies credentials; no AWS access keys in repository.
    value = boto3.client('secretsmanager',region_name=args.region).get_secret_value(SecretId=args.secret_id)
    content = env_file(json.loads(value['SecretString']))
    path = Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(descriptor,'w') as stream:
        stream.write(content)
    os.chmod(path,0o600)
    print('Deployment environment loaded from Secrets Manager; values are not logged.')


if __name__ == '__main__':
    main()
