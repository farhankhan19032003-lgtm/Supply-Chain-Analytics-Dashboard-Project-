#!/usr/bin/env python3
"""
08_build_dashboards.py
----------------------
Builds dashboards/index.html: the four dashboards from tableau/TABLEAU_BUILD_GUIDE.md as one self-contained
HTML page (inline SVG, no internet needed). Numbers come from the verified outputs of scripts 01-07.

Run:  python scripts/08_build_dashboards.py
"""
import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX, RES = f"{ROOT}/tableau/extracts", f"{ROOT}/outputs/sql_results"
OUT = f"{ROOT}/dashboards"
os.makedirs(OUT, exist_ok=True)

CR = 1e7
DEFICIT = ["STOCKOUT", "CRITICAL", "LOW"]


def rd(path, **kw):
    return pd.read_csv(path, **kw)


# ----------------------------------------------------------------------------------- inventory (D1, D2)
inv = rd(f"{EX}/inventory_weekly.csv", usecols=[
    "week_start", "week_end", "warehouse_id", "warehouse_name", "region", "latitude", "longitude", "category",
    "demand_units", "units_sold", "lost_revenue_inr", "stock_value_inr", "stock_status"])
latest_end = inv["week_end"].max()
lat = inv[inv["week_end"] == latest_end]
lat_deficit = lat[lat["stock_status"].isin(DEFICIT)]
print("latest week_end", latest_end, "| deficit lines", len(lat_deficit), "of", len(lat))

fill_all = inv["units_sold"].sum() / inv["demand_units"].sum() * 100
lost_cr = inv["lost_revenue_inr"].sum() / CR
stock_cr = lat["stock_value_inr"].sum() / CR

wk = inv.groupby("week_start")[["units_sold", "demand_units"]].sum()
weekly = [{"x": d, "y": round(r.units_sold / r.demand_units * 100, 2)} for d, r in wk.iterrows()]

kpi = rd(f"{RES}/kpi_by_warehouse.csv")
dem_share = inv.groupby("warehouse_id")["demand_units"].sum()
stk_share = lat.groupby("warehouse_id")["stock_value_inr"].sum()
deficit_wh = lat_deficit.groupby("warehouse_id").size()
lines_wh = lat.groupby("warehouse_id").size()
geo = rd(f"{EX}/warehouse_geo.csv").set_index("warehouse_id")
wh = []
for _, r in kpi.iterrows():
    w = r.warehouse_id
    wh.append({
        "id": w, "name": r.warehouse_name, "region": r.region, "fill": float(r.fill_rate_pct),
        "lost_pct": round(100 - float(r.fill_rate_pct), 2), "lost_cr": round(r.lost_revenue_inr / CR, 2),
        "stock_share": round(stk_share[w] / stk_share.sum() * 100, 1),
        "demand_share": round(dem_share[w] / dem_share.sum() * 100, 1),
        "stock_cr": round(stk_share[w] / CR, 2),
        "deficit_pct": round(deficit_wh.get(w, 0) / lines_wh[w] * 100, 1),
        "lat": float(geo.loc[w, "latitude"]), "lon": float(geo.loc[w, "longitude"])})

cats = sorted(lat["category"].unique())
whs_sorted = [w["name"] for w in sorted(wh, key=lambda z: -z["deficit_pct"])]
heat = []
for name in whs_sorted:
    row = []
    for c in cats:
        sub = lat[(lat.warehouse_name == name) & (lat.category == c)]
        d = sub["stock_status"].isin(DEFICIT).sum()
        row.append(round(d / len(sub) * 100, 1) if len(sub) else None)
    heat.append(row)

statuses = ["STOCKOUT", "CRITICAL", "LOW", "HEALTHY", "EXCESS"]
regions = sorted(lat["region"].unique())
mix = {s: [int(((lat.region == rg) & (lat.stock_status == s)).sum()) for rg in regions] for s in statuses}

deficits = rd(f"{RES}/stock_deficit_alerts.csv").sort_values("weekly_margin_at_risk_inr", ascending=False)
actions = [[r.warehouse_name, r.sku_name, r.stock_status, r.weeks_of_cover, int(r.closing_stock),
            int(r.inbound_open_qty), r.inbound_risk, round(r.weekly_margin_at_risk_inr / 1000, 1)]
           for r in deficits.head(25).itertuples()]

# ----------------------------------------------------------------------------------- pipeline (D3)
sup = rd(f"{RES}/supplier_scorecard.csv").sort_values("on_time_pct")
suppliers = [{"name": r.supplier_name, "tier": r.supplier_tier, "ontime": float(r.on_time_pct),
              "overdue": int(r.overdue_open_pos)} for r in sup.itertuples()]

po = rd(f"{EX}/purchase_orders.csv", parse_dates=["order_date", "promised_date", "received_date"])
rec = po[po["received_date"].notna()].copy()
rec["m"] = rec["received_date"].dt.to_period("M")
months = sorted(rec["m"].unique())[1:-1]                      # drop the partial first and last month
mo = rec.groupby("m")["on_time_flag"].mean() * 100
ontime_m = [{"x": str(m), "y": round(mo[m], 1)} for m in months]

rec["prom"] = (rec["promised_date"] - rec["order_date"]).dt.days
rec["act"] = (rec["received_date"] - rec["order_date"]).dt.days
lt = rec.groupby(["supplier_id", "supplier_name"]).agg(prom=("prom", "mean"), act=("act", "mean"),
                                                         val=("po_value_inr", "sum")).reset_index()
leadtime = [{"name": r.supplier_name, "x": round(r.prom, 1), "y": round(r.act, 1), "v": round(r.val / CR, 1)}
            for r in lt.itertuples()]

od = rd(f"{RES}/pipeline_delay_alerts.csv").sort_values("days_overdue", ascending=False)
overdue = [[r.po_id, r.supplier_name, r.warehouse_name, r.sku_name, int(r.days_overdue),
            round(r.po_value_inr / 1e5, 1), r.severity] for r in od.head(25).itertuples()]
overdue_n, overdue_crit = len(od), int((od.severity == "CRITICAL").sum())
overdue_val = od.po_value_inr.sum() / CR

# ----------------------------------------------------------------------------------- root cause & waste (D4)
causes = rd(f"{RES}/rca_cause_summary.csv")
cause_rows = [{"name": r.primary_cause[2:], "cr": round(r.lost_revenue_inr / CR, 2), "pct": float(r.pct_of_lost_revenue)}
              for r in causes.itertuples()]
cause_names = [c["name"] for c in cause_rows]
rca = rd(f"{EX}/rca_events.csv", usecols=["week_start", "lost_revenue_inr", "primary_cause"], parse_dates=["week_start"])
rca["m"] = rca["week_start"].dt.to_period("M").astype(str)
rca["c"] = rca["primary_cause"].str[2:]
pv = rca.pivot_table(index="m", columns="c", values="lost_revenue_inr", aggfunc="sum", fill_value=0) / CR
rca_months = list(pv.index)
rca_series = [[round(float(pv.loc[m, c]) if c in pv.columns else 0, 3) for m in rca_months] for c in cause_names]

ex = rd(f"{RES}/excess_by_warehouse.csv").sort_values("above_target_cover_value_inr", ascending=False)
excess = [{"name": r.warehouse_name, "cr": round(r.above_target_cover_value_inr / CR, 2),
           "pct": float(r.above_target_pct_of_stock)} for r in ex.itertuples()]

ast = rd(f"{RES}/asset_rca_warehouse.csv")
assets = [{"name": r.warehouse_name, "util": float(r.utilisation_pct), "down": float(r.downtime_pct),
           "idle_cr": round(r.idle_cost_inr / CR, 2), "surplus": int(r.net_surplus_assets)} for r in ast.itertuples()]

tr = rd(f"{RES}/rebalance_transfers.csv").sort_values("est_net_benefit_inr", ascending=False)
transfers = [[r.sku_name, r.from_warehouse, r.to_warehouse, int(r.transfer_units), r.receiver_status,
              round(r.est_net_benefit_inr / 1e5, 2)] for r in tr.head(15).itertuples()]
tr_all = dict(n=len(tr), units=int(tr.transfer_units.sum()), benefit_l=round(tr.est_net_benefit_inr.sum() / 1e5, 1))

alerts = rd(f"{RES}/alert_summary.csv")
alert_rows = [[r.alert_type, r.severity, int(r.alerts)] for r in alerts.itertuples()]

D = dict(
    asof=str(latest_end), fill=round(fill_all, 2), lost_cr=round(lost_cr, 1), stock_cr=round(stock_cr, 1),
    deficit=int(len(lat_deficit)), lines=int(len(lat)), wh=wh, weekly=weekly, cats=cats, heat_wh=whs_sorted,
    heat=heat, regions=regions, statuses=statuses, mix=mix, actions=actions, suppliers=suppliers,
    ontime_m=ontime_m, leadtime=leadtime, overdue=overdue, overdue_n=overdue_n, overdue_crit=overdue_crit,
    overdue_val=round(overdue_val, 2), causes=cause_rows, rca_months=rca_months, rca_series=rca_series,
    excess=excess, assets=assets, transfers=transfers, tr_all=tr_all, alerts=alert_rows)

html = open(f"{ROOT}/scripts/dashboard_template.html", encoding="utf-8").read()
html = html.replace("/*__DATA__*/null", json.dumps(D, default=str))
open(f"{OUT}/index.html", "w", encoding="utf-8").write(html)
print(f"wrote {OUT}/index.html  ({os.path.getsize(OUT + '/index.html') / 1024:.0f} KB)")
