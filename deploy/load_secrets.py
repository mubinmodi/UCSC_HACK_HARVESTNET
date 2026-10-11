"""Retrieve only allowed configuration from Secrets Manager, without logging it."""
import argparse
import json
import os
from pathlib import Path

ALLOWED = {'TRANSPORT_TOKEN','API_EVENTS_TOKEN','DEMO_SWITCH_TOKEN','POSTGRES_PASSWORD',
           'CORE_API_TOKEN','BEECEPTOR_BASE_URL','ANTHROPIC_API_KEY','CLAUDE_RUN_CAP_USD',
           'CLAUDE_TOTAL_CAP_USD','CORE_API_URL','APPROVAL_PUBLIC_URL','HARVESTNET_DOMAIN',
           'CORE_API_IMAGE','AGNTCY_DIRECTORY_ADDRESS','N8N_DECISION_WEBHOOK_URL','N8N_WEBHOOK_TOKEN'}


def env_file(values):
    if not isinstance(values,dict) or set(values)-ALLOWED:
        raise ValueError('Secret contains unknown configuration keys')
    lines = []
    for key,value in values.items():
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
