# UCSC_HACK_HARVESTNET
hackathon project

## Lane C implementation

The platform integration branches now contain organization-system fixtures,
A2A/native AGNTCY hosts, version-bound human approvals, importable n8n workflows,
offline fallbacks, deployment configuration and a real-agent join adapter.

Start with [the platform runbook](docs/platform/DEPLOYMENT.md).
For an account-free local rehearsal, run `python -m harvestnet_platform.demo`
from the repo root, then open the URL saved in `runtime/demo-url.txt`.
This is a labeled platform rehearsal; the full household/core/negotiator
implementation and live deployments are tracked in the team's other issues.

Tests: `python -m unittest discover -s tests -v` (Python 3.12+).
Optional native SDK tests require `requirements-agntcy.txt`.
