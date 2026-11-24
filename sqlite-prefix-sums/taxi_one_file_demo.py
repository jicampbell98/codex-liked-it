"""Fetch one bounded NYC taxi JSON extract and benchmark one SQLite report."""

import json
import sqlite3
import statistics
import subprocess
import time
from contextlib import closing
from decimal import Decimal
from urllib.parse import urlencode
from sqlite_sales_ledger import SCHEMA, report

query = urlencode({'$select':'tpep_pickup_datetime,fare_amount',
                   '$where':"tpep_pickup_datetime >= '2023-01-01T00:00:00' AND tpep_pickup_datetime < '2023-01-02T00:00:00' AND fare_amount IS NOT NULL",
                   '$order':'tpep_pickup_datetime,:id', '$limit':5000})
raw = subprocess.check_output(['curl','--fail','--silent','--show-error','--max-time','20','--max-filesize','2000000','https://data.cityofnewyork.us/resource/4b4i-vvec.json?' + query])
assert len(raw) <= 2_000_000
records = json.loads(raw, parse_float=Decimal)
rows = []
for row in records:
    cents = Decimal(str(row['fare_amount'])) * 100
    assert cents == cents.to_integral_value()
    stamp = int(''.join(c for c in row['tpep_pickup_datetime'][:19] if c.isdigit()))
    rows.append((stamp, int(cents)))
assert len(rows) == 5000 and all(a[0] <= b[0] for a,b in zip(rows, rows[1:]))
bounds = (20230101000000, 20230102000000)
expected = len(rows), sum(amount for _,amount in rows)
def cumulative_rows():
    total = 0
    for number, (stamp,amount) in enumerate(rows,1):
        total += amount
        yield stamp,number,amount,total
with closing(sqlite3.connect(':memory:')) as standard, closing(sqlite3.connect(':memory:')) as fast:
    t = time.perf_counter_ns()
    with standard:
        standard.execute('CREATE TABLE trips (stamp INTEGER, fare_cents INTEGER)')
        standard.executemany('INSERT INTO trips VALUES (?,?)', rows)
        standard.execute('CREATE INDEX trips_report ON trips(stamp,fare_cents)')
    baseline_load = (time.perf_counter_ns()-t)/1_000_000
    t = time.perf_counter_ns()
    with fast:
        fast.execute(SCHEMA)
        fast.executemany('INSERT INTO sale_postings VALUES (?,?,?,?)', cumulative_rows())
    prefix_load = (time.perf_counter_ns()-t)/1_000_000
    def baseline():
        return standard.execute('SELECT count(*), sum(fare_cents) FROM trips WHERE stamp>=? AND stamp<?',bounds).fetchone()
    def ledger():
        return report(fast,*bounds)
    for query in (baseline,ledger):
        assert query() == expected
    samples = [[],[]]
    for i in range(101):
        for idx in ((0,1) if i%2==0 else (1,0)):
            func = (baseline,ledger)[idx]
            t = time.perf_counter_ns()
            result = func()
            elapsed = time.perf_counter_ns()-t
            assert result == expected
            if i: samples[idx].append(elapsed/1000)
print(json.dumps({'json_bytes':len(raw),'trips':expected[0],'fare_cents':expected[1],
                  'covering_index_report_us':statistics.median(samples[0]),
                  'two_lookup_report_us':statistics.median(samples[1]),
                  'covering_index_load_ms':baseline_load,'two_lookup_load_ms':prefix_load}))
