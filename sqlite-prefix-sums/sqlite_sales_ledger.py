"""Append-only SQLite sales ledger with exact reports over [start, end)."""

import argparse
import json
import sqlite3
from contextlib import closing


SCHEMA = """
CREATE TABLE IF NOT EXISTS sale_postings (
    posted_at INTEGER NOT NULL,
    posting_number INTEGER NOT NULL CHECK (posting_number > 0),
    amount_cents INTEGER NOT NULL,
    cumulative_cents INTEGER NOT NULL,
    PRIMARY KEY (posted_at, posting_number)
) WITHOUT ROWID, STRICT
"""

REPORT = """
WITH end_posting AS (
    SELECT posting_number, cumulative_cents FROM sale_postings WHERE posted_at < ?2
    ORDER BY posted_at DESC, posting_number DESC LIMIT 1
), start_posting AS (
    SELECT posting_number, cumulative_cents FROM sale_postings WHERE posted_at < ?1
    ORDER BY posted_at DESC, posting_number DESC LIMIT 1
)
SELECT 1, posting_number, cumulative_cents FROM end_posting
UNION ALL
SELECT -1, posting_number, cumulative_cents FROM start_posting
"""


def open_ledger(path):
    """Open a ledger connection. The caller is responsible for closing it."""
    ledger = sqlite3.connect(path)
    try:
        ledger.execute("PRAGMA journal_mode = WAL")
        ledger.execute("PRAGMA synchronous = FULL")
        ledger.execute(SCHEMA)
    except sqlite3.Error:
        ledger.close()
        raise
    return ledger


def append_posting(ledger, posted_at, amount_cents):
    """Append a sale or refund and return its posting number after commit."""
    if type(posted_at) is not int or type(amount_cents) is not int:
        raise TypeError("Timestamp and amount in cents must be integers")
    # Lock before reading the tail so independent writers cannot reuse its totals.
    ledger.execute("BEGIN IMMEDIATE")
    with ledger:
        previous = ledger.execute("""
            SELECT posted_at, posting_number, cumulative_cents FROM sale_postings
            ORDER BY posted_at DESC, posting_number DESC LIMIT 1
        """).fetchone()
        number = 1
        total = amount_cents
        if previous is not None:
            last_timestamp, last_number, last_total = previous
            if posted_at < last_timestamp:
                raise ValueError("Postings must use a timestamp at or after the last posting")
            number = last_number + 1
            total += last_total
        ledger.execute("INSERT INTO sale_postings VALUES (?, ?, ?, ?)",
                       (posted_at, number, amount_cents, total))
    return number


def report(ledger, start, end):
    """Return (posting count, net cents) in one snapshot. An empty sum is None."""
    if type(start) is not int or type(end) is not int:
        raise TypeError("Report bounds must be integers")
    if start > end:
        raise ValueError("Report end must be at or after its start")
    count = total = 0
    for sign, posting_number, cumulative_cents in ledger.execute(REPORT, (start, end)):
        count += sign * posting_number
        total += sign * cumulative_cents
    return count, total if count else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", help="Path to a SQLite ledger file")
    commands = parser.add_subparsers(dest="command", required=True)
    append = commands.add_parser("append", help="Append a posting in integer cents")
    append.add_argument("timestamp", type=int)
    append.add_argument("cents", type=int)
    summary = commands.add_parser("report", help="Report over [start, end)")
    summary.add_argument("start", type=int)
    summary.add_argument("end", type=int)
    args = parser.parse_args()
    try:
        with closing(open_ledger(args.database)) as ledger:
            if args.command == "append":
                result = {"posting_number": append_posting(ledger, args.timestamp, args.cents)}
            else:
                count, total = report(ledger, args.start, args.end)
                result = {"posting_count": count, "net_cents": total}
    except (sqlite3.Error, ValueError, OverflowError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
