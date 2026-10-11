"""The core's household notices for pickup emails (Workflow 3; design sections 9, 11).

Each notice is the trusted data Lane C's ``/notifications/prepare`` turns into an email
(subject and plain text) for n8n's Send Email node and Amazon SES. The core supplies the facts:
pounds from the portion calculator, produce names in the household's language (``name_es``
from the reviewed produce profiles), the pickup window, the request code, the "Can't make it"
link, and ``to`` only if the household gave an email. Nothing here sends anything.

Three kinds: ``pickup_ready`` (a committed pickup), ``pickup_changed`` (built by
``cooler_join.household_texts`` after a changed version commits), and ``pickup_released``
(the thank-you after a household said it can't make it). Proposed, pending #18 and #22.
"""
from .contact import release_url
from .records import NotFound


def household_email(records, request_code):
    """The household's email, or ``None``. Only the core reads it, never the API."""
    try:
        return records.get('email', request_code)['email']
    except NotFound:
        return None


def pickup_notice(api, pickup_id, *, household_page_url):
    """A committed pickup's ``pickup_ready`` notice, in its household's language."""
    p = api.records.get('pickup', pickup_id)
    if p['status'] != 'committed':
        raise ValueError(f"pickup {pickup_id} is {p['status']}; only committed produce is announced")
    r = api.records.get('request', p['request_code'])
    language = r.get('language', 'en')
    return {
        'kind': 'pickup_ready', 'committed': True, 'language': language,
        'food_bank_id': p['food_bank_id'], 'food_bank': p['food_bank_name'],
        'items': [{'produce_id': i['produce_id'], 'name': api.item_name(i['produce_id'], language).lower(), 'pounds': i['pounds']}
                  for i in p['items']],
        'window': {'start': p['window']['start'], 'end': p['window']['end']},
        'request_code': p['request_code'], 'pickup_id': pickup_id, 'version': p['version'], 'snap': r.get('snap'),
        'reply_expected': p.get('reply_expected') is True,
        'release_url': release_url(household_page_url, pickup_id, p['request_code'], language),
        'to': household_email(api.records, p['request_code']),
    }


def released_notice(api, pickup_id, request_code):
    """The thank-you after "Can't make it". Raises unless the pickup really was released."""
    p = api.records.get('pickup', pickup_id)
    if p['request_code'] != request_code or p['status'] != 'released':
        raise ValueError('only a released pickup of this request gets a release notice')
    r = api.records.get('request', request_code)
    return {'kind': 'pickup_released', 'released': True, 'language': r.get('language', 'en'), 'pickup_id': pickup_id,
            'released_lb': p['pounds'], 'to': household_email(api.records, request_code)}
