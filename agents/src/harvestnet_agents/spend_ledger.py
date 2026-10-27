"""The persistent Claude spend ledger: one JSON file of cumulative actual spend.

``SpendingCap`` (``llm_negotiators.py``) enforces the per-run cap in memory and the total cap
(``CLAUDE_TOTAL_CAP_USD``) against this file, so a restart, a second process or a paid
evaluation run cannot reset the total. Every live Claude caller (the LLM negotiators, the
front-desk and voice extractor, ``python -m harvestnet_core evaluate``) goes through it.

**File.** ``CLAUDE_SPEND_LEDGER`` (default ``runtime/claude-spend.json``; ``/app/budget/claude-spend.json``
in the AWS stack, on the ``budget-data`` volume that ``deploy/aws/reset_data.sh`` keeps).
JSON, ``{"version": 1, "entries": [...], "pending": {...}}``. An entry has only a time, a caller
label (``negotiator``, ``front_desk``, ``voice_line``, ``evaluation``, ``manual``), a model and a cost in
USD, plus a free-text ``note`` on manual entries. No prompts, transcripts or personal data.

**Safe across processes.** Every read-modify-write holds an exclusive ``flock`` on a sibling
``.lock`` file and replaces the ledger with an atomic rename, so concurrent writers never lose an
entry and a crash never leaves half a file. If the file can't be read or written the cap fails
closed (no call is made).

**Reservations.** Before a call, ``reserve`` adds the call's worst-case cost to ``pending`` under the
lock, after checking that cumulative spend plus every pending reservation (from any process) plus this one
fits the total cap. After the call, ``settle`` swaps the reservation for the actual cost. A process that
dies mid-call leaves its reservation, which counts at its worst case; one older than an hour is charged
as spent at that worst case the next time the ledger is written.

Seed or correct the ledger by hand (a spend that happened before the ledger existed)::

    python -m harvestnet_agents.spend_ledger add 9.92 --note "Oct 11 runs, upper bound"
    python -m harvestnet_agents.spend_ledger show

Costs are estimates from token usage and the price table in ``llm_negotiators.py``; this is not a
provider billing cap.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

try:  # POSIX (the Docker image and macOS); the ledger needs an inter-process lock
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

__all__ = ["DEFAULT_LEDGER_PATH", "LEDGER_ENV", "LedgerError", "SpendLedger", "TotalCapReached", "main"]

LEDGER_ENV = "CLAUDE_SPEND_LEDGER"
DEFAULT_LEDGER_PATH = "runtime/claude-spend.json"
VERSION = 1
STALE_RESERVATION = timedelta(hours=1)


class LedgerError(RuntimeError):
    """The ledger can't be read or written. Callers fail closed: no call is made."""


class TotalCapReached(LedgerError):
    """A call's worst case doesn't fit under the total cap. No call was made."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _usd(value: Any, what: str = "cost") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{what} must be a finite, nonnegative number of US dollars, not {value!r}")
    return round(float(value), 6)


class SpendLedger:
    """Cumulative Claude spend in one JSON file. Cheap to construct: nothing is touched until used."""

    def __init__(self, path: str | os.PathLike[str], *, clock=_now):
        self.path = Path(path)
        self._clock = clock

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "SpendLedger":
        env = os.environ if env is None else env
        return cls((env.get(LEDGER_ENV) or "").strip() or DEFAULT_LEDGER_PATH)

    # --- storage -----------------------------------------------------------------------------

    @contextmanager
    def _locked(self) -> Iterator[None]:
        if fcntl is None:  # pragma: no cover
            raise LedgerError("the spend ledger needs a POSIX file lock")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(self.path.with_name(self.path.name + ".lock"), "a")
        except OSError as exc:
            raise LedgerError(f"can't open the spend ledger lock beside {self.path}: {exc}") from exc
        with handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"version": VERSION, "entries": [], "pending": {}}
        except OSError as exc:
            raise LedgerError(f"can't read the spend ledger {self.path}: {exc}") from exc
        try:
            data = json.loads(text)
            if not (isinstance(data, dict) and isinstance(data.get("entries"), list) and isinstance(data.get("pending", {}), dict)):
                raise ValueError("unexpected shape")
            for entry in data["entries"]:
                _usd(entry["cost_usd"])
            for reservation in data.get("pending", {}).values():
                _usd(reservation["reserved_usd"])
        except (ValueError, KeyError, TypeError) as exc:
            raise LedgerError(f"the spend ledger {self.path} is unreadable ({exc}); fix or restore it before any paid call") from exc
        data.setdefault("pending", {})
        data["version"] = VERSION
        return data

    def _write(self, data: dict[str, Any]) -> None:
        try:
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name + ".", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, indent=1, sort_keys=True, allow_nan=False)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except OSError as exc:
            raise LedgerError(f"can't write the spend ledger {self.path}: {exc}") from exc

    def _expire_stale(self, data: dict[str, Any]) -> bool:
        cutoff = self._clock() - STALE_RESERVATION

        def stale(held: Mapping[str, Any]) -> bool:
            try:
                return datetime.fromisoformat(held["time"]) < cutoff
            except (KeyError, TypeError, ValueError):
                return True  # no usable time: charge it now rather than hold it forever

        expired = [r for r, v in data["pending"].items() if stale(v)]
        for rid in expired:
            held = data["pending"].pop(rid)
            data["entries"].append({
                "time": self._clock().isoformat(), "caller": held.get("caller", "unknown"), "model": "unknown",
                "cost_usd": held["reserved_usd"], "note": "reservation never settled; charged at its worst case",
            })
        return bool(expired)

    @staticmethod
    def _sum(data: Mapping[str, Any]) -> float:
        return round(math.fsum(e["cost_usd"] for e in data["entries"]) + math.fsum(p["reserved_usd"] for p in data["pending"].values()), 6)

    # --- reading -----------------------------------------------------------------------------

    def total_usd(self) -> float:
        """Spent so far, plus calls in flight at their worst case."""
        with self._locked():
            return self._sum(self._read())

    def entries(self) -> list[dict[str, Any]]:
        with self._locked():
            return list(self._read()["entries"])

    # --- writing -----------------------------------------------------------------------------

    def reserve(self, caller: str, worst_case_usd: float, total_cap_usd: float) -> str:
        """Hold ``worst_case_usd`` against the total cap, or raise ``TotalCapReached``. Returns the reservation id."""
        worst = _usd(worst_case_usd, "worst case")
        with self._locked():
            data = self._read()
            expired = self._expire_stale(data)
            spent = self._sum(data)
            if spent + worst > total_cap_usd + 1e-9:
                if expired:
                    self._write(data)  # keep the charge for reservations that were never settled
                raise TotalCapReached(
                    f"a call could cost up to ${worst:.4f}; the ledger shows ${spent:.4f} spent of the ${total_cap_usd:.2f} total cap"
                )
            rid = uuid.uuid4().hex
            data["pending"][rid] = {"time": self._clock().isoformat(), "caller": caller, "reserved_usd": worst}
            self._write(data)
            return rid

    def settle(self, reservation_id: str | None, caller: str, model: str, cost_usd: float) -> None:
        """Replace a reservation with the actual cost of the call (recorded even if it exceeded the reservation)."""
        cost = _usd(cost_usd)
        with self._locked():
            data = self._read()
            data["pending"].pop(reservation_id or "", None)
            data["entries"].append({"time": self._clock().isoformat(), "caller": caller, "model": model, "cost_usd": cost})
            self._write(data)

    def release(self, reservation_id: str | None) -> None:
        """Drop a reservation whose call was never made."""
        if not reservation_id:
            return
        with self._locked():
            data = self._read()
            if data["pending"].pop(reservation_id, None) is not None:
                self._write(data)

    def add(self, cost_usd: float, *, caller: str = "manual", model: str = "", note: str | None = None) -> dict[str, Any]:
        """Record spend by hand, such as spend from before the ledger existed."""
        entry: dict[str, Any] = {"time": self._clock().isoformat(), "caller": caller, "model": model, "cost_usd": _usd(cost_usd)}
        if note:
            entry["note"] = note
        with self._locked():
            data = self._read()
            data["entries"].append(entry)
            self._write(data)
        return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m harvestnet_agents.spend_ledger", description="Inspect or seed the Claude spend ledger.")
    parser.add_argument("--ledger", help=f"ledger file (default: ${LEDGER_ENV}, else {DEFAULT_LEDGER_PATH})")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="record a manual starting entry")
    add.add_argument("usd", type=float, help="cost in US dollars")
    add.add_argument("--note", default=None, help="what this is (no personal data)")
    commands.add_parser("show", help="print the entries and the total")
    args = parser.parse_args(argv)
    ledger = SpendLedger(args.ledger) if args.ledger else SpendLedger.from_env()
    try:
        if args.command == "add":
            ledger.add(args.usd, note=args.note)
        for e in ledger.entries():
            print(f"{e['time']}  {e['caller']:<12} {e.get('model', ''):<20} ${e['cost_usd']:.4f}  {e.get('note', '')}".rstrip())
        print(f"ledger {ledger.path}: total ${ledger.total_usd():.4f} (including calls in flight)")
    except (LedgerError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
