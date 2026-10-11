# Lane A takeover acceptance stack

User authorized commits on all six original yi36 branches; review stack #7 -> #8 -> #9 -> #10 -> #22 -> #24. Requirements are the supplied plan and live GitHub issues. Keep issues open until all acceptance gates are verified. No AWS, paid model runs or real SMS is authorized.

## Issue #7

Transactional records, owner holds, exact-version human approvals, event audits and real-agent fixture execution. Shared calculator and API primitives are prerequisites for executing household confirmations and releases. SQLite is the local fallback; CI uses a dedicated Postgres service. Test: python -m unittest discover -s core_tests -v, with agents/src on PYTHONPATH.
