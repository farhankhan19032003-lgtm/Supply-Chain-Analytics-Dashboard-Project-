#!/usr/bin/env python3
"""
07_tableau_extracts_and_previews.py
  1. writes the Tableau-ready CSV extracts to tableau/extracts/
  2. renders four dashboard PREVIEW images to tableau/previews/ from the same numbers
     (matplotlib renders of what the Tableau dashboards should show - they are not Tableau output).
Palette: validated reference palette (blue = base series, orange = emphasis on problem sites).
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R, Q, D = f"{ROOT}/outputs/sql_results", f"{ROOT}/outputs/queries", f"{ROOT}/data/clean"
EX, PV = f"{ROOT}/tableau/extracts", f"{ROOT}/tableau/previews"
os.makedirs(EX, exist_ok=True); os.makedirs(PV, exist_ok=True)

# ------------------------------------------------------------------------------------ extracts
inv = pd.read_csv(f"{R}/tableau_inventory_weekly.csv")
for c in ["avg_demand_4w", "weeks_of_cover"]:
    inv[c] = inv[c].round(2)
for c in ["stock_value_inr", "cogs_inr", "lost_revenue_inr", "lost_margin_inr"]:
    inv[c] = inv[c].round(0)
inv.to_csv(f"{EX}/inventory_weekly.csv", index=False)
pd.read_csv(f"{R}/tableau_purchase_orders.csv").to_csv(f"{EX}/purchase_orders.csv", index=False)
pd.read_csv(f"{R}/tableau_asset_monthly.csv").round(2).to_csv(f"{EX}/asset_monthly.csv", index=False)
for src, dst in [("alert_log", "alerts"), ("rca_events", "rca_events"), ("supplier_scorecard", "supplier_scorecard"),
                 ("excess_lines", "excess_lines"), ("rebalance_transfers", "rebalance_transfers"),
                 ("asset_rca_detail", "asset_rca_detail"), ("kpi_by_warehouse", "warehouse_kpis")]:
    pd.read_csv(f"{R}/{src}.csv").to_csv(f"{EX}/{dst}.csv", index=False)
pd.read_csv(f"{D}/dim_warehouse.csv").to_csv(f"{EX}/warehouse_geo.csv", index=False)
pd.read_csv(f"{D}/dim_week.csv").to_csv(f"{EX}/dim_week.csv", index=False)
for f in sorted(os.listdir(EX)):
    print(f"  extract {f:28s} {os.path.getsize(f'{EX}/{f}') / 1e6:6.1f} MB")

# ------------------------------------------------------------------------------------ style
BLUE, ORANGE, INK, SEC, MUTED, GRID, SURF = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "figure.facecolor": SURF, "axes.facecolor": SURF,
                     "axes.edgecolor": "#c3c2b7", "axes.labelcolor": SEC, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False})
SEQ = LinearSegmentedColormap.from_list("seq", ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])

def ttl(ax, text, sub=None):
    ax.set_title(text, loc="left", fontsize=10.5, fontweight="bold", color=INK, pad=14 if sub else 8)
    if sub:
        ax.text(0, 1.015, sub, transform=ax.transAxes, fontsize=8, color=SEC, va="bottom")

def hbar(ax, labels, vals, hi=None, fmt="{:,.1f}", xlabel=None):
    hi = hi if hi is not None else [False] * len(vals)
    y = np.arange(len(vals))
    ax.barh(y, vals, color=[ORANGE if h else BLUE for h in hi], height=0.62)
    ax.set_yticks(y); ax.set_yticklabels(labels, color=SEC); ax.invert_yaxis()
    ax.xaxis.grid(True, color=GRID, lw=0.6); ax.set_axisbelow(True)
    mx = max(vals) if len(vals) else 1
    for yi, v in zip(y, vals):
        ax.text(v + mx * 0.012, yi, fmt.format(v), va="center", fontsize=8, color=INK)
    ax.set_xlim(0, mx * 1.16)
    if xlabel: ax.set_xlabel(xlabel)
    ax.tick_params(axis="y", length=0)

def save(fig, name):
    fig.savefig(f"{PV}/{name}", dpi=130, facecolor=SURF, bbox_inches="tight")
    plt.close(fig)
    print("  preview", name)

# ------------------------------------------------------------------------------------ data
wk = pd.read_csv(f"{R}/kpi_by_warehouse.csv")
wk["lost_pct"] = 100 - wk["fill_rate_pct"]
q6 = pd.read_csv(f"{Q}/Q6.csv")
last = inv[inv["week_end"] == inv["week_end"].max()]
weekly = inv.groupby("week_start").agg(d=("demand_units", "sum"), s=("units_sold", "sum")).reset_index()
weekly["fill"] = 100 * weekly.s / weekly.d
weekly["dt"] = pd.to_datetime(weekly["week_start"])
reg = inv.groupby("region")["lost_revenue_inr"].sum().sort_values(ascending=False) / 1e7
name = dict(zip(wk.warehouse_id, wk.warehouse_name.str.replace(" DC", "")))

# ---- Dashboard 1: executive overview
fig, ax = plt.subplots(2, 2, figsize=(14, 8.4))
fig.suptitle("1  Executive overview - the network is stocked in the wrong places", x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
a = wk.sort_values("lost_pct", ascending=False)
hbar(ax[0, 0], [name[w] for w in a.warehouse_id], a.lost_pct.values, (a.lost_pct > 5).values, "{:.1f}%", "% of demand not served")
ttl(ax[0, 0], "Chennai and Guwahati lose 11-12% of demand", "Demand lost to stock-outs, 104 weeks")
b = q6.sort_values("pct_of_network_stock", ascending=False)
y = np.arange(len(b)); h = 0.38
ax[0, 1].barh(y - h / 2, b.pct_of_network_stock, h, color=BLUE, label="Share of network stock value")
ax[0, 1].barh(y + h / 2, b.pct_of_network_demand, h, color=ORANGE, label="Share of network demand (at cost)")
ax[0, 1].set_yticks(y); ax[0, 1].set_yticklabels([name[w] for w in b.warehouse_id], color=SEC); ax[0, 1].invert_yaxis()
ax[0, 1].xaxis.grid(True, color=GRID, lw=0.6); ax[0, 1].set_axisbelow(True); ax[0, 1].tick_params(axis="y", length=0)
for yi, v1, v2 in zip(y, b.pct_of_network_stock, b.pct_of_network_demand):
    ax[0, 1].text(v1 + 0.4, yi - h / 2, f"{v1:.1f}%", va="center", fontsize=7.5, color=INK)
    ax[0, 1].text(v2 + 0.4, yi + h / 2, f"{v2:.1f}%", va="center", fontsize=7.5, color=INK)
ax[0, 1].legend(frameon=False, loc="lower right", fontsize=8, labelcolor=SEC)
top2 = b.head(2)
ttl(ax[0, 1], f"Bhiwandi + Gurugram hold {top2.pct_of_network_stock.sum():.0f}% of stock for {top2.pct_of_network_demand.sum():.0f}% of demand", "Latest week")
wkp = weekly.iloc[3:]                      # first 3 weeks excluded: opening-stock seeding artefact
ax[1, 0].plot(wkp.dt, wkp.fill, color=BLUE, lw=2)
c = pd.Timestamp("2025-10-20") - pd.Timedelta(days=10)
ax[1, 0].axvspan(c - pd.Timedelta(days=10), c + pd.Timedelta(days=10), color=GRID, alpha=0.8, lw=0)
ax[1, 0].text(c, 99.0, "Diwali build-up", ha="center", fontsize=7.5, color=SEC)
ax[1, 0].set_ylim(92, 99.5); ax[1, 0].yaxis.grid(True, color=GRID, lw=0.6); ax[1, 0].set_ylabel("Fill rate %")
ttl(ax[1, 0], f"Fill rate fell to {wkp.fill.min():.1f}% in the 2025 Diwali build-up", "Weekly units sold / units demanded (first 3 weeks excluded: opening-stock seeding)")
hbar(ax[1, 1], reg.index.tolist(), reg.values, (reg.index == "South").tolist() if False else None, "INR {:.1f} Cr", "INR crore")
ttl(ax[1, 1], "South and East carry most of the lost revenue", "Revenue lost to stock-outs by region, 104 weeks")
fig.tight_layout(rect=[0, 0, 1, 0.96]); save(fig, "dashboard1_executive_overview.png")

# ---- Dashboard 2: inventory health
fig, ax = plt.subplots(1, 2, figsize=(14, 6.2), gridspec_kw={"width_ratios": [1.25, 1]})
fig.suptitle("2  Inventory health and stock-deficit alerts (latest week)", x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
last = last.assign(deficit=last.stock_status.isin(["STOCKOUT", "CRITICAL", "LOW"]).astype(int))
hm = (100 * last.pivot_table(index="warehouse_name", columns="category", values="deficit", aggfunc="mean")).round(0)
hm.index = [i.replace(" DC", "") for i in hm.index]; short = {"Beverages": "Beverages", "Electronics Accessories": "Electronics", "Home Care": "Home Care", "OTC Pharma & Wellness": "OTC Pharma", "Packaged Staples": "Staples", "Packaging & Supplies": "Packaging", "Personal Care": "Personal\nCare", "Snacks & Confectionery": "Snacks"}
hm.columns = [short[c] for c in hm.columns]
order = hm.mean(axis=1).sort_values(ascending=False).index
hm = hm.loc[order]
im = ax[0].imshow(hm.values, cmap=SEQ, aspect="auto", vmin=0, vmax=100)
ax[0].set_xticks(range(hm.shape[1])); ax[0].set_xticklabels(hm.columns, fontsize=7.5, color=SEC)
ax[0].set_yticks(range(hm.shape[0])); ax[0].set_yticklabels(hm.index, color=SEC)
ax[0].xaxis.tick_top(); ax[0].tick_params(length=0)
for sp in ax[0].spines.values(): sp.set_visible(False)
for i in range(hm.shape[0]):
    for j in range(hm.shape[1]):
        v = hm.values[i, j]; ax[0].text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8, color="white" if v > 45 else INK)
ax[0].set_title("Share of SKU lines in deficit, % (STOCKOUT / CRITICAL / LOW)", loc="left", fontsize=10.5, fontweight="bold", color=INK, pad=34)
t10 = pd.read_csv(f"{R}/stock_deficit_alerts.csv").head(10)
hbar(ax[1], [f"{r.warehouse_name.replace(' DC', '')} - {r.sku_name}" for r in t10.itertuples()],
     (t10.weekly_margin_at_risk_inr / 1e3).values, None, "INR {:,.0f}k", "INR thousand per week")
ttl(ax[1], "Top 10 stocked-out lines by weekly margin at risk", "All are STOCKOUT status; ranked by avg weekly demand x unit margin")
fig.tight_layout(rect=[0, 0, 1, 0.95]); save(fig, "dashboard2_inventory_health_alerts.png")

# ---- Dashboard 3: supplier & pipeline
fig, ax = plt.subplots(1, 2, figsize=(14, 6.4))
fig.suptitle("3  Pipeline and supplier performance", x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
s = pd.read_csv(f"{R}/supplier_scorecard.csv").sort_values("on_time_pct")
hbar(ax[0], s.supplier_name.tolist(), s.on_time_pct.values, (s.on_time_pct < 55).tolist(), "{:.0f}%", "On-time delivery % (PO received on or before promise date)")
ttl(ax[0], "Four suppliers deliver on time less than half the time", "Received POs, 104 weeks")
q2 = pd.read_csv(f"{Q}/Q2.csv")
q2 = q2.iloc[1:-1].copy()                  # first / last months are partial (simulation start-up, 4 days of Oct-26)
q2["m"] = pd.to_datetime(q2.receipt_month + "-01")
ax[1].plot(q2.m, q2.on_time_pct, color=BLUE, lw=2, marker="o", ms=4)
for yr in (2025, 2026):
    ax[1].axvspan(pd.Timestamp(f"{yr}-07-01"), pd.Timestamp(f"{yr}-09-30"), color=GRID, alpha=0.8, lw=0)
    ax[1].text(pd.Timestamp(f"{yr}-08-15"), q2.on_time_pct.max() + 1, "Monsoon", ha="center", fontsize=8, color=SEC)
ax[1].set_ylim(55, q2.on_time_pct.max() + 4); ax[1].yaxis.grid(True, color=GRID, lw=0.6); ax[1].set_ylabel("On-time %")
ttl(ax[1], "On-time delivery falls in monsoon months", "All suppliers, by month received (partial first/last months excluded)")
fig.tight_layout(rect=[0, 0, 1, 0.95]); save(fig, "dashboard3_pipeline_supplier.png")

# ---- Dashboard 4: root cause & waste
fig, ax = plt.subplots(2, 2, figsize=(14, 8.4))
fig.suptitle("4  Root cause and operational waste", x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
cs = pd.read_csv(f"{R}/rca_cause_summary.csv")
labs = [c.split(" ", 1)[1].replace(" (reorder point too low)", "\n(reorder point too low)").replace(" / thin safety stock", "\n/ thin safety stock") for c in cs.primary_cause]
c2 = cs.assign(l=labs).sort_values("lost_revenue_inr", ascending=False)
hbar(ax[0, 0], c2.l.tolist(), (c2.lost_revenue_inr / 1e7).values, None, "INR {:.1f} Cr", "INR crore lost revenue")
ttl(ax[0, 0], "Supplier delay and planning-policy gaps explain 70% of lost sales", "Primary cause of each stock-out event, 104 weeks")
ex = pd.read_csv(f"{R}/excess_by_warehouse.csv").sort_values("above_target_cover_value_inr", ascending=False)
hbar(ax[0, 1], [w.replace(" DC", "") for w in ex.warehouse_name], (ex.above_target_cover_value_inr / 1e7).values, (ex.warehouse_id.isin(["WH01", "WH04"])).tolist(), "INR {:.2f} Cr", "INR crore")
ttl(ax[0, 1], "Stock above 4 weeks of cover sits in Bhiwandi and Gurugram", "Value above target cover, latest week")
ar = pd.read_csv(f"{R}/asset_rca_warehouse.csv").sort_values("idle_cost_inr", ascending=False)
hbar(ax[1, 0], [w.replace(" DC", "") for w in ar.warehouse_name], (ar.idle_cost_inr / 1e5).values, ar.warehouse_id.isin(["WH05", "WH02"]).tolist(), "INR {:.0f} L", "INR lakh, 24 months")
ttl(ax[1, 0], "Pune and Jaipur fleets sit idle", "Idle-asset cost (ownership + share of operator cost)")
ax[1, 1].scatter(ar.utilisation_pct, ar.downtime_pct, s=46, color=BLUE, zorder=3)
for r in ar.itertuples():
    if r.warehouse_id in ("WH05", "WH02", "WH08", "WH10", "WH03", "WH11"):
        ax[1, 1].annotate(r.warehouse_name.replace(" DC", ""), (r.utilisation_pct, r.downtime_pct), xytext=(6, 4), textcoords="offset points", fontsize=8, color=INK)
ax[1, 1].set_xlabel("Utilisation % (run hours / scheduled)"); ax[1, 1].set_ylabel("Downtime %")
ax[1, 1].grid(True, color=GRID, lw=0.6); ax[1, 1].set_axisbelow(True)
ttl(ax[1, 1], "Kolkata and Lucknow: ageing fleets; Chennai: overstretched", "Warehouse fleets, 24 months")
fig.tight_layout(rect=[0, 0, 1, 0.96]); save(fig, "dashboard4_root_cause_waste.png")
