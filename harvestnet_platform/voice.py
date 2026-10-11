"""Text alternative to voice: consent-ready draft, never an allocation."""


def text_intake(data):
    size = data.get('household_size')
    if type(size) is not int or not 1 <= size <= 30:
        raise ValueError('Household size must be 1 to 30')
    if type(data.get('limited_fridge')) is not bool:
        raise ValueError('Limited fridge answer required')
    if data.get('snap','not_said') not in ('yes','no','not_said'):
        raise ValueError('SNAP answer is optional: yes, no, or not_said')
    if not isinstance(data.get('pickup_windows'),list) or not data['pickup_windows']:
        raise ValueError('Pickup windows required')
    # Whitelist fields; names, addresses and arbitrary transcript instructions do
    # not enter an agent context. The real front desk/core own submission/expiry.
    draft = {key:data[key] for key in ('household_size','pickup_windows','limited_fridge')}
    draft.update(neighborhood=str(data.get('neighborhood',''))[:100],
                 cannot_eat=data.get('cannot_eat',[]),snap=data.get('snap','not_said'),
                 language=data.get('language','en'))
    return {'mode':'text_intake_fallback','status':'readback_awaiting_consent','draft_request':draft,
            'saved':False,'allocated':False,'reason':'Review this draft, then submit with consent to the core household API when available.'}
