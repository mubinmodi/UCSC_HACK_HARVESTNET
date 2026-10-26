"""Deliver committed household notices to n8n without putting email in event records.

The event and outbox entry commit together for new pickup events. Each entry is
claimed before a network call, so a restart never silently sends a second copy after
an ambiguous timeout. An uncertain entry needs an operator to inspect/reissue it.
"""
import threading
from urllib.parse import urlsplit

from harvestnet_platform.http import request_json

from .notices import pickup_notice, released_notice
from .records import NotFound


def post_webhook(url, token, notice):
    validate_webhook_url(url)
    result=request_json(url,notice,token=token,timeout=10,method='POST')
    if not isinstance(result,dict) or result.get('sent') is not True:
        raise ValueError('notification webhook did not confirm sending')


def validate_webhook_url(url):
    parsed=urlsplit(url)
    if not parsed.netloc or (parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1'))):
        raise ValueError('notification webhook must use HTTPS')


class EmailDispatcher:
    def __init__(self, api, *, pickup_webhook, release_webhook, token, allowed_recipients=(), send=post_webhook):
        if not api.household_page_url or not token:
            raise ValueError('household URL and notification token are required')
        self.api=api
        self.webhooks={'pickup_ready':pickup_webhook,'pickup_changed':pickup_webhook,
                       'pickup_released':release_webhook}
        for url in self.webhooks.values():
            validate_webhook_url(url)
        self.token=token
        self.allowed={address.strip().lower() for address in allowed_recipients if address.strip()}
        if not self.allowed:
            raise ValueError('SES_TEST_RECIPIENTS is required while household email is enabled')
        self.send=send

    def _update(self, entry, status, reason=None):
        with self.api.records.transaction():
            self.api.records.put('email_outbox',str(entry['event_sequence']),{
                **entry,'status':status, **({'reason':reason} if reason else {})})

    def dispatch_pending(self):
        """Attempt each new notice once. Return a count by final status, never addresses."""
        counts={'sent':0,'skipped':0,'uncertain':0}
        records=self.api.records
        with records.lock:
            pending=[x for x in records.all('email_outbox') if x['status']=='pending']
        for entry in pending:
            url=self.webhooks.get(entry['kind'])
            if not url:
                continue
            with records.lock:
                if records.get('email_outbox',str(entry['event_sequence']))['status']!='pending':
                    continue
                # A changed/released pickup supersedes an unsent older notice.
                try:
                    pickup=records.get('pickup',entry['pickup_id'])
                    if entry['kind']=='pickup_released':
                        notice=released_notice(self.api,entry['pickup_id'],pickup['request_code'])
                    else:
                        if pickup['status']!='committed' or pickup['version']!=entry['version']:
                            self._update(entry,'skipped','superseded')
                            counts['skipped']+=1
                            continue
                        notice=pickup_notice(self.api,entry['pickup_id'],household_page_url=self.api.household_page_url)
                        notice['kind']=entry['kind']
                except (NotFound,KeyError,ValueError):
                    self._update(entry,'skipped','pickup unavailable')
                    counts['skipped']+=1
                    continue
                if not notice['to']:
                    self._update(entry,'skipped','no household email')
                    counts['skipped']+=1
                    continue
                if self.allowed and notice['to'].lower() not in self.allowed:
                    self._update(entry,'skipped','recipient outside test allowlist')
                    counts['skipped']+=1
                    continue
                self._update(entry,'sending')
            # Keep the API's records lock free during the remote SMTP workflow.
            try:
                self.send(url,self.token,notice)
            except Exception:
                # A timeout may mean n8n accepted the message. Never auto-retry it.
                self._update(entry,'uncertain','delivery unconfirmed')
                counts['uncertain']+=1
            else:
                self._update(entry,'sent')
                counts['sent']+=1
        return counts

    def run_forever(self, stop=None, interval=2):
        stop=stop or threading.Event()
        while not stop.wait(interval):
            self.dispatch_pending()
