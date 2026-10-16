# Tableau calculated fields - paste-ready

Create each field with **Analysis > Create Calculated Field**, using the exact name in the heading.
Create them **in the order shown**: later fields use earlier ones. Field names assume Tableau's default
renaming of the column (`closing_stock` -> `Closing Stock`, `week_end` -> `Week End`).
Same formulas as `TABLEAU_BUILD_GUIDE.md` section 3; the two marked *(added)* are not in the guide.

## 0. Parameters first (Create Parameter, then right-click > Show Parameter)

| Name | Data type | Current value |
|---|---|---|
| `p_critical_cover` | Float | 0.5 |
| `p_low_cover` | Float | 1.5 |
| `p_excess_cover` | Float | 8 |
| `p_overdue_warn_days` | Integer | 3 |
| `p_overdue_critical_days` | Integer | 7 |

---

## 1. Inventory data source (`vw_stock_status_all` or `inventory_weekly.csv` + `dim_week`)

### Is Latest Week
```
[Week End] = { MAX([Week End]) }
```

### Stockout Flag
```
IF [Lost Units] > 0 THEN 1 ELSE 0 END
```

### Fill Rate
```
SUM([Units Sold]) / SUM([Demand Units])
```

### Stockout Rate
```
SUM([Stockout Flag]) / COUNT([Sku Id])
```

### Weeks of Cover - NOT NEEDED with the MySQL views
`vw_stock_status_all` already has the columns `weeks_of_cover` and `avg_demand_4w`, which Tableau shows as
**Weeks Of Cover** and **Avg Demand 4w**. Do not create a field with the same name; use those columns.
(Only when you load the CSV extract, where the column is missing, create `Weeks Of Cover` as
`IF [Avg Demand 4w] > 0 THEN [Closing Stock] / [Avg Demand 4w] END`.)

### Dynamic Status
```
IF [Avg Demand 4w] = 0 THEN "NO DEMAND"
ELSEIF [Closing Stock] = 0 THEN "STOCKOUT"
ELSEIF [Weeks Of Cover] < [p_critical_cover] THEN "CRITICAL"
ELSEIF [Weeks Of Cover] < [p_low_cover] THEN "LOW"
ELSEIF [Weeks Of Cover] > [p_excess_cover] THEN "EXCESS"
ELSE "HEALTHY" END
```

### Deficit Flag
```
IF [Dynamic Status] = "STOCKOUT" OR [Dynamic Status] = "CRITICAL" OR [Dynamic Status] = "LOW" THEN 1 ELSE 0 END
```

### Deficit Lines (Latest Week)
```
SUM(IF [Is Latest Week] THEN [Deficit Flag] ELSE 0 END)
```

### Deficit Lines % (Latest Week)
```
[Deficit Lines (Latest Week)] / SUM(IF [Is Latest Week] THEN 1 ELSE 0 END)
```

### Stock Value (Cr)
```
SUM(IF [Is Latest Week] THEN [Stock Value Inr] ELSE 0 END) / 10000000
```

### Lost Revenue (Cr)
```
SUM([Lost Revenue Inr]) / 10000000
```

### Network Stock Share %
Table calculation: right-click the pill > Compute Using > Warehouse Name.
```
[Stock Value (Cr)] / TOTAL([Stock Value (Cr)])
```

### Network Demand Share % *(added - needed for the Stock Share vs Demand Share bars on D1)*
Compute Using > Warehouse Name.
```
SUM([Demand Units]) / TOTAL(SUM([Demand Units]))
```

### Alert Banner - Stock *(from guide section 5, option 2)*
```
IF [Deficit Lines % (Latest Week)] > 0.25
THEN "⚠ " + STR([Deficit Lines (Latest Week)]) + " SKU lines in deficit"
END
```

---

## 2. Pipeline data source (`vw_po_enriched` + `supplier_scorecard`)

### On-Time %
`On Time Flag` is blank for open POs, so COUNT = received POs only.
```
SUM([On Time Flag]) / COUNT([On Time Flag])
```

### Overdue Severity
For open POs, `Days Vs Promise` already means days past promise as of the data as-of date.
```
IF [Overdue Open Flag] = 1 AND [Days Vs Promise] >= [p_overdue_critical_days] THEN "CRITICAL"
ELSEIF [Overdue Open Flag] = 1 AND [Days Vs Promise] >= [p_overdue_warn_days] THEN "WARNING"
END
```

### Overdue PO Value (INR)
```
SUM(IF [Overdue Severity] = "CRITICAL" OR [Overdue Severity] = "WARNING" THEN [Po Value Inr] END)
```

### Overdue PO Count
```
SUM(IF [Overdue Severity] = "CRITICAL" OR [Overdue Severity] = "WARNING" THEN 1 ELSE 0 END)
```

### Alert Banner - Pipeline *(added, mirrors the stock banner)*
```
IF [Overdue PO Count] > 50
THEN "⚠ " + STR([Overdue PO Count]) + " overdue POs"
END
```

---

## 2b. Notes for the MySQL views (checked against the live database)
* `vw_stock_status_all` also has a ready-made `stock_status` column (Stock Status). `Dynamic Status` below is the
  version that reacts to the parameters; use `Stock Status` if you do not need that.
* There is no Season / Diwali column in the views. For the Diwali shading on D1, add the table `dim_week` to the
  Inventory data source (relationship `week_start` = `week_start`).
* `vw_po_enriched` has `on_time_flag`, `overdue_open_flag`, `days_vs_promise`, `po_value_inr` as used below.
* Fields from `rca_events`, `excess_lines`, `rebalance_transfers` (Dashboard 4) are in `tableau/extracts/*.csv`, not in these views.

## 3. Check values (as of 4-Oct-2026, default parameters)

| Field | Expected |
|---|---|
| Deficit Lines (Latest Week), all warehouses | 398 |
| Overdue PO Count | 71 |
| Fill Rate, all 104 weeks | about 97.25% |

If Deficit Lines is not 398, check that the parameters are at their defaults and that the filter
`Is Latest Week = True` is applied. If you load from `vw_stock_status_all` and its status column
already exists, your `Dynamic Status` can differ from it only when you move the parameters.
