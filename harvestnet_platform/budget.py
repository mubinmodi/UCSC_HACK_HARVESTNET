"""Durable, fail-closed spending reservations for live Claude calls."""
import os
import sqlite3
import threading
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path


class BudgetExceeded(ValueError):
    pass


def cents(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid USD amount') from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError('Finite, nonnegative USD amount required')
    return int((amount*100).to_integral_value(rounding=ROUND_CEILING))


class Budget:
    def __init__(self, path=':memory:', run_cap_usd=0, total_cap_usd=0):
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.run_cap, self.total_cap = cents(run_cap_usd), cents(total_cap_usd)
        self.db = sqlite3.connect(path,check_same_thread=False)
        self.lock = threading.RLock()
        self.db.execute('CREATE TABLE IF NOT EXISTS charges(run TEXT, call TEXT, cents INTEGER, settled INTEGER, PRIMARY KEY(run,call))')
        self.db.commit()

    @classmethod
    def from_env(cls):
        return cls(os.getenv('CLAUDE_BUDGET_DB','runtime/claude-budget.sqlite'),
                   os.getenv('CLAUDE_RUN_CAP_USD','0'),os.getenv('CLAUDE_TOTAL_CAP_USD','0'))

    def reserve(self, run, call, max_cost_usd):
        maximum = cents(max_cost_usd)
        if not run or not call or maximum <= 0:
            raise ValueError('Run ID, unique call ID and positive maximum cost required')
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                if self.db.execute('SELECT 1 FROM charges WHERE run=? AND call=?',(run,call)).fetchone():
                    raise BudgetExceeded('Call ID already reserved; do not repeat the live API request')
                total = self.db.execute('SELECT COALESCE(SUM(cents),0) FROM charges').fetchone()[0]
                used = self.db.execute('SELECT COALESCE(SUM(cents),0) FROM charges WHERE run=?',(run,)).fetchone()[0]
                if used+maximum > self.run_cap or total+maximum > self.total_cap:
                    raise BudgetExceeded('Claude spending cap reached; use rules or recorded replay')
                self.db.execute('INSERT INTO charges VALUES (?,?,?,0)',(run,call,maximum))
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def settle(self, run, call, actual_cost_usd):
        actual = cents(actual_cost_usd)
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row = self.db.execute('SELECT cents,settled FROM charges WHERE run=? AND call=?',(run,call)).fetchone()
                if not row or row[1] or actual > row[0]:
                    raise BudgetExceeded('Missing, repeated or underestimated cost reservation')
                self.db.execute('UPDATE charges SET cents=?,settled=1 WHERE run=? AND call=?',(actual,run,call))
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def call(self, run, call, max_cost_usd, function):
        self.reserve(run,call,max_cost_usd)
        # An uncertain failure retains the full reservation, preventing overspend.
        result, actual_cost_usd = function()
        self.settle(run,call,actual_cost_usd)
        return result
