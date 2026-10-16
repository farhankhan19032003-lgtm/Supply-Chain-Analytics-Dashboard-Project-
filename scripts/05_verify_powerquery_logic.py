#!/usr/bin/env python3
"""
05_verify_powerquery_logic.py
-----------------------------
Re-implements, step by step, what the Power Query (M) queries in powerquery/queries/ do, using pandas.
Purpose: (1) prove the cleaning RULES recover the original clean data exactly, and
         (2) write powerquery/expected_results.csv - the checksums you compare with after running the
             M queries in Excel (row count, sums, data-quality counts per region).

NOTE: this validates the logic, not the M syntax. Excel is the only thing that can run M.
"""
import os
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, CLEAN = f"{ROOT}/data/raw_regional_extracts", f"{ROOT}/data/clean"
STD = ["week_start_raw", "warehouse_raw", "sku_raw", "opening_stock", "receipts", "demand_units",
       "units_sold", "lost_units", "closing_stock"]

def rd(name, **kw):
    return pd.read_csv(f"{RAW}/{name}", dtype=str, keep_default_na=False, **kw)

def to_number(x):                       # fnToNumber
    t = str(x).strip()
    if t == "" or t.upper() in ("NA", "N/A") or t == "-":
        return np.nan
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return np.nan

def to_date(x, fmt):                    # fnToDate
    t = str(x).strip()
    if t == "":
        return pd.NaT
    if fmt == "yyyy-MM-dd":
        t = t[:10]
    py = {"dd-MM-yyyy": "%d-%m-%Y", "yyyy/MM/dd": "%Y/%m/%d", "dd-MMM-yyyy": "%d-%b-%Y",
          "dd/MM/yyyy": "%d/%m/%Y", "yyyy-MM-dd": "%Y-%m-%d"}[fmt]
    try:
        return pd.Timestamp(datetime.strptime(t, py))
    except ValueError:
        return pd.NaT

def standardize(src, fmt, region):      # fnStandardize
    d = src[STD].copy()
    d = d[~(d.apply(lambda c: c.str.strip()) == "").all(axis=1)]            # NonBlank
    d["week_start"] = d["week_start_raw"].map(lambda v: to_date(v, fmt))
    d["warehouse_key"] = d["warehouse_raw"].str.strip().str.upper()
    d["sku_id"] = d["sku_raw"].str.strip().str.upper()
    for c in ["opening_stock", "receipts", "demand_units", "units_sold", "lost_units", "closing_stock"]:
        d[c] = d[c].map(to_number)
    d["dq_lost_filled"] = (d["lost_units"].isna() & d["demand_units"].notna() & d["units_sold"].notna()).astype(int)
    d["lost_units"] = np.where(d["lost_units"].notna(), d["lost_units"], d["demand_units"] - d["units_sold"])
    d["dq_closing_repaired"] = (d["closing_stock"].isna() | (d["closing_stock"] < 0)).astype(int)
    d["closing_stock"] = np.where(d["dq_closing_repaired"] == 0, d["closing_stock"],
                                  d["opening_stock"] + d["receipts"] - d["units_sold"])
    d["region_extract"] = region
    d = d[d["week_start"].notna()]
    return d[["week_start", "warehouse_key", "sku_id", "opening_stock", "receipts", "demand_units", "units_sold",
              "lost_units", "closing_stock", "dq_lost_filled", "dq_closing_repaired", "region_extract"]]

def ren(df, mapping):
    return df.rename(columns=mapping)

north = standardize(ren(rd("North_Weekly_Stock_FY26.csv"), {"Wk Start": "week_start_raw", "WH Code": "warehouse_raw",
    "SKU Code": "sku_raw", "Opening Stock": "opening_stock", "Receipts": "receipts", "Demand": "demand_units",
    "Sold": "units_sold", "Lost": "lost_units", "Closing Stock": "closing_stock"}), "dd-MM-yyyy", "North")
west = standardize(ren(rd("West_Weekly_Stock_FY26.csv", skiprows=3), {"week_start": "week_start_raw", "warehouse": "warehouse_raw",
    "sku": "sku_raw", "open_qty": "opening_stock", "recv_qty": "receipts", "demand_qty": "demand_units",
    "sales_qty": "units_sold", "lost_qty": "lost_units", "close_qty": "closing_stock"}), "yyyy/MM/dd", "West")
south = standardize(ren(rd("South_Weekly_Stock_FY26.csv", sep=";"), {"Week": "week_start_raw", "Warehouse_ID": "warehouse_raw",
    "Item": "sku_raw", "Opening": "opening_stock", "Inbound": "receipts", "Demand": "demand_units",
    "Units Sold": "units_sold", "Lost Sales": "lost_units", "Closing": "closing_stock"}), "dd-MMM-yyyy", "South")
east = standardize(ren(rd("East_Weekly_Stock_FY26.csv"), {"SKU": "sku_raw", "Warehouse": "warehouse_raw",
    "Week Commencing": "week_start_raw", "Closing Stock": "closing_stock", "Units Sold": "units_sold", "Demand": "demand_units",
    "Lost Units": "lost_units", "Receipts": "receipts", "Opening Stock": "opening_stock"}), "dd/MM/yyyy", "East")
central = standardize(ren(rd("Central_Weekly_Stock_FY26.csv"), {"week_start": "week_start_raw", "warehouse_id": "warehouse_raw",
    "sku_id": "sku_raw"}), "yyyy-MM-dd", "Central")

staged = pd.concat([north, west, south, east, central], ignore_index=True)       # Inventory_Staged
clean = staged.drop_duplicates(["week_start", "warehouse_key", "sku_id"], keep="first")   # Table.Distinct

# masters
wbm = f"{RAW}/Master_Data_Raw.xlsx"
wh_m = pd.read_excel(wbm, sheet_name="Warehouse_Master", header=1)
sku_m = pd.read_excel(wbm, sheet_name="SKU_Master", header=2)
lk = pd.concat([pd.DataFrame({"warehouse_key": wh_m["Code"].str.upper(), "warehouse_id": wh_m["Code"].str.upper()}),
                pd.DataFrame({"warehouse_key": wh_m["Name"].str.upper(), "warehouse_id": wh_m["Code"].str.upper()})])
sku_m = sku_m.rename(columns={"SKU Code": "sku_id", "Unit Cost (INR)": "unit_cost_inr", "Unit Price (INR)": "unit_price_inr"})
sku_m["sku_id"] = sku_m["sku_id"].str.strip().str.upper()
clean = clean.merge(lk, on="warehouse_key", how="left").merge(sku_m[["sku_id", "unit_cost_inr", "unit_price_inr"]], on="sku_id", how="left")
clean["stock_value_inr"] = clean["closing_stock"] * clean["unit_cost_inr"]
clean["lost_revenue_inr"] = clean["lost_units"] * clean["unit_price_inr"]

# ------------------------------------------------------------------ compare with the original clean data
orig = pd.read_csv(f"{CLEAN}/fact_inventory_weekly.csv")
weeks = sorted(orig["week_start"].unique())[-52:]
orig = orig[orig["week_start"].isin(weeks)]
clean["week_start"] = clean["week_start"].dt.strftime("%Y-%m-%d")
m = orig.merge(clean, on=["week_start", "warehouse_id", "sku_id"], suffixes=("_o", "_c"), how="outer", indicator=True)
ok = True
print("Row count after cleaning:", len(clean), "| original:", len(orig))
print("Unmatched keys:", int((m["_merge"] != "both").sum()))
ok &= (m["_merge"] == "both").all()
for a, b in [("opening_stock_o", "opening_stock_c"), ("receipts_o", "receipts_c"), ("demand_units_o", "demand_units_c"),
             ("units_sold_o", "units_sold_c"), ("lost_units_o", "lost_units_c"), ("closing_stock_o", "closing_stock_c")]:
    mism = int((m[a] != m[b]).sum())
    print(f"  {a[:-2]:15s} mismatches vs original: {mism}")
    ok &= mism == 0
print("RESULT:", "cleaning logic reproduces the original data exactly" if ok else "MISMATCH")

# ------------------------------------------------------------------ expected checksums for Excel
dq = staged.groupby("region_extract").agg(rows_staged_non_blank=("sku_id", "size"),
                                          closing_stock_repaired=("dq_closing_repaired", "sum"),
                                          lost_units_filled=("dq_lost_filled", "sum"))
dq["rows_clean"] = clean.groupby("region_extract").size()
dq["duplicates_removed"] = dq["rows_staged_non_blank"] - dq["rows_clean"]
exp = pd.DataFrame({
    "metric": ["Inventory_Clean row count", "SUM(demand_units)", "SUM(units_sold)", "SUM(lost_units)",
               "SUM(closing_stock)", "SUM(stock_value_inr)", "SUM(lost_revenue_inr)", "Fill rate %"],
    "expected_value": [len(clean), clean.demand_units.sum(), clean.units_sold.sum(), clean.lost_units.sum(),
                       clean.closing_stock.sum(), round(clean.stock_value_inr.sum(), 2), round(clean.lost_revenue_inr.sum(), 2),
                       round(100 * clean.units_sold.sum() / clean.demand_units.sum(), 3)]})
os.makedirs(f"{ROOT}/powerquery", exist_ok=True)
exp.to_csv(f"{ROOT}/powerquery/expected_results.csv", index=False)
dq.reset_index().to_csv(f"{ROOT}/powerquery/expected_DQ_Log.csv", index=False)
print("\nExpected after running the M queries in Excel:")
print(exp.to_string(index=False))
print("\nExpected DQ_Log:")
print(dq.reset_index().to_string(index=False))
raise SystemExit(0 if ok else 1)
