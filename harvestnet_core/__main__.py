"""``python -m harvestnet_core run|evaluate|replay``.

``evaluate`` stores each scenario's results in the same records the server reads
(``--database``, default ``DATABASE_URL`` or ``runtime/core.sqlite``), so ``GET /results``
returns them unchanged. Without ``--llm-cap-usd`` the LLM method is ``not_run``. A zero cap
runs the LLM method with no model calls and labels it ``fallback_only``. A nonzero cap needs
``--allow-paid`` and is shared by every scenario and repetition in this command. It is the per-run
cap; ``CLAUDE_TOTAL_CAP_USD`` (default: the same cap) also applies, against the persistent spend ledger
(``CLAUDE_SPEND_LEDGER``) that every paid caller shares.
"""
import argparse
import json
import os
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m harvestnet_core')
    parser.add_argument('command', choices=['run', 'evaluate', 'replay'])
    parser.add_argument('paths', nargs='+', help='fixture paths (run, evaluate) or one saved replay (replay)')
    parser.add_argument('--output', default='runtime/replays', help='where evaluate saves recorded replays')
    parser.add_argument('--database', default=os.environ.get('DATABASE_URL', 'runtime/core.sqlite'),
                        help='records that GET /results reads (SQLite path or PostgreSQL DSN)')
    parser.add_argument('--repeats', type=int, default=1, help='repetitions of the LLM method')
    parser.add_argument('--llm-cap-usd', type=float, default=None, help='per-run spending cap for the LLM method (0 to 100); CLAUDE_TOTAL_CAP_USD also applies, via the spend ledger')
    parser.add_argument('--allow-paid', action='store_true', help='authorize a nonzero LLM spending cap')
    args = parser.parse_args(argv)
    if args.command == 'replay':
        from .evaluation import replay
        results = [replay(path) for path in args.paths]
    elif args.command == 'run':
        from .engine import run_fixture
        results = [run_fixture(json.loads(Path(path).read_text(encoding='utf-8'))) for path in args.paths]
    else:
        from .live_evaluation import LLMProvider, publish_evaluation
        from .records import Records
        provider = None
        if args.llm_cap_usd is not None:
            # A zero cap never builds a model client; a nonzero cap needs --allow-paid.
            provider = LLMProvider(None, limit_usd=args.llm_cap_usd, allow_paid=args.allow_paid)
        if not args.database.startswith(('postgres://', 'postgresql://')):
            Path(args.database).parent.mkdir(parents=True, exist_ok=True)
        records = Records(args.database)
        try:
            results = [publish_evaluation(json.loads(Path(path).read_text(encoding='utf-8')), records, llm_provider=provider,
                                          repeats=args.repeats, output=args.output) for path in args.paths]
        finally:
            records.close()
    print(json.dumps(results if args.command == 'evaluate' else results[0] if len(results) == 1 else results, indent=2, allow_nan=False))
    return results


if __name__ == '__main__':
    main()
