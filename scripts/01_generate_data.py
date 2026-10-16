#!/usr/bin/env python3
"""
01_generate_data.py
-------------------
Builds the SIMULATED nationwide (India) FMCG / consumer-goods distribution dataset used by the
Supply Chain Analytics Platform project.

Why simulated?  Real warehouse-level inventory, PO and asset logs are proprietary and are not
published openly. This generator reproduces the *mechanics* of a real distribution network
(replenishment policy, supplier lead-time variability, festive/monsoon seasonality, regional
misalignment, ageing assets) so the SQL / Power Query / Tableau work on top of it is realistic.

Output (data/clean/):
  dim_warehouse.csv, dim_sku.csv, dim_supplier.csv, dim_week.csv, dim_asset.csv
  fact_inventory_weekly.csv, fact_purchase_orders.csv, fact_asset_monthly.csv
  cfg_thresholds.csv

Usage:  python3 01_generate_data.py <output_dir>
Deterministic: fixed seed -> identical files every run.
"""
import math
import os
import sys

import numpy as np
import pandas as pd

SEED = 2026
OUT = sys.argv[1] if len(sys.argv) > 1 else "data/clean"
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(SEED)

START = np.datetime64("2024-10-07")            # a Monday
N_WEEKS = 104                                    # Oct-2024 .. Sep-2026
WEEK_START = START + np.arange(N_WEEKS) * np.timedelta64(7, "D")
WEEK_END = WEEK_START + np.timedelta64(6, "D")
AS_OF = WEEK_END[-1]                              # 2026-10-04

# --------------------------------------------------------------------------------------
# 1. Warehouses  (12 regional DCs).  policy_factor = how aggressively the local planner
#    sets reorder points (1.0 = neutral).  <1 => chronic under-stocking, >1 => over-stocking.
#    These "planted" misalignments are what the SQL root-cause procedures later discover.
# --------------------------------------------------------------------------------------
WH = [
    # id,   name,           city,        state,           region,   lat,     lon,     scale, policy, target_util
    ("WH01", "Gurugram DC", "Gurugram", "Haryana", "North", 28.4595, 77.0266, 1.30, 1.75, 0.84),
    ("WH02", "Jaipur DC", "Jaipur", "Rajasthan", "North", 26.9124, 75.7873, 0.70, 1.00, 0.66),
    ("WH03", "Lucknow DC", "Lucknow", "Uttar Pradesh", "North", 26.8467, 80.9462, 0.80, 1.00, 0.70),
    ("WH04", "Bhiwandi DC", "Bhiwandi", "Maharashtra", "West", 19.2813, 73.0483, 1.60, 1.85, 0.88),
    ("WH05", "Pune DC", "Pune", "Maharashtra", "West", 18.5204, 73.8567, 0.90, 1.10, 0.68),
    ("WH06", "Ahmedabad DC", "Ahmedabad", "Gujarat", "West", 23.0225, 72.5714, 1.00, 1.00, 0.72),
    ("WH07", "Bengaluru DC", "Bengaluru", "Karnataka", "South", 12.9716, 77.5946, 1.30, 1.00, 0.74),
    ("WH08", "Chennai DC", "Chennai", "Tamil Nadu", "South", 13.0827, 80.2707, 1.10, 0.62, 0.55),
    ("WH09", "Hyderabad DC", "Hyderabad", "Telangana", "South", 17.3850, 78.4867, 1.10, 1.00, 0.72),
    ("WH10", "Kolkata DC", "Kolkata", "West Bengal", "East", 22.5726, 88.3639, 1.00, 0.90, 0.64),
    ("WH11", "Guwahati DC", "Guwahati", "Assam", "East", 26.1445, 91.7362, 0.45, 0.58, 0.50),
    ("WH12", "Nagpur DC", "Nagpur", "Maharashtra", "Central", 21.1458, 79.0882, 0.60, 1.00, 0.70),
]
wh = pd.DataFrame(WH, columns=["warehouse_id", "warehouse_name", "city", "state", "region",
                               "latitude", "longitude", "scale", "policy_factor", "target_util"])
REGIONS = ["North", "West", "South", "East", "Central"]
wh_region_idx = wh["region"].map({r: i for i, r in enumerate(REGIONS)}).values
W = len(wh)

# --------------------------------------------------------------------------------------
# 2. SKU master  (120 SKUs, 8 categories x 15).  Generic product names (no brands).
# --------------------------------------------------------------------------------------
CATS = {
    "Packaged Staples": dict(
        names=["Atta 5kg", "Basmati Rice 5kg", "Toor Dal 1kg", "Moong Dal 1kg", "Sunflower Oil 1L",
               "Mustard Oil 1L", "Sugar 1kg", "Iodized Salt 1kg", "Tea Leaves 500g", "Poha 500g",
               "Besan 1kg", "Rajma 1kg", "Jaggery 1kg", "Ghee 500ml", "Suji 1kg"],
        cost=(40, 300), margin=0.12, dem=(300, 900), lead=(5, 10), shelf=270, cv=0.22, case=12, festive=0.15,
        season=[1.0, .97, .97, .98, .98, .98, 1.0, 1.0, 1.02, 1.08, 1.06, 1.03]),
    "Beverages": dict(
        names=["Cola 750ml", "Lemon Soda 600ml", "Mango Drink 1L", "Packaged Water 1L", "Energy Drink 250ml",
               "Fruit Juice 1L", "Iced Tea 500ml", "Coconut Water 200ml", "Instant Coffee 100g",
               "Tea Bags 100pk", "Buttermilk 200ml", "Lassi 200ml", "Sports Drink 500ml",
               "Tonic Water 300ml", "Malt Drink 500g"],
        cost=(15, 120), margin=0.18, dem=(400, 1200), lead=(4, 8), shelf=180, cv=0.28, case=24, festive=0.10,
        season=[.80, .90, 1.20, 1.45, 1.55, 1.30, .95, .90, .95, .95, .85, .80]),
    "Snacks & Confectionery": dict(
        names=["Potato Chips 90g", "Namkeen Mix 400g", "Glucose Biscuits 300g", "Cream Biscuits 120g",
               "Chocolate Bar 40g", "Instant Noodles 70g", "Popcorn 60g", "Peanut Chikki 200g",
               "Cookies 200g", "Wafers 75g", "Mathri 250g", "Dry Fruit Mix 250g", "Soan Papdi 500g",
               "Rusk 300g", "Candy Pack 150g"],
        cost=(10, 150), margin=0.22, dem=(300, 1000), lead=(5, 9), shelf=120, cv=0.26, case=12, festive=0.45,
        season=[.95, .95, .95, .95, .95, .95, .98, 1.0, 1.02, 1.05, 1.05, 1.0]),
    "Personal Care": dict(
        names=["Shampoo 340ml", "Soap 4-pack", "Toothpaste 150g", "Face Wash 100ml", "Body Lotion 400ml",
               "Hair Oil 200ml", "Deodorant 150ml", "Sanitary Pads 20pk", "Razor 5pk", "Talc 300g",
               "Sunscreen 50g", "Hand Wash 250ml", "Kajal Pack", "Lip Balm", "Mouthwash 250ml"],
        cost=(30, 400), margin=0.30, dem=(150, 500), lead=(7, 14), shelf=540, cv=0.25, case=12, festive=0.25,
        season=[1.05, 1.05, 1.0, .95, .95, .95, .95, .98, 1.02, 1.08, 1.10, 1.10]),
    "Home Care": dict(
        names=["Detergent Powder 2kg", "Dishwash Liquid 750ml", "Floor Cleaner 1L", "Toilet Cleaner 500ml",
               "Glass Cleaner 500ml", "Fabric Softener 1L", "Mosquito Coil 10pk", "Air Freshener 250ml",
               "Garbage Bags 30pk", "Scrub Pad 3pk", "Bleach 500ml", "Phenyl 1L", "Agarbatti 100pk",
               "Matchbox 10pk", "Naphthalene Balls 200g"],
        cost=(40, 350), margin=0.25, dem=(150, 450), lead=(7, 12), shelf=720, cv=0.22, case=12, festive=0.35,
        season=[.95, .95, 1.0, 1.0, 1.0, .98, .98, 1.0, 1.02, 1.05, 1.0, .95]),
    "Electronics Accessories": dict(
        names=["USB-C Cable 1m", "Fast Charger 25W", "Power Bank 10000mAh", "Wired Earphones", "TWS Earbuds",
               "Bluetooth Speaker", "Phone Case", "Screen Guard", "LED Bulb 9W", "Extension Board 4-socket",
               "AA Batteries 10pk", "SD Card 64GB", "Wireless Mouse", "USB Keyboard", "HDMI Cable 2m"],
        cost=(150, 2500), margin=0.28, dem=(40, 160), lead=(14, 30), shelf=0, cv=0.38, case=10, festive=1.10,
        season=[.85, .85, .85, .90, .90, .90, .95, 1.0, 1.0, 1.0, 1.0, 1.0]),
    "OTC Pharma & Wellness": dict(
        names=["Paracetamol 500mg 15s", "ORS Sachets 10pk", "Antacid Syrup 200ml", "Cough Syrup 100ml",
               "Multivitamin 30s", "Antiseptic Liquid 250ml", "Pain Balm 50g", "Bandage Pack",
               "Digital Thermometer", "Glucose Powder 500g", "Vitamin C 30s", "Eye Drops 10ml",
               "Zinc Tablets 20s", "Hand Sanitizer 500ml", "Face Masks 50pk"],
        cost=(25, 600), margin=0.32, dem=(80, 300), lead=(10, 18), shelf=365, cv=0.34, case=12, festive=0.0,
        season=[1.15, 1.0, .90, .90, .95, 1.0, 1.25, 1.35, 1.25, .95, .95, 1.15]),
    "Packaging & Supplies": dict(
        names=["Corrugated Box 12x12", "Stretch Film 500mm", "BOPP Tape 48mm", "Bubble Wrap Roll",
               "Pallet Strapping Roll", "Shipping Labels 1000", "Poly Mailer 100pk", "Void Fill Paper",
               "Cable Ties 100pk", "Edge Protectors 50pk", "Pallet Wrap Hand", "Courier Bags 100pk",
               "Thermal Paper Roll 20pk", "Safety Gloves 12pk", "Cutter Blades 10pk"],
        cost=(20, 800), margin=0.20, dem=(60, 250), lead=(10, 21), shelf=0, cv=0.24, case=20, festive=0.25,
        season=[.95, .95, .95, .95, .95, .95, 1.0, 1.0, 1.05, 1.10, 1.10, 1.0]),
}
CAT_LIST = list(CATS)

# --------------------------------------------------------------------------------------
# 3. Suppliers (22 fictional firms, 2-3 per category).  4 are chronically unreliable.
# --------------------------------------------------------------------------------------
SUP = [
    # name, category, origin_city, origin_region, delay_prob, avg_delay_days, shortship_prob
    ("Shree Ganesh Agro Foods", "Packaged Staples", "Indore", "Central", 0.14, 3.0, 0.05),
    ("Annapurna Staples Pvt Ltd", "Packaged Staples", "Kanpur", "North", 0.22, 4.0, 0.08),
    ("Kisan Mill Traders", "Packaged Staples", "Kolkata", "East", 0.52, 7.0, 0.16),   # BAD
    ("Coastal Beverages Co", "Beverages", "Kochi", "South", 0.12, 2.5, 0.04),
    ("Himalayan Spring Bottlers", "Beverages", "Dehradun", "North", 0.20, 3.5, 0.06),
    ("Sunrise Fruit Drinks", "Beverages", "Nashik", "West", 0.28, 4.0, 0.09),
    ("Crunchy Bite Foods", "Snacks & Confectionery", "Ahmedabad", "West", 0.15, 3.0, 0.05),
    ("Mithaiwala Confectionery", "Snacks & Confectionery", "Jaipur", "North", 0.24, 4.0, 0.07),
    ("Namkeen Nation Pvt Ltd", "Snacks & Confectionery", "Bikaner", "North", 0.18, 3.0, 0.06),
    ("Glow Naturals Care", "Personal Care", "Mumbai", "West", 0.13, 3.0, 0.04),
    ("Ayur Beauty Labs", "Personal Care", "Hyderabad", "South", 0.26, 4.5, 0.08),
    ("PureSkin Personal Care", "Personal Care", "Baddi", "North", 0.48, 8.0, 0.15),   # BAD
    ("CleanSwift Home Products", "Home Care", "Pune", "West", 0.16, 3.0, 0.05),
    ("Sparkle Household Ltd", "Home Care", "Vapi", "West", 0.21, 3.5, 0.07),
    ("TechNest Accessories", "Electronics Accessories", "Noida", "North", 0.30, 5.0, 0.10),
    ("VoltEdge Electronics", "Electronics Accessories", "Chennai", "South", 0.19, 4.0, 0.06),
    ("ConnectPro Gadgets", "Electronics Accessories", "Shenzhen-Imports Mumbai", "West", 0.55, 9.0, 0.18),  # BAD
    ("VitaCare Pharma Distributors", "OTC Pharma & Wellness", "Ahmedabad", "West", 0.14, 3.0, 0.04),
    ("MediTrust Healthcare", "OTC Pharma & Wellness", "Hyderabad", "South", 0.23, 4.0, 0.07),
    ("WellSpring OTC Pvt Ltd", "OTC Pharma & Wellness", "Guwahati", "East", 0.30, 5.0, 0.09),
    ("PackWell Industries", "Packaging & Supplies", "Faridabad", "North", 0.20, 3.5, 0.06),
    ("SafeShip Packaging", "Packaging & Supplies", "Coimbatore", "South", 0.46, 6.5, 0.14),  # BAD
]
sup = pd.DataFrame(SUP, columns=["supplier_name", "category", "origin_city", "origin_region",
                                 "delay_prob", "avg_delay_days", "shortship_prob"])
sup.insert(0, "supplier_id", [f"SUP{i + 1:02d}" for i in range(len(sup))])
sup["origin_city"] = sup["origin_city"].replace({"Shenzhen-Imports Mumbai": "Mumbai"})
sup["supplier_tier"] = np.where(sup["delay_prob"] < 0.20, "Tier 1", np.where(sup["delay_prob"] < 0.35, "Tier 2", "Tier 3"))
sup["payment_terms_days"] = rng.choice([30, 45, 60], size=len(sup), p=[.4, .4, .2])

# --------------------------------------------------------------------------------------
# 4. SKU rows
# --------------------------------------------------------------------------------------
rows = []
sid = 0
for cat, c in CATS.items():
    cat_sups = sup[sup["category"] == cat]["supplier_id"].tolist()
    for nm in c["names"]:
        sid += 1
        cost = float(np.round(np.exp(rng.uniform(math.log(c["cost"][0]), math.log(c["cost"][1]))), 0))
        price = float(np.round(cost * (1 + c["margin"] * rng.uniform(0.85, 1.15)), 0))
        rows.append(dict(
            sku_id=f"SKU{sid:03d}", sku_name=nm, category=cat,
            unit_cost_inr=cost, unit_price_inr=price,
            base_weekly_demand=float(np.round(rng.uniform(*c["dem"]), 0)),
            lead_time_days=int(rng.integers(c["lead"][0], c["lead"][1] + 1)),
            shelf_life_days=c["shelf"], case_pack=c["case"],
            primary_supplier_id=str(rng.choice(cat_sups)),
        ))
sku = pd.DataFrame(rows)
S = len(sku)
cat_idx = sku["category"].map({c: i for i, c in enumerate(CAT_LIST)}).values
sup_idx_map = {s: i for i, s in enumerate(sup["supplier_id"])}
sku_sup_idx = sku["primary_supplier_id"].map(sup_idx_map).values

# --------------------------------------------------------------------------------------
# 5. Demand model
# --------------------------------------------------------------------------------------
P = W * S
pair_wh = np.repeat(np.arange(W), S)
pair_sku = np.tile(np.arange(S), W)

aff = rng.uniform(0.75, 1.35, size=(len(REGIONS), len(CAT_LIST)))      # region x category affinity
aff[2, 1] = 1.40   # South loves beverages
aff[3, 0] = 1.25   # East staples
aff[1, 7] = 1.35   # West packaging (industrial belt)
pair_noise = np.exp(rng.normal(0, 0.22, size=P))
slow_mask = rng.random(P) < 0.14                                        # slow-moving pairs
slow_factor = np.where(slow_mask, 0.22, 1.0)

base_mu = (sku["base_weekly_demand"].values[pair_sku]
           * wh["scale"].values[pair_wh]
           * aff[wh_region_idx[pair_wh], cat_idx[pair_sku]]
           * pair_noise * slow_factor)

DIWALI = [np.datetime64(d) for d in ("2024-11-01", "2025-10-20", "2026-11-08")]
mid = WEEK_START + np.timedelta64(3, "D")
months = (mid.astype("datetime64[M]").astype(int) % 12)                 # 0..11
festive_prox = np.zeros(N_WEEKS)
for d in DIWALI:
    centre = d - np.timedelta64(10, "D")                                # pre-Diwali buying peak
    z = (mid - centre).astype("timedelta64[D]").astype(float) / 9.0
    festive_prox += np.exp(-0.5 * z ** 2)

season = np.zeros((N_WEEKS, len(CAT_LIST)))
for ci, cat in enumerate(CAT_LIST):
    c = CATS[cat]
    season[:, ci] = np.array(c["season"])[months] * (1 + c["festive"] * festive_prox)
trend = 1 + 0.10 * np.arange(N_WEEKS) / 52.0

# --------------------------------------------------------------------------------------
# 6. Replenishment simulation (s,S policy with regional policy_factor)
# --------------------------------------------------------------------------------------
sup_region_idx = sup["origin_region"].map({r: i for i, r in enumerate(REGIONS)}).values
cross_region = (sup_region_idx[sku_sup_idx[pair_sku]] != wh_region_idx[pair_wh]).astype(int)
guwahati = (wh["warehouse_id"].values[pair_wh] == "WH11").astype(int)
lead_days = sku["lead_time_days"].values[pair_sku] + 3 * cross_region + 3 * guwahati
lead_w = np.ceil(lead_days / 7.0)
pf = wh["policy_factor"].values[pair_wh] * np.exp(rng.normal(0, 0.06, size=P))
case = sku["case_pack"].values[pair_sku].astype(float)
moq = np.ceil(sku["base_weekly_demand"].values[pair_sku] * 3.0 / case) * case
cv = np.array([CATS[CAT_LIST[c]]["cv"] for c in cat_idx[pair_sku]])
unit_cost = sku["unit_cost_inr"].values[pair_sku]
sup_p = sup["delay_prob"].values[sku_sup_idx[pair_sku]]
sup_d = sup["avg_delay_days"].values[sku_sup_idx[pair_sku]]
sup_ss = sup["shortship_prob"].values[sku_sup_idx[pair_sku]]

MONSOON_UPLIFT = np.array([1.20, 1.40, 1.15, 1.60, 1.30])               # N, W, S, E, C  (Jul-Sep)
wh_id_arr = wh["warehouse_id"].values[pair_wh]

def delay_prob(week_idx):
    """probability that a PO placed in this week arrives late"""
    m = int(months[week_idx]) + 1
    p = sup_p.copy()
    if m in (7, 8, 9):
        p = p * MONSOON_UPLIFT[wh_region_idx[pair_wh]]
    if m in (10, 11, 12):                                               # NE monsoon, Chennai
        p = np.where(wh_id_arr == "WH08", p * 1.5, p)
    p = np.where(wh_id_arr == "WH11", p * 1.3, p)                       # long NE lanes
    return np.clip(p, 0, 0.95)

PIPE_LEN = N_WEEKS + 20
ord_pipe = np.zeros((PIPE_LEN, P))
rec_pipe = np.zeros((PIPE_LEN, P))

hist = np.zeros((N_WEEKS, P))
mu0 = base_mu * trend[0] * season[0, cat_idx[pair_sku]]
on_hand = np.round(mu0 * (lead_w + 3) * rng.uniform(0.8, 1.3, size=P))
on_order = np.zeros(P)

inv_rec, po_rec = [], []
for t in range(N_WEEKS):
    opening = on_hand.copy()
    receipts = rec_pipe[t]
    on_hand = on_hand + receipts
    on_order = on_order - ord_pipe[t]

    mu_t = base_mu * trend[t] * season[t, cat_idx[pair_sku]]
    k = 1.0 / (cv ** 2)
    demand = rng.poisson(rng.gamma(k, mu_t / k)).astype(float)
    sold = np.minimum(on_hand, demand)
    lost = demand - sold
    on_hand = on_hand - sold
    hist[t] = demand

    # planner forecast = trailing-6-week mean demand (seeded with initial mean in early weeks)
    n = min(t + 1, 6)
    fc = (hist[t - n + 1: t + 1].sum(axis=0) + (6 - n) * mu0) / 6.0
    rop = pf * fc * (lead_w + 1.0)
    S_up = pf * fc * (lead_w + 1.0 + 3.0)

    # order decision at end of week t -> PO dated in week t+1
    if t + 1 < N_WEEKS:
        pos = on_hand + on_order
        need = pos <= rop
        qty = np.maximum(S_up - pos, moq)
        qty = np.ceil(qty / case) * case
        qty = np.where(need, qty, 0.0)
        idx = np.nonzero(need)[0]
        if len(idx):
            dp = delay_prob(t + 1)
            delayed = rng.random(len(idx)) < dp[idx]
            dly = np.where(delayed, 1 + np.round(rng.gamma(2.0, sup_d[idx] / 2.0)), 0).astype(int)
            off = rng.integers(0, 2, size=len(idx))
            odate = WEEK_START[t + 1] + off.astype("timedelta64[D]")
            prom = odate + lead_days[idx].astype("timedelta64[D]")
            act = prom + dly.astype("timedelta64[D]")
            q = qty[idx]
            short = rng.random(len(idx)) < sup_ss[idx]
            qrec = np.where(short, np.floor(q * rng.uniform(0.70, 0.95, size=len(idx)) / case[idx]) * case[idx], q)
            arr_w = ((act - START).astype("timedelta64[D]").astype(int)) // 7
            for j, p_i in enumerate(idx):
                if arr_w[j] < PIPE_LEN:
                    ord_pipe[arr_w[j], p_i] += q[j]
                    rec_pipe[arr_w[j], p_i] += qrec[j]
            on_order[idx] += q
            po_rec.append(pd.DataFrame(dict(
                pair=idx, order_date=odate, promised_date=prom, actual_date=act,
                ordered_qty=q.astype(int), received_qty=qrec.astype(int), delay_days=dly)))

    inv_rec.append(pd.DataFrame(dict(
        t=t, pair=np.arange(P), opening=opening.astype(int), receipts=receipts.astype(int),
        demand=demand.astype(int), sold=sold.astype(int), lost=lost.astype(int),
        closing=on_hand.astype(int), on_order=on_order.astype(int),
        rop=np.round(rop).astype(int), fc=np.round(fc, 1))))

inv = pd.concat(inv_rec, ignore_index=True)
po = pd.concat(po_rec, ignore_index=True)

# --------------------------------------------------------------------------------------
# 7. Assemble fact_inventory_weekly
# --------------------------------------------------------------------------------------
fact_inv = pd.DataFrame(dict(
    week_start=pd.to_datetime(WEEK_START[inv["t"].values]).strftime("%Y-%m-%d"),
    week_end=pd.to_datetime(WEEK_END[inv["t"].values]).strftime("%Y-%m-%d"),
    warehouse_id=wh["warehouse_id"].values[pair_wh[inv["pair"].values]],
    sku_id=sku["sku_id"].values[pair_sku[inv["pair"].values]],
    opening_stock=inv["opening"], receipts=inv["receipts"], demand_units=inv["demand"],
    units_sold=inv["sold"], lost_units=inv["lost"], closing_stock=inv["closing"],
    on_order_units=inv["on_order"], reorder_point_units=inv["rop"], forecast_weekly_units=inv["fc"]))

# --------------------------------------------------------------------------------------
# 8. Purchase orders
# --------------------------------------------------------------------------------------
po = po.sort_values(["order_date", "pair"]).reset_index(drop=True)
open_mask = po["actual_date"] > AS_OF
cost_noise = rng.uniform(0.97, 1.03, size=len(po))
fact_po = pd.DataFrame(dict(
    po_id=[f"PO{i + 1:07d}" for i in range(len(po))],
    warehouse_id=wh["warehouse_id"].values[pair_wh[po["pair"].values]],
    sku_id=sku["sku_id"].values[pair_sku[po["pair"].values]],
    supplier_id=sup["supplier_id"].values[sku_sup_idx[pair_sku[po["pair"].values]]],
    order_date=pd.to_datetime(po["order_date"]).dt.strftime("%Y-%m-%d"),
    promised_date=pd.to_datetime(po["promised_date"]).dt.strftime("%Y-%m-%d"),
    received_date=np.where(open_mask, "", pd.to_datetime(po["actual_date"]).dt.strftime("%Y-%m-%d")),
    ordered_qty=po["ordered_qty"],
    received_qty=np.where(open_mask, 0, po["received_qty"]),
    unit_cost_inr=np.round(unit_cost[po["pair"].values] * cost_noise, 2)))
fact_po["po_value_inr"] = np.round(fact_po["ordered_qty"] * fact_po["unit_cost_inr"], 2)

# --------------------------------------------------------------------------------------
# 9. ABC classification + warehouse capacity (post-hoc, so utilisation is plausible)
# --------------------------------------------------------------------------------------
rev = (fact_inv.groupby("sku_id")["units_sold"].sum() * sku.set_index("sku_id")["unit_price_inr"]).sort_values(ascending=False)
cum = rev.cumsum() / rev.sum()
abc = np.where(cum <= 0.70, "A", np.where(cum <= 0.90, "B", "C"))
abc_map = dict(zip(rev.index, abc))
sku["abc_class"] = sku["sku_id"].map(abc_map)

avg_units = fact_inv.groupby(["week_start", "warehouse_id"])["closing_stock"].sum().groupby("warehouse_id").mean()
wh["capacity_units"] = [int(round(avg_units[w] / u, -3)) for w, u in zip(wh["warehouse_id"], wh["target_util"])]

# --------------------------------------------------------------------------------------
# 10. Assets (forklifts, trucks ...) and monthly usage
# --------------------------------------------------------------------------------------
fact_inv["month"] = fact_inv["week_start"].str.slice(0, 7)
wh_month_units = fact_inv.groupby(["warehouse_id", "month"])["units_sold"].sum().unstack(fill_value=0)
MONTHS = list(wh_month_units.columns)                                    # 24 months
avg_month_units = wh_month_units.mean(axis=1)

ASSET_TYPES = {
    "Forklift (Electric)": dict(rated=400, h=6.0, cost=(1100000, 1600000), life=10, op=150, repair=(18000, 45000), pm=6500, energy=55),
    "Reach Truck": dict(rated=400, h=4.0, cost=(2200000, 3200000), life=10, op=170, repair=(30000, 80000), pm=9000, energy=70),
    "Electric Pallet Jack": dict(rated=400, h=8.0, cost=(250000, 450000), life=8, op=110, repair=(6000, 18000), pm=2500, energy=25),
    "Conveyor Line": dict(rated=500, h=3.0, cost=(1800000, 4500000), life=15, op=60, repair=(25000, 90000), pm=12000, energy=90),
    "Delivery Truck": dict(rated=300, h=5.0, cost=(1900000, 2800000), life=9, op=220, repair=(20000, 70000), pm=8000, energy=420),
}
FLEET_MISALIGN = {"WH05": 1.9, "WH02": 1.7, "WH08": 0.60, "WH11": 0.65}   # over / under provisioned
OLD_FLEET = {"WH10": (2012, 2016), "WH03": (2013, 2017)}                  # ageing fleets
assets = []
aid = 0
for _, w in wh.iterrows():
    for tname, a in ASSET_TYPES.items():
        n = max(1, int(round(avg_month_units[w.warehouse_id] / 1000.0 * a["h"] / (a["rated"] * 0.70)
                             * FLEET_MISALIGN.get(w.warehouse_id, 1.0))))
        for _ in range(n):
            aid += 1
            yr_lo, yr_hi = OLD_FLEET.get(w.warehouse_id, (2018, 2024))
            pdate = pd.Timestamp(year=int(rng.integers(yr_lo, yr_hi + 1)), month=int(rng.integers(1, 13)), day=1)
            pc = float(np.round(rng.uniform(*a["cost"]), -3))
            assets.append(dict(
                asset_id=f"AST{aid:04d}", warehouse_id=w.warehouse_id, asset_type=tname,
                purchase_date=pdate.strftime("%Y-%m-%d"), purchase_cost_inr=pc,
                useful_life_years=a["life"], rated_hours_per_month=a["rated"],
                hourly_ownership_cost_inr=round(pc / (a["life"] * 12 * a["rated"]), 2),
                hourly_operator_cost_inr=a["op"]))
dim_asset = pd.DataFrame(assets)
n_by = dim_asset.groupby(["warehouse_id", "asset_type"]).size()

arows = []
for _, a in dim_asset.iterrows():
    spec = ASSET_TYPES[a.asset_type]
    n_peer = n_by[(a.warehouse_id, a.asset_type)]
    for m in MONTHS:
        m_ts = pd.Timestamp(m + "-01")
        age_y = (m_ts - pd.Timestamp(a.purchase_date)).days / 365.25
        load = wh_month_units.loc[a.warehouse_id, m] / 1000.0 * spec["h"] / n_peer * rng.uniform(0.92, 1.08)
        util = load / a.rated_hours_per_month
        dt_pct = np.clip(0.02 + 0.006 * age_y + 0.05 * max(0.0, util - 0.9) + rng.normal(0, 0.006), 0.005, 0.30)
        down = a.rated_hours_per_month * dt_pct
        run = min(load, a.rated_hours_per_month - down)
        idle = max(0.0, a.rated_hours_per_month - run - down)
        bd = int(rng.poisson(0.25 + 0.12 * age_y + 2.0 * max(0.0, util - 0.9)))
        maint = bd * rng.uniform(*spec["repair"]) + spec["pm"] * (1 + 0.04 * age_y)
        arows.append((a.asset_id, m + "-01", a.rated_hours_per_month, round(run, 1), round(idle, 1),
                      round(down, 1), bd, round(maint, 0), round(run * spec["energy"], 0)))
fact_asset = pd.DataFrame(arows, columns=["asset_id", "month_start", "scheduled_hours", "run_hours",
                                          "idle_hours", "downtime_hours", "breakdown_count",
                                          "maintenance_cost_inr", "energy_cost_inr"])

# --------------------------------------------------------------------------------------
# 11. dim_week + thresholds + exports
# --------------------------------------------------------------------------------------
ws = pd.to_datetime(WEEK_START)
mid_ts = ws + pd.Timedelta(days=3)
def season_tag(ts, fp):
    m = ts.month
    if fp > 0.35: return "Festive (Diwali)"
    if m in (7, 8, 9): return "Monsoon"
    if m in (3, 4, 5, 6): return "Summer"
    if m in (12, 1, 2): return "Winter"
    return "Regular"
dim_week = pd.DataFrame(dict(
    week_start=ws.strftime("%Y-%m-%d"), week_end=pd.to_datetime(WEEK_END).strftime("%Y-%m-%d"),
    week_no=np.arange(1, N_WEEKS + 1), calendar_year=mid_ts.year, month_no=mid_ts.month,
    month_name=mid_ts.strftime("%b"), quarter="Q" + mid_ts.quarter.astype(str),
    fiscal_year=np.where(mid_ts.month >= 4, "FY" + (mid_ts.year % 100 + 1).astype(str).str.zfill(2),
                         "FY" + (mid_ts.year % 100).astype(str).str.zfill(2)),
    season=[season_tag(t, f) for t, f in zip(mid_ts, festive_prox)]))

cfg = pd.DataFrame([
    ("critical_cover_weeks", 0.5, "Closing stock below this many weeks of demand = CRITICAL"),
    ("low_cover_weeks", 1.5, "Below this = LOW (deficit risk)"),
    ("excess_cover_weeks", 8.0, "Above this = EXCESS"),
    ("obsolete_cover_weeks", 20, "Cover above this many weeks = slow-moving / obsolescence risk"),
    ("expiry_cover_share", 0.5, "Cover (days) above this share of shelf life = expiry risk"),
    ("holding_cost_pct_annual", 0.22, "Annual inventory carrying cost as a fraction of stock value"),
    ("overdue_warn_days", 3, "Open PO this many days past promise = WARNING"),
    ("overdue_critical_days", 7, "Open PO this many days past promise = CRITICAL"),
    ("operator_idle_share", 0.25, "Share of operator cost wasted while an asset sits idle"),
    ("asset_idle_flag_pct", 0.40, "Idle hours / scheduled hours above this = over-provisioned"),
    ("asset_downtime_flag_pct", 0.07, "Downtime hours / scheduled hours above this = reliability problem"),
    ("asset_overstretch_util", 0.90, "Run hours / scheduled hours above this = under-provisioned"),
    ("asset_target_util", 0.70, "Target run-hour utilisation used to size the fleet"),
    ("rebalance_keep_weeks", 4, "Donor warehouses keep this many weeks of cover when transferring out"),
    ("rebalance_target_weeks", 3, "Receiving warehouses are topped up to this many weeks of cover"),
    ("transfer_cost_same_region_per_unit", 2.5, "Indicative freight INR/unit, same region"),
    ("transfer_cost_cross_region_per_unit", 6.0, "Indicative freight INR/unit, cross region"),
    ("capacity_warn_util", 0.80, "Warehouse storage utilisation warning level"),
    ("capacity_critical_util", 0.90, "Warehouse storage utilisation critical level"),
], columns=["param", "param_value", "description"])

wh_out = wh.drop(columns=["scale", "policy_factor", "target_util"])             # hide planted parameters
sup_out = sup.drop(columns=["delay_prob", "avg_delay_days", "shortship_prob"])  # hide planted parameters
sku_out = sku.copy()
fact_inv_out = fact_inv.drop(columns=["month"])

wh_out.to_csv(f"{OUT}/dim_warehouse.csv", index=False)
sku_out.to_csv(f"{OUT}/dim_sku.csv", index=False)
sup_out.to_csv(f"{OUT}/dim_supplier.csv", index=False)
dim_week.to_csv(f"{OUT}/dim_week.csv", index=False)
dim_asset.to_csv(f"{OUT}/dim_asset.csv", index=False)
cfg.to_csv(f"{OUT}/cfg_thresholds.csv", index=False)
fact_inv_out.to_csv(f"{OUT}/fact_inventory_weekly.csv", index=False)
fact_po.to_csv(f"{OUT}/fact_purchase_orders.csv", index=False)
fact_asset.to_csv(f"{OUT}/fact_asset_monthly.csv", index=False)

print("as_of:", str(AS_OF))
for name, df in [("dim_warehouse", wh_out), ("dim_sku", sku_out), ("dim_supplier", sup_out), ("dim_week", dim_week),
                 ("dim_asset", dim_asset), ("fact_inventory_weekly", fact_inv_out),
                 ("fact_purchase_orders", fact_po), ("fact_asset_monthly", fact_asset)]:
    print(f"{name:24s} {len(df):>8,d} rows")
print("open POs:", int(open_mask.sum()))
