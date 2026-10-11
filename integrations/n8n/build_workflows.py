"""Generate importable, inactive n8n workflows without credentials or decisions.

Credential placeholders are linked by the operator after import: they are referenced by
name only, and no secret is in any JSON file. No workflow has an approve operation; human
callbacks go through the exact-terms review page.

Messages go by email (user decision, October 11, 2026): n8n's Send Email node over SMTP,
with Amazon SES SMTP credentials configured in n8n Cloud. No workflow uses SMS.
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent
TYPE_VERSIONS = {'n8n-nodes-base.webhook': 2, 'n8n-nodes-base.httpRequest': 4.2,
                 'n8n-nodes-base.respondToWebhook': 1.4, 'n8n-nodes-base.emailSend': 2.1, 'n8n-nodes-base.code': 2}
# The one n8n SMTP credential every email workflow uses. Create it in n8n Cloud;
# neither generated workflow JSON nor the EC2 deployment contains its password.
SMTP_CREDENTIAL = {'smtp': {'id': 'CONFIGURE_IN_N8N', 'name': 'HarvestNet Amazon SES SMTP'}}


def node(name, kind, parameters, x, credentials=None):
    result = {'id': name.lower().replace(' ', '-'), 'name': name, 'type': kind,
              'typeVersion': TYPE_VERSIONS.get(kind, 1), 'position': [x,0], 'parameters': parameters}
    if credentials:
        result['credentials'] = credentials
    return result


def workflow(name, nodes):
    connections = {a['name']: {'main': [[{'node':b['name'],'type':'main','index':0}]]} for a,b in zip(nodes,nodes[1:])}
    return {'name':name,'nodes':nodes,'connections':connections,'active':False,
            'settings':{'executionOrder':'v1','saveDataSuccessExecution':'none','saveDataErrorExecution':'none'},
            'pinData':{}, 'tags':[]}


def webhook(path):
    return node('Authenticated event','n8n-nodes-base.webhook',
                {'httpMethod':'POST','path':path,'authentication':'headerAuth','responseMode':'responseNode','options':{}},0,
                {'httpHeaderAuth': {'id':'CONFIGURE_IN_N8N','name':'HarvestNet incoming event header'}})


def api(path):
    return node('Validate and prepare','n8n-nodes-base.httpRequest',{
        'method':'POST','url':'={{ $vars.HARVESTNET_PLATFORM_URL + "'+path+'" }}',
        'authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth',
        'sendBody':True,'specifyBody':'json','jsonBody':'={{ JSON.stringify($json.body) }}',
        'options':{'timeout':10000}},260,
        {'httpHeaderAuth':{'id':'CONFIGURE_IN_N8N','name':'HarvestNet API event bearer'}})


def respond(body='={{ JSON.stringify($json) }}'):
    return node('Respond','n8n-nodes-base.respondToWebhook',{'respondWith':'json','responseBody':body,'options':{}},800)


def email(text_field='text'):
    """Send Email over SMTP (Amazon SES). The From address is an n8n variable, never the payload."""
    return node('Send email','n8n-nodes-base.emailSend',{
        'operation':'send','fromEmail':'={{ $vars.HARVESTNET_EMAIL_FROM }}','toEmail':'={{ $json.to }}',
        'subject':'={{ $json.subject }}','emailFormat':'text','text':'={{ $json.'+text_field+' }}',
        'options':{'appendAttribution':False}},520,SMTP_CREDENTIAL)


# After a send, answer without echoing the address back: the response says only that it went.
SENT = '={{ JSON.stringify({sent: true}) }}'


def main():
    # Approval events already carry platform-issued version-bound review URLs.
    code = node('Prepare review email','n8n-nodes-base.code',{'jsCode':
        "const b = $json.body; if (!b.to || !b.message || !b.decision_url || !Number.isInteger(b.version)) throw new Error('Issued human review request required'); "
        "return [{json: {to:b.to, subject: b.subject || ('HarvestNet: review draft version ' + b.version), message:b.message}}];"},260)
    decision_api = api('/approvals')
    decision_api['parameters']['url'] = '={{ $vars.HARVESTNET_CORE_URL + "/approvals" }}'
    decision_api['credentials'] = {'httpHeaderAuth':{'id':'CONFIGURE_IN_N8N','name':'HarvestNet core approval receipt bearer'}}
    files = {
        'approval-requests.json': workflow('HarvestNet - email human review requests', [webhook('harvestnet-approval-request'),code,email('message'),respond(SENT)]),
        # A committed pickup, or a changed one after a cooler failure: the platform turns the
        # core's notice into one email with a "Can't make it" link to the household page.
        'pickup-emails.json': workflow('HarvestNet - email committed pickup and verified Market Match tip',[webhook('harvestnet-pickup'),api('/notifications/prepare'),email(),respond(SENT)]),
        # "Can't make it" happens on the household page (the email's link calls the core's
        # release_pickup). This workflow emails the thank-you for the core's release notice.
        'cannot-make-it.json': workflow("HarvestNet - email the thank-you after Can't make it",[webhook('harvestnet-cannot-make-it'),api('/notifications/prepare'),email(),respond(SENT)]),
        'human-decisions.json': workflow('HarvestNet - relay explicit version-bound human decision',[webhook('harvestnet-human-decision'),decision_api,respond()])}
    for old in ('pickup-texts.json',):  # renamed: texts became emails
        (ROOT/old).unlink(missing_ok=True)
    for file, data in files.items():
        (ROOT/file).write_text(json.dumps(data,indent=2)+'\n')
    print(f'Generated {len(files)} inactive workflows')


if __name__ == '__main__':
    main()
