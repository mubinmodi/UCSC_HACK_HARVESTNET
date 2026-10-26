"""The one organization roster: who takes part, in what role, and who has humans and systems.

Organization IDs are names, not roles (docs/contracts/README.md decision 1). Every module in
this package reads its lists from here; the core's scenario fixtures name the same organizations.
"""
DONOR = 'market'
BANKS = ('city', 'rural', 'eastside')
ADVOCATE = 'advocate'

ORGANIZATIONS = (DONOR, *BANKS, ADVOCATE)  # everyone with an agent
ROLES = {DONOR: 'donor', **{bank: 'food_bank' for bank in BANKS}, ADVOCATE: 'advocate'}
# The advocate has no human who approves and no systems of its own.
APPROVERS = SYSTEM_ORGANIZATIONS = (DONOR, *BANKS)
