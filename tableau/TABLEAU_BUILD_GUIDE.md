# Tableau Build Guide (≈ 60-90 minutes)

You will build **4 dashboards** and **2 alert rules**. No `.twbx` is shipped (Tableau workbooks cannot be authored
outside Tableau), so this guide gives every click-level decision plus the exact calculated fields.
`previews/*.png` show what each dashboard should look like - they are matplotlib renders of the same numbers,
not Tableau output, so your layout can differ.

Works in Tableau Desktop or Tableau Public (Public: no alerts, no live MySQL - use the CSV extracts).

## 1. Connect the data

**Option A - CSV extracts (simplest).** Folder `tableau/extracts/`. Create four data sources:

| Data source | Files | Join / relationship |
|---|---|---|
| **Inventory** | `inventory_weekly.csv` (149,760 rows) + `dim_week.csv` | relationship on `week_start` |
| **Pipeline** | `purchase_orders.csv` + `supplier_scorecard.csv` | `supplier_id` |
| **Root cause** | `rca_events.csv` | - |
| **Assets** | `asset_monthly.csv` + `asset_rca_detail.csv` | none needed; use separately |
| (Alerts, transfers, excess) | `alerts.csv`, `rebalance_transfers.csv`, `excess_lines.csv`, `warehouse_kpis.csv` | stand-alone |

**Option B - live MySQL.** Connect to `supply_chain_analytics` and drag in the views `vw_stock_status_all`,
`vw_po_enriched`, `vw_asset_monthly_enriched`, plus the `alert_log` table. Field names are the same
(Tableau shows `week_start` as "Week Start"). Use an extract for speed; refresh weekly.

**Set field roles:** `latitude` / `longitude` → Geographic role (Latitude / Longitude); `week_start`, `week_end` → Date;
`warehouse_id`, `sku_id`, `po_id` → String dimensions.

## 2. Parameters (make thresholds user-controllable)

| Parameter | Type | Default |
|---|---|---|
| `p_critical_cover` | Float | 0.5 |
| `p_low_cover` | Float | 1.5 |
| `p_excess_cover` | Float | 8 |
| `p_overdue_warn_days` | Integer | 3 |
| `p_overdue_critical_days` | Integer | 7 |

(Same defaults as `cfg_thresholds`. Right-click each → *Show Parameter*.)

## 3. Calculated fields

**Inventory data source**
```
// Is Latest Week
[Week End] = { MAX([Week End]) }

// Stockout Flag
IF [Lost Units] > 0 THEN 1 ELSE 0 END

// Fill Rate
SUM([Units Sold]) / SUM([Demand Units])

// Stockout Rate
SUM([Stockout Flag]) / COUNT([Sku Id])

// Weeks of Cover (line level, uses the 4-week average already in the extract)
IF [Avg Demand 4W] > 0 THEN [Closing Stock] / [Avg Demand 4W] END

// Dynamic Status  (re-classifies using the parameters)
IF [Avg Demand 4W] = 0 THEN "NO DEMAND"
ELSEIF [Closing Stock] = 0 THEN "STOCKOUT"
ELSEIF [Weeks of Cover] < [p_critical_cover] THEN "CRITICAL"
ELSEIF [Weeks of Cover] < [p_low_cover] THEN "LOW"
ELSEIF [Weeks of Cover] > [p_excess_cover] THEN "EXCESS"
ELSE "HEALTHY" END

// Deficit Flag
IF [Dynamic Status] = "STOCKOUT" OR [Dynamic Status] = "CRITICAL" OR [Dynamic Status] = "LOW" THEN 1 ELSE 0 END

// Deficit Lines (Latest Week)      <- the metric the stock-deficit alert watches
SUM(IF [Is Latest Week] THEN [Deficit Flag] ELSE 0 END)

// Deficit Lines % (Latest Week)
[Deficit Lines (Latest Week)] / SUM(IF [Is Latest Week] THEN 1 ELSE 0 END)

// Stock Value (Cr)
SUM(IF [Is Latest Week] THEN [Stock Value Inr] ELSE 0 END) / 10000000

// Lost Revenue (Cr)
SUM([Lost Revenue Inr]) / 10000000

// Network Stock Share %   (table calc: Compute using Warehouse Name)
[Stock Value (Cr)] / TOTAL([Stock Value (Cr)])
```

**Pipeline data source**
```
// On-Time %
SUM([On Time Flag]) / COUNT([On Time Flag])        // On Time Flag is blank for open POs, so COUNT = received POs

// Overdue Severity
IF [Overdue Open Flag] = 1 AND [Days Vs Promise] >= [p_overdue_critical_days] THEN "CRITICAL"
ELSEIF [Overdue Open Flag] = 1 AND [Days Vs Promise] >= [p_overdue_warn_days] THEN "WARNING"
END

// Overdue PO Value (INR)
SUM(IF [Overdue Severity] = "CRITICAL" OR [Overdue Severity] = "WARNING" THEN [Po Value Inr] END)

// Overdue PO Count
SUM(IF [Overdue Severity] = "CRITICAL" OR [Overdue Severity] = "WARNING" THEN 1 ELSE 0 END)
```
(For open POs `Days Vs Promise` already means "days past promise as of 4-Oct-2026".)

## 4. The four dashboards

Canvas 1400 × 900, floating titles. Palette: blue `#2a78d6` as the base colour, orange `#eb6834` **only** to
highlight problem sites; status colours (green/amber/red) only for stock-status fields.

### D1 - Executive Overview  (`previews/dashboard1_executive_overview.png`)
1. **KPI tiles** (4 sheets, text only): Fill Rate; Lost Revenue (Cr); Stock Value (Cr); Deficit Lines (Latest Week).
2. **Map**: Longitude × Latitude, detail = Warehouse Name, size = Stock Value (Cr), colour = Deficit Lines % (diverging, centre 0.25). Label with warehouse name.
3. **Bar**: Warehouse Name × (1 − Fill Rate) sorted descending - "demand lost to stock-outs". Colour orange where > 5%.
4. **Paired bars**: Stock Share % vs Demand Share % per warehouse (measure names on colour) - shows where stock sits vs where demand is.
5. **Line**: Week Start × Fill Rate, reference band on Diwali weeks (Dim Week → *Season* = "Festive (Diwali)").
Filter actions: clicking a warehouse filters the whole dashboard.

### D2 - Inventory Health & Alerts  (`previews/dashboard2_...png`)
1. **Heatmap**: rows Warehouse Name, columns Category, colour = Deficit Lines %, filter *Is Latest Week* = True.
2. **Status mix**: stacked bar of Dynamic Status by Region (filter latest week). Use the only multi-colour palette here: STOCKOUT/CRITICAL = red, LOW = amber, HEALTHY = grey-green, EXCESS = blue; every status is also a text label.
3. **Action list** (text table): Warehouse, SKU Name, Dynamic Status, Weeks of Cover, Closing Stock, On Order Units, sorted by `Avg Demand 4W × (Unit Price − Unit Cost)`. Add a **Top N** filter parameter.
4. Show the five parameters so planners can tighten/loosen thresholds.

### D3 - Pipeline & Supplier Performance  (`previews/dashboard3_...png`)
1. **Bar**: Supplier Name × On-Time %, sorted ascending; colour orange where < 55%.
2. **Line**: month of Received Date × On-Time %; shade Jul-Sep (monsoon). Exclude the partial first and last months.
3. **Overdue PO table**: PO Id, Supplier, Warehouse, SKU, Days Vs Promise, PO Value, Overdue Severity (filter ≠ Null), sorted by days overdue.
4. **Scatter**: Avg promised lead time vs avg actual lead time by supplier (size = PO value) with a 45° reference line.

### D4 - Root Cause & Waste  (`previews/dashboard4_...png`)
1. **Root cause bars** (`rca_events.csv`): Primary Cause × SUM(Lost Revenue Inr)/1e7, sorted.
2. **Stacked area**: month of Week Start × Lost Revenue by Primary Cause (shows the festive spike and monsoon delay).
3. **Excess**: `excess_lines.csv` - bar of Excess Value by Warehouse; table of top offenders.
4. **Assets** (`asset_monthly.csv`): scatter of Utilisation % vs Downtime % by Warehouse, size = idle cost, labels on outliers; second bar of idle cost by warehouse.
5. **Rebalance** (`rebalance_transfers.csv`): from-warehouse → to-warehouse table with transfer units and net benefit; optional Sankey-style bar-in-bar.

## 5. Alerts

The alert *logic* already exists in SQL (`sp_generate_alerts` → `alert_log` table; `alerts.csv` is a snapshot). Choose how to surface it:

### Option 1 - Tableau data-driven alerts (Tableau Cloud / Tableau Server only)
Publish the workbook and its data source with a scheduled extract refresh, then on a worksheet whose axis is continuous:
* **Stock deficit alert**: sheet showing `Deficit Lines (Latest Week)` → Alert → "above" a threshold (e.g. 350, between the 2024 average and today's 398), send to your email / Slack-email, frequency daily.
* **Pipeline delay alert**: sheet showing `Overdue PO Value` or `Overdue PO Count` → alert "above" a threshold (e.g. ₹1 Cr or 50 POs).
Alert menu names and options differ slightly between Tableau versions - follow your version's "Send Data-Driven Alerts" help page.

### Option 2 - Visual alerts (works in Desktop and Public)
Build an **Alert Banner** sheet: a single text mark `IF [Deficit Lines % (Latest Week)] > 0.25 THEN "⚠ " + STR([Deficit Lines (Latest Week)]) + " SKU lines in deficit" END` coloured red; same for overdue POs. Place it at the top of D1 so a breach is unmistakable.

### Option 3 - Push alerts from the database
Schedule `CALL sp_generate_alerts(...)` weekly (MySQL Event Scheduler or cron), connect Tableau live to `alert_log`, and use Tableau **subscriptions** on the alert dashboard. Example (untested - adapt to your MySQL setup):
```sql
SET GLOBAL event_scheduler = ON;
DELIMITER //
CREATE EVENT ev_weekly_alerts ON SCHEDULE EVERY 1 WEEK STARTS '2026-10-19 06:00:00'
DO BEGIN
  SET @asof = (SELECT MAX(week_end) FROM fact_inventory_weekly);
  CALL sp_generate_alerts(@asof);
END //
DELIMITER ;
```

## 6. Tableau sanity checks (compare with the SQL results)
After building, these must match `outputs/sql_results/`:
* Fill Rate (all weeks, all warehouses) = **97.25%**; Chennai **89.14%**, Guwahati **87.86%**.
* Latest-week status counts (default parameters): STOCKOUT **124**, CRITICAL **58**, LOW **216**, EXCESS **120** (of 1,440 lines).
* Overdue POs ≥ 3 days: **71** (28 critical, 43 warning), value **₹2.44 Cr**.
* Lost Revenue (all weeks) = **₹39.6 Cr**.

## 7. Publishing
Tableau Public: no alerts, 15M-row extract limit (this data is 150k - fine). Export a PDF/PNG of each dashboard for your portfolio, and screenshot the alert configuration.
