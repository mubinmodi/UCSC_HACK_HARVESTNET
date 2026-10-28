"""Generate importable, inactive n8n workflows without credentials or decisions.

Credential placeholders are linked by the operator after import: they are referenced by
name only, and no secret is in any JSON file. No workflow has an approve operation; human
callbacks go through the exact-terms review page.

Messages go by email (user decision, October 11, 2026): n8n's Send Email node over SMTP,
with Amazon SES SMTP credentials configured in n8n Cloud. No workflow uses SMS.

No workflow is an open mail relay. Each email workflow checks the recipient itself, against
the n8n variable ``HARVESTNET_EMAIL_ALLOWLIST`` (comma-separated; set it to the same verified
addresses as ``SES_TEST_RECIPIENTS``). An empty or missing list sends nothing. The callers'
own allowlists stay as a first check, but the workflow does not rely on them. The review
email is written here from a fixed template and checked fields, never from free text in the
payload; its link must start with ``HARVESTNET_REVIEW_BASE_URL`` (the deployment's
``APPROVAL_PUBLIC_URL``) followed by ``/human/review?token=``.
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

# The recipient check every email workflow runs first (fails closed when the list is unset).
ALLOWLIST_JS = (
    "const allow = String($vars.HARVESTNET_EMAIL_ALLOWLIST || '').split(',').map(a => a.trim().toLowerCase()).filter(Boolean); "
    "const recipient = (value) => { const to = typeof value === 'string' ? value.trim().toLowerCase() : ''; "
    "if (!allow.length || !allow.includes(to)) throw new Error('Recipient is not on HARVESTNET_EMAIL_ALLOWLIST'); return to; }; ")

# The review email: checked fields into a fixed template. No subject or message comes from the payload.
REVIEW_EMAIL_JS = ALLOWLIST_JS + (
    "const b = $json.body || {}; const to = recipient(b.to); "
    "const base = String($vars.HARVESTNET_REVIEW_BASE_URL || '').replace(/\\/+$/, '') + '/human/review?token='; "
    "const url = typeof b.decision_url === 'string' ? b.decision_url : ''; "
    "if (!base.startsWith('https://') || !url.startsWith(base) || !/^[A-Za-z0-9_-]{20,128}$/.test(url.slice(base.length))) "
    "throw new Error('A review link issued by HarvestNet is required'); "
    "if (!/^[a-z][a-z0-9-]{0,40}$/.test(String(b.organization_id || '')) || !/^[A-Za-z0-9._:-]{1,100}$/.test(String(b.lot_id || '')) "
    "|| !Number.isInteger(b.version) || b.version < 1 || !/^sha256:[0-9a-f]{64}$/.test(String(b.terms_hash || ''))) "
    "throw new Error('Issued human review request required'); "
    "const subject = 'HarvestNet: review draft version ' + b.version + ' for lot ' + b.lot_id; "
    "const message = 'HarvestNet: ' + b.organization_id + ', review draft version ' + b.version + ' for lot ' + b.lot_id + '.\\n\\n' "
    "+ 'Open the link to see the exact terms (terms hash ' + b.terms_hash + ') and choose Approve or Decline:\\n' + url "
    "+ '\\n\\nNo reply means no approval.'; "
    "return [{json: {to, subject, message}}];")

# Pickup emails: the platform already wrote the text from the core's notice; check the recipient here.
PREPARED_EMAIL_JS = ALLOWLIST_JS + (
    "const m = $json; "
    "if (m.mode !== 'prepared_email' || typeof m.subject !== 'string' || typeof m.text !== 'string') "
    "throw new Error('A platform-prepared email is required'); "
    "return [{json: {to: recipient(m.to), subject: m.subject, text: m.text}}];")


def check_recipient():
    return node('Check recipient allowlist','n8n-nodes-base.code',{'jsCode':PREPARED_EMAIL_JS},390)


def main():
    # Approval events already carry platform-issued version-bound review URLs.
    code = node('Check recipient and write review email','n8n-nodes-base.code',{'jsCode':REVIEW_EMAIL_JS},260)
    decision_api = api('/approvals')
    decision_api['parameters']['url'] = '={{ $vars.HARVESTNET_CORE_URL + "/approvals" }}'
    decision_api['credentials'] = {'httpHeaderAuth':{'id':'CONFIGURE_IN_N8N','name':'HarvestNet core approval receipt bearer'}}
    files = {
        'approval-requests.json': workflow('HarvestNet - email human review requests', [webhook('harvestnet-approval-request'),code,email('message'),respond(SENT)]),
        # A committed pickup, or a changed one after a cooler failure: the platform turns the
        # core's notice into one email with a "Can't make it" link to the household page.
        'pickup-emails.json': workflow('HarvestNet - email committed pickup and verified Market Match tip',[webhook('harvestnet-pickup'),api('/notifications/prepare'),check_recipient(),email(),respond(SENT)]),
        # "Can't make it" happens on the household page (the email's link calls the core's
        # release_pickup). This workflow emails the thank-you for the core's release notice.
        'cannot-make-it.json': workflow("HarvestNet - email the thank-you after Can't make it",[webhook('harvestnet-cannot-make-it'),api('/notifications/prepare'),check_recipient(),email(),respond(SENT)]),
        'human-decisions.json': workflow('HarvestNet - relay explicit version-bound human decision',[webhook('harvestnet-human-decision'),decision_api,respond()])}
    for old in ('pickup-texts.json',):  # renamed: texts became emails
        (ROOT/old).unlink(missing_ok=True)
    for file, data in files.items():
        (ROOT/file).write_text(json.dumps(data,indent=2)+'\n')
    print(f'Generated {len(files)} inactive workflows')


if __name__ == '__main__':
    main()
