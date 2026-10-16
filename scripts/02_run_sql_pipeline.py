#!/usr/bin/env python3
"""
02_run_sql_pipeline.py
----------------------
Executes the project's REAL SQL files (sql/03_views.sql, sql/04_stored_procedures.sql,
sql/05_analysis_queries.sql) and writes every result set to outputs/.

Why SQLite?  The deliverable SQL is written for MySQL 8. This script loads the same CSVs into an
in-memory SQLite database, registers MySQL-compatible shims (DATEDIFF, GREATEST, LEAST, CONCAT,
CEILING, FLOOR), turns each CREATE PROCEDURE body into a parameterised script and runs the *same SQL
text*. That lets the numbers in the README / Excel / Tableau extracts come out of the actual
stored-procedure logic. It is NOT a substitute for running the files on MySQL (see README, "Verification").

Run:  python3 scripts/02_run_sql_pipeline.py
"""
import math
import os
import re
import sqlite3
import time
from datetime import datetime

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA, SQL, OUT = f"{ROOT}/data/clean", f"{ROOT}/sql", f"{ROOT}/outputs"
RES = f"{OUT}/sql_results"
os.makedirs(RES, exist_ok=True)
os.makedirs(f"{OUT}/queries", exist_ok=True)

# ----------------------------------------------------------------------------- MySQL shims
def _d(x):
    return None if x is None else datetime.strptime(str(x)[:10], "%Y-%m-%d").date()

def datediff(a, b):
    a, b = _d(a), _d(b)
    return None if a is None or b is None else (a - b).days

def greatest(*a):
    return None if any(v is None for v in a) else max(a)

def least(*a):
    return None if any(v is None for v in a) else min(a)

def _fmt(v):
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)

def concat(*a):
    return None if any(v is None for v in a) else "".join(_fmt(v) for v in a)

def ceiling(x):
    return None if x is None else math.ceil(x)

def floor(x):
    return None if x is None else math.floor(x)

con = sqlite3.connect(":memory:")
for name, fn, n in [("DATEDIFF", datediff, 2), ("GREATEST", greatest, -1), ("LEAST", least, -1),
                    ("CONCAT", concat, -1), ("CEILING", ceiling, 1), ("FLOOR", floor, 1)]:
    con.create_function(name, n, fn)

# ----------------------------------------------------------------------------- load data
TABLES = ["dim_warehouse", "dim_supplier", "dim_sku", "dim_week", "dim_asset", "cfg_thresholds",
          "fact_inventory_weekly", "fact_purchase_orders", "fact_asset_monthly"]
headers = {}
for t in TABLES:
    df = pd.read_csv(f"{DATA}/{t}.csv")
    headers[t] = list(df.columns)
    df.to_sql(t, con, index=False)
con.execute("CREATE INDEX i1 ON fact_inventory_weekly (warehouse_id, sku_id, week_start)")
con.execute("CREATE INDEX i2 ON fact_inventory_weekly (week_end)")
con.execute("CREATE INDEX i3 ON fact_purchase_orders (warehouse_id, sku_id, promised_date)")
con.execute("""CREATE TABLE alert_log (alert_id INTEGER PRIMARY KEY AUTOINCREMENT, as_of_date TEXT, alert_type TEXT,
               severity TEXT, warehouse_id TEXT, sku_id TEXT, supplier_id TEXT, message TEXT,
               metric_value REAL, threshold_value REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

# ----------------------------------------------------------------------------- schema consistency check
schema_txt = re.sub(r"--[^\n]*", "", open(f"{SQL}/01_schema.sql").read())
problems = 0
for t in TABLES:
    m = re.search(rf"CREATE TABLE {t} \((.*?)\)\s*ENGINE", schema_txt, re.S)
    cols = []
    for line in m.group(1).split("\n"):
        tok = line.strip().split()
        if tok and tok[0].upper() not in ("PRIMARY", "KEY", "CONSTRAINT", "FOREIGN", "UNIQUE"):
            cols.append(tok[0])
    if cols != headers[t]:
        problems += 1
        print(f"  SCHEMA MISMATCH in {t}:\n    schema: {cols}\n    csv   : {headers[t]}")
load_txt = open(f"{SQL}/02_load_data.sql").read()
m = re.search(r'\(po_id,(.*?)\) "', load_txt, re.S)
raw = re.sub(r'["\n]', " ", m.group(1))
po_cols = ["po_id"] + [c.strip().lstrip("@") for c in raw.split(",") if c.strip()]
po_cols = ["received_date" if c == "received_date" else c for c in po_cols]
if po_cols != headers["fact_purchase_orders"]:
    problems += 1
    print("  LOAD-COLUMN-LIST MISMATCH for fact_purchase_orders", po_cols)
print("Schema / CSV / LOAD DATA column check:", "OK" if problems == 0 else f"{problems} PROBLEM(S)")

# ----------------------------------------------------------------------------- helpers
def statements(sql_text):
    sql_text = re.sub(r"--[^\n]*", "", sql_text)
    sql_text = re.sub(r"^\s*USE\s+\w+\s*;", "", sql_text, flags=re.M | re.I)
    return [s.strip() for s in sql_text.split(";") if s.strip()]

def shim(stmt):
    return re.sub(r"DROP TEMPORARY TABLE", "DROP TABLE", stmt, flags=re.I)

def run_select(stmt, params=None):
    cur = con.execute(stmt, params or {})
    cols = [d[0] for d in cur.description] if cur.description else None
    return pd.DataFrame(cur.fetchall(), columns=cols) if cols else None

# views
t0 = time.time()
for s in statements(open(f"{SQL}/03_views.sql").read()):
    con.execute(shim(s))
print(f"Views created ({len(re.findall('CREATE VIEW', open(f'{SQL}/03_views.sql').read()))}) in {time.time() - t0:.1f}s")

# procedures
proc_txt = re.sub(r"--[^\n]*", "", open(f"{SQL}/04_stored_procedures.sql").read())
PROCS = {}
for name, params, body in re.findall(r"CREATE PROCEDURE\s+(\w+)\s*\((.*?)\)\s*BEGIN(.*?)\bEND\s*//", proc_txt, re.S):
    pnames = re.findall(r"IN\s+(p_\w+)\s+\w+", params)
    b = body
    for p in pnames:
        b = re.sub(rf"\b{p}\b", f":{p}", b)
    PROCS[name] = (pnames, [shim(x) for x in [s.strip() for s in b.split(";")] if x])
print("Procedures parsed:", ", ".join(PROCS))

def call(name, *args):
    pnames, stmts = PROCS[name]
    params = dict(zip(pnames, args))
    results = []
    for s in stmts:
        if s.lstrip().upper().startswith("SELECT"):
            results.append(run_select(s, params))
        else:
            con.execute(s, params)
    return results

def save(df, name):
    df.to_csv(f"{RES}/{name}.csv", index=False)
    print(f"  {name:34s} {len(df):>7,d} rows")

# ----------------------------------------------------------------------------- run everything
AS_OF = con.execute("SELECT MAX(week_end) FROM fact_inventory_weekly").fetchone()[0]
FIRST = con.execute("SELECT MIN(week_start) FROM fact_inventory_weekly").fetchone()[0]
LAST_WK = con.execute("SELECT MAX(week_start) FROM fact_inventory_weekly").fetchone()[0]
print(f"\nas-of {AS_OF}; window {FIRST} .. {LAST_WK}\nRunning procedures...")

def timed(label, fn):
    t = time.time()
    r = fn()
    print(f"[{time.time() - t:5.1f}s] {label}")
    return r

r = timed("sp_regional_kpis", lambda: call("sp_regional_kpis", FIRST, LAST_WK))
save(r[0], "kpi_by_warehouse"); save(r[1], "po_perf_by_warehouse")

r = timed("sp_stock_deficit_alerts", lambda: call("sp_stock_deficit_alerts", AS_OF))
save(r[0], "stock_deficit_alerts")

r = timed("sp_pipeline_delay_alerts", lambda: call("sp_pipeline_delay_alerts", AS_OF))
save(r[0], "pipeline_delay_alerts")

r = timed("sp_stockout_root_cause", lambda: call("sp_stockout_root_cause", FIRST, LAST_WK))
save(r[0], "rca_cause_summary"); save(r[1], "rca_warehouse_matrix")
save(r[2], "rca_factor_overlap"); save(r[3], "rca_events")

r = timed("sp_excess_inventory_waste", lambda: call("sp_excess_inventory_waste", AS_OF))
save(r[0], "excess_by_warehouse"); save(r[1], "excess_by_category"); save(r[2], "excess_lines")

r = timed("sp_regional_rebalance", lambda: call("sp_regional_rebalance", AS_OF))
save(r[0], "rebalance_transfers"); save(r[1], "rebalance_flows")

r = timed("sp_asset_waste_rca", lambda: call("sp_asset_waste_rca", "2024-10-01", "2026-09-01"))
save(r[0], "asset_rca_detail"); save(r[1], "asset_rca_warehouse")

r = timed("sp_generate_alerts", lambda: call("sp_generate_alerts", AS_OF))
save(r[0], "alert_summary")
save(run_select("SELECT * FROM alert_log ORDER BY alert_id"), "alert_log")

# time-travel check: the as-of logic must work for a historical date too
hist = "2026-01-04"
h = call("sp_generate_alerts", hist)[0]
print(f"  time-travel alerts as of {hist}: {int(h['alerts'].sum())} alerts")
con.execute("DELETE FROM alert_log WHERE as_of_date = ?", (hist,))   # keep alert_log = latest only

save(run_select("SELECT * FROM vw_supplier_scorecard ORDER BY on_time_pct"), "supplier_scorecard")

# ad-hoc analysis queries
qtxt = open(f"{SQL}/05_analysis_queries.sql").read()
blocks = re.split(r"(?m)^-- (Q\d+): ", qtxt)[1:]
print("Analysis queries:")
for qid, rest in zip(blocks[0::2], blocks[1::2]):
    title, _, remainder = rest.partition("\n")
    stmt = statements(remainder)[0]
    df = run_select(shim(stmt))
    df.to_csv(f"{OUT}/queries/{qid}.csv", index=False)
    print(f"  {qid}: {title[:70]:70s} {len(df):>4d} rows")

# flat extracts for Tableau / Excel
print("Flat extracts:")
save(run_select("SELECT * FROM vw_stock_status_all ORDER BY week_start, warehouse_id, sku_id"), "tableau_inventory_weekly")
save(run_select("SELECT * FROM vw_po_enriched ORDER BY po_id"), "tableau_purchase_orders")
save(run_select("SELECT * FROM vw_asset_monthly_enriched ORDER BY month_start, asset_id"), "tableau_asset_monthly")

print("\nDone. Results are in outputs/sql_results and outputs/queries.")
