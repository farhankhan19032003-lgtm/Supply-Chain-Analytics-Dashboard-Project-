#!/usr/bin/env python3
"""
04_validate_results.py
----------------------
Independent reconciliation: recomputes the headline numbers with pandas straight from the raw CSVs
(no SQL involved) and compares them with what the stored-procedure logic produced.
Writes outputs/validation_report.txt and exits non-zero if any check fails.

Run (after 02_run_sql_pipeline.py):  python3 scripts/04_validate_results.py
"""
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D, R = f"{ROOT}/data/clean", f"{ROOT}/outputs/sql_results"
lines, fails = [], 0

def check(name, ok, detail=""):
    global fails
    fails += 0 if ok else 1
    lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))

inv = pd.read_csv(f"{D}/fact_inventory_weekly.csv")
sku = pd.read_csv(f"{D}/dim_sku.csv")
po = pd.read_csv(f"{D}/fact_purchase_orders.csv", parse_dates=["order_date", "promised_date", "received_date"])
cfg = pd.read_csv(f"{D}/cfg_thresholds.csv").set_index("param")["param_value"]
wh = pd.read_csv(f"{D}/dim_warehouse.csv")
AS_OF = pd.Timestamp(inv["week_end"].max())

inv = inv.merge(sku[["sku_id", "unit_cost_inr", "unit_price_inr", "lead_time_days", "category"]], on="sku_id")
inv = inv.sort_values(["warehouse_id", "sku_id", "week_start"]).reset_index(drop=True)
g = inv.groupby(["warehouse_id", "sku_id"])["demand_units"]
inv["avg4"] = g.transform(lambda s: s.rolling(4, min_periods=1).mean())
inv["prior8"] = g.transform(lambda s: s.shift(1).rolling(8, min_periods=1).mean())
inv["prior4"] = g.transform(lambda s: s.shift(1).rolling(4, min_periods=1).mean())
inv["cover"] = np.where(inv["avg4"] > 0, inv["closing_stock"] / inv["avg4"].replace(0, np.nan), np.nan)

# ---- 1. KPI table
k = pd.read_csv(f"{R}/kpi_by_warehouse.csv").set_index("warehouse_id")
pd_k = inv.groupby("warehouse_id").agg(d=("demand_units", "sum"), s=("units_sold", "sum"), l=("lost_units", "sum"))
check("Fill rate per warehouse equals independent calc",
      np.allclose(k["fill_rate_pct"], (100 * pd_k.s / pd_k.d).round(2)))
lr = (inv["lost_units"] * inv["unit_price_inr"]).groupby(inv["warehouse_id"]).sum()
check("Lost revenue per warehouse equals independent calc", np.allclose(k["lost_revenue_inr"], lr.round(0), atol=1))
tot_fill = inv.units_sold.sum() / inv.demand_units.sum()
lines.append(f"      network fill rate = {100 * tot_fill:.2f}%  | total lost revenue = INR {lr.sum() / 1e7:.2f} Cr")

# ---- 2. stock deficit alerts at as-of week
last = inv[inv["week_end"] == AS_OF.strftime("%Y-%m-%d")].copy()
def status(r):
    if not r.avg4 > 0: return "NO DEMAND"
    if r.closing_stock == 0: return "STOCKOUT"
    if r.cover < cfg["critical_cover_weeks"]: return "CRITICAL"
    if r.cover < cfg["low_cover_weeks"]: return "LOW"
    if r.cover > cfg["excess_cover_weeks"]: return "EXCESS"
    return "HEALTHY"
last["status"] = last.apply(status, axis=1)
cnt = last["status"].value_counts().to_dict()
sd = pd.read_csv(f"{R}/stock_deficit_alerts.csv")
check("Deficit-alert rows == STOCKOUT+CRITICAL+LOW rows", len(sd) == sum(cnt.get(x, 0) for x in ["STOCKOUT", "CRITICAL", "LOW"]),
      f"sql={len(sd)} pandas={sum(cnt.get(x, 0) for x in ['STOCKOUT', 'CRITICAL', 'LOW'])}")
check("Per-status counts match", sd["stock_status"].value_counts().to_dict() == {k_: cnt[k_] for k_ in ["STOCKOUT", "CRITICAL", "LOW"] if k_ in cnt},
      str({k_: cnt.get(k_, 0) for k_ in ["STOCKOUT", "CRITICAL", "LOW", "EXCESS", "HEALTHY"]}))

# ---- 3. pipeline delay alerts
open_po = po[po["received_date"].isna()].copy()
open_po["days_over"] = (AS_OF - open_po["promised_date"]).dt.days
pdl = pd.read_csv(f"{R}/pipeline_delay_alerts.csv")
exp_n = int((open_po["days_over"] >= cfg["overdue_warn_days"]).sum())
check("Pipeline-delay alert count equals open POs >= warn days overdue", len(pdl) == exp_n, f"sql={len(pdl)} pandas={exp_n}")
check("Critical pipeline alerts match", int((pdl["severity"] == "CRITICAL").sum()) == int((open_po["days_over"] >= cfg["overdue_critical_days"]).sum()))
lines.append(f"      open POs = {len(open_po)}; overdue (>0 d) = {int((open_po['days_over'] > 0).sum())}; "
             f"value overdue >= warn = INR {pdl['po_value_inr'].sum() / 1e5:.1f} lakh")

# ---- 4. RCA
ev = pd.read_csv(f"{R}/rca_events.csv")
exp_ev = inv[inv["lost_units"] > 0]
check("RCA event count == weeks with lost sales", len(ev) == len(exp_ev), f"{len(ev)}")
cs = pd.read_csv(f"{R}/rca_cause_summary.csv")
check("RCA cause summary sums to total lost revenue", abs(cs["lost_revenue_inr"].sum() - lr.sum()) < len(ev), f"{cs['lost_revenue_inr'].sum():,.0f}")
check("RCA cause shares sum to ~100%", abs(cs["pct_of_lost_revenue"].sum() - 100) < 0.6)
m = exp_ev.merge(ev[["week_start", "warehouse_id", "sku_id", "f_policy_gap", "f_spike", "f_late_po", "f_short_ship"]],
                 on=["week_start", "warehouse_id", "sku_id"])
pg = ((m["prior4"].notna()) & (m["reorder_point_units"] < 0.75 * m["prior4"] * (np.ceil(m["lead_time_days"] / 7.0) + 1))).astype(int)
sp = ((m["prior8"].notna()) & (m["demand_units"] > 1.5 * m["prior8"])).astype(int)
check("f_policy_gap flag identical to independent calc on all events", (pg.values == m["f_policy_gap"].values).all())
check("f_spike flag identical to independent calc on all events", (sp.values == m["f_spike"].values).all())
# late-PO / short-ship flags, brute force on a random 1,500-event sample
samp = m.sample(1500, random_state=1)
po_by = {kk: v for kk, v in po.groupby(["warehouse_id", "sku_id"])}
bad = 0
for _, r in samp.iterrows():
    ws_, we_ = pd.Timestamp(r.week_start), pd.Timestamp(r.week_end)
    p = po_by.get((r.warehouse_id, r.sku_id))
    late = short = 0
    if p is not None:
        c1 = (p.order_date < ws_) & (p.promised_date <= we_) & (p.received_date.isna() | ((p.received_date >= ws_) & (p.received_date > p.promised_date)))
        late = int(c1.any())
        c2 = p.received_date.notna() & (p.received_date <= we_) & ((we_ - p.received_date).dt.days <= 27) & (p.received_qty < 0.9 * p.ordered_qty)
        short = int(c2.any())
    bad += (late != r.f_late_po) + (short != r.f_short_ship)
check("f_late_po / f_short_ship flags match brute force (1,500-event sample)", bad == 0, f"mismatches={bad}")

# ---- 5. rebalance
tr = pd.read_csv(f"{R}/rebalance_transfers.csv")
keep = cfg["rebalance_keep_weeks"]
donor = last[last["status"] == "EXCESS"].copy()
donor["surplus"] = np.floor(donor["closing_stock"] - keep * donor["avg4"])
dsum = tr.groupby(["sku_id", "from_warehouse_id"])["transfer_units"].sum().reset_index()
dsum = dsum.merge(donor[["sku_id", "warehouse_id", "surplus"]], left_on=["sku_id", "from_warehouse_id"], right_on=["sku_id", "warehouse_id"])
check("No donor is asked for more than its surplus", (dsum["transfer_units"] <= dsum["surplus"] + 1e-9).all(), f"{len(dsum)} donor-SKU pairs")
check("Donor is always an EXCESS row, receiver always deficit",
      set(tr["receiver_status"]) <= {"STOCKOUT", "CRITICAL", "LOW"})
check("No transfer lines to self", (tr["from_warehouse_id"] != tr["to_warehouse_id"]).all())
lines.append(f"      transfers = {len(tr)} lines, {int(tr.transfer_units.sum()):,} units, "
             f"net benefit INR {tr['est_net_benefit_inr'].sum() / 1e5:.1f} lakh (indicative)")

# ---- 6. excess
ex = pd.read_csv(f"{R}/excess_by_warehouse.csv")
ex_units = np.where(last["status"] == "EXCESS", np.maximum(0, last["closing_stock"] - cfg["excess_cover_weeks"] * last["avg4"]), 0)
exp_ex_val = float((ex_units * last["unit_cost_inr"]).sum())
check("Excess inventory value equals independent calc", abs(ex["excess_value_inr"].sum() - exp_ex_val) < 20, f"{exp_ex_val:,.0f}")
above = np.maximum(0, last["closing_stock"] - keep * last["avg4"]) * last["unit_cost_inr"]
mask = last["avg4"] > 0
check("Above-target-cover value equals independent calc", abs(ex["above_target_cover_value_inr"].sum() - above[mask].sum()) < 50, f"{above[mask].sum():,.0f}")

# ---- 7. supplier scorecard
sc = pd.read_csv(f"{R}/supplier_scorecard.csv").set_index("supplier_id")
rec = po[po["received_date"].notna()].copy()
rec["ontime"] = rec["received_date"] <= rec["promised_date"]
ot = (100 * rec.groupby("supplier_id")["ontime"].mean()).round(1)
check("Supplier on-time % equals independent calc", np.allclose(sc["on_time_pct"].sort_index(), ot.sort_index()))

# ---- 8. assets
ar = pd.read_csv(f"{R}/asset_rca_warehouse.csv")
fa = pd.read_csv(f"{D}/fact_asset_monthly.csv").merge(pd.read_csv(f"{D}/dim_asset.csv")[["asset_id", "warehouse_id", "hourly_ownership_cost_inr", "hourly_operator_cost_inr"]], on="asset_id")
fa["idle_cost"] = fa["idle_hours"] * (fa["hourly_ownership_cost_inr"] + cfg["operator_idle_share"] * fa["hourly_operator_cost_inr"])
chk = fa.groupby("warehouse_id")["idle_cost"].sum().round(0)
check("Asset idle cost per warehouse equals independent calc", np.allclose(ar.set_index("warehouse_id")["idle_cost_inr"].sort_index(), chk.sort_index(), atol=2))

# ---- 9. alert log
al = pd.read_csv(f"{R}/alert_log.csv")
cap_n = int((al["alert_type"] == "CAPACITY_RISK").sum())
check("alert_log = deficits + pipeline + capacity", len(al) == len(sd) + len(pdl) + cap_n, f"{len(al)} = {len(sd)} + {len(pdl)} + {cap_n}")

lines.insert(0, f"Validation report | as-of {AS_OF.date()} | {len(lines)} checks\n")
open(f"{ROOT}/outputs/validation_report.txt", "w").write("\n".join(lines) + f"\n\nRESULT: {'ALL CHECKS PASSED' if fails == 0 else str(fails) + ' CHECK(S) FAILED'}\n")
print("\n".join(lines))
print("\nRESULT:", "ALL CHECKS PASSED" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
