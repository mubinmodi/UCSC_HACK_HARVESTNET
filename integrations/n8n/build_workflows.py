"""Generate importable, inactive n8n workflows without credentials or decisions.

Credential placeholders are linked by the operator after import. No workflow has
an approve operation; human callbacks go through the exact-terms review page.
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent


def node(name, kind, parameters, x, credentials=None):
    result = {'id': name.lower().replace(' ', '-'), 'name': name, 'type': kind,
              'typeVersion': {'n8n-nodes-base.webhook': 2, 'n8n-nodes-base.httpRequest': 4.2,
                              'n8n-nodes-base.respondToWebhook': 1.4, 'n8n-nodes-base.twilio': 1}.get(kind,1),
              'position': [x,0], 'parameters': parameters}
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


def respond():
    return node('Respond','n8n-nodes-base.respondToWebhook',{'respondWith':'json','responseBody':'={{ JSON.stringify($json) }}','options':{}},800)


def sms():
    return node('Send text','n8n-nodes-base.twilio',{
        'resource':'sms','operation':'send','from':'={{ $vars.HARVESTNET_SMS_FROM }}',
        'to':'={{ $json.to }}','message':'={{ $json.message }}','options':{}},520,
        {'twilioApi':{'id':'CONFIGURE_IN_N8N','name':'HarvestNet SMS provider'}})


def main():
    # Approval events already carry platform-issued version-bound review URLs.
    code = node('Prepare review text','n8n-nodes-base.code',{'jsCode':
        "const b = $json.body; if (!b.to || !b.message || !b.decision_url || !Number.isInteger(b.version)) throw new Error('Issued human review request required'); return [{json: {to:b.to, message:b.message}}];"},260)
    code['typeVersion'] = 2
    decision_api = api('/approvals')
    decision_api['parameters']['url'] = '={{ $vars.HARVESTNET_CORE_URL + "/approvals" }}'
    decision_api['credentials'] = {'httpHeaderAuth':{'id':'CONFIGURE_IN_N8N','name':'HarvestNet core approval receipt bearer'}}
    files = {
        'approval-requests.json': workflow('HarvestNet - carry human review requests', [webhook('harvestnet-approval-request'),code,sms(),respond()]),
        'pickup-texts.json': workflow('HarvestNet - committed pickup and verified Market Match text',[webhook('harvestnet-pickup'),api('/notifications/prepare'),sms(),respond()]),
        'cannot-make-it.json': workflow('HarvestNet - authenticated cannot make it reply',[webhook('harvestnet-household-reply'),api('/household/replies'),respond()]),
        'human-decisions.json': workflow('HarvestNet - relay explicit version-bound human decision',[webhook('harvestnet-human-decision'),decision_api,respond()])}
    for file, data in files.items():
        (ROOT/file).write_text(json.dumps(data,indent=2)+'\n')
    print(f'Generated {len(files)} inactive workflows')


if __name__ == '__main__':
    main()
