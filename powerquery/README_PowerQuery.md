# Power Query Workflow (≈ 30-45 minutes)

**Goal:** turn 5 inconsistent regional stock files + 1 master-data workbook into one clean, merged
74,880-row table with a data-quality log - refreshable with one click.

> **Status:** the M code in `queries/` has **not been executed in Excel** (it can't be run outside Excel). Its cleaning
> rules were re-implemented in pandas (`scripts/05_verify_powerquery_logic.py`) and reproduce the original data exactly.
> If Excel reports an M error, the message names the step - the code is split into small named steps to make that easy to fix.
> Needs Excel 2016+ / Microsoft 365 for Windows (Mac Excel has limited Power Query authoring; use Windows if you can).

## The mess you are fixing (inputs in `data/raw_regional_extracts/`)

| File | Problems |
|---|---|
| North | `dd-mm-yyyy` dates · trailing spaces in warehouse code · lower-case SKU codes · numbers as text with commas (`"1,689"`) · 75 duplicate rows · empty rows · junk Remarks column |
| West | 3 report-title lines above the header · different column names · `yyyy/mm/dd` dates · warehouse given as a *name* |
| South | `;` delimiter · `06-Oct-2025` dates · text `NA` in Lost Sales (1,691 rows) |
| East | columns in a different order · `dd/mm/yyyy` dates · 8 negative closing-stock typos |
| Central | timestamps in the date · 761 blank Closing Stock · blank Lost Units |
| Master_Data_Raw.xlsx | SKU / Supplier / Warehouse sheets with title rows, padded UPPER-CASE names, lower-case codes |

## Build steps

1. Open a new Excel workbook. **Data → Get Data → From Other Sources → Blank Query**.
2. In the Query Editor choose **Home → Advanced Editor**, paste the contents of one file from `queries/`, and rename the query to the file name (without `.m`). Do them in this order so references resolve:

   | # | Query | Type | Load setting |
   |---|---|---|---|
   | 1 | `pFolder` | parameter (edit the path first!) | connection only |
   | 2 | `fnToNumber`, `fnToDate`, `fnStandardize` | functions | connection only |
   | 3 | `Q_North`, `Q_West`, `Q_South`, `Q_East`, `Q_Central` | staging | connection only |
   | 4 | `Inventory_Staged` | staging | connection only |
   | 5 | `Master_SKU`, `Master_Supplier`, `Master_Warehouse`, `WH_Lookup` | staging | connection only |
   | 6 | `Inventory_Clean` | **output** | Table, or Data Model |
   | 7 | `DQ_Log` | **output** | Table |
   | 8 | `Region_Week_Summary` | **output** | Table |

   (`pFolder` can be created via *Home → Manage Parameters → New*, Type = Text, current value = your folder path **with a trailing backslash**.)
3. **Close & Load**. Refresh time is a few seconds.
4. Build a PivotTable / PivotChart on `Region_Week_Summary` or `Inventory_Clean` (Data Model) for fill rate by region.

## Expected results (check yourself)

`expected_results.csv` and `expected_DQ_Log.csv` are generated from the cleaning logic:

| Metric | Expected |
|---|---|
| `Inventory_Clean` rows | **74,880** (52 weeks × 12 warehouses × 120 SKUs) |
| SUM(demand_units) | 36,511,963 |
| SUM(units_sold) | 35,407,539 |
| SUM(lost_units) | 1,104,424 |
| SUM(closing_stock) | 123,203,560 |
| SUM(lost_revenue_inr) | 235,515,585 |
| Fill rate | **96.975%** |

(`SUM(stock_value_inr)` = 14,740,899,398 is the sum of 52 *weekly* stock values - divide by 52 for the average inventory level.)

| Region | Rows staged | Duplicates removed | Closing repaired | Lost filled |
|---|---|---|---|---|
| North | 18,795 | 75 | 0 | 0 |
| West | 18,720 | 0 | 0 | 0 |
| South | 18,720 | 0 | 0 | 1,691 |
| East | 12,480 | 0 | 8 | 0 |
| Central | 6,240 | 0 | 761 | 318 |

(Blank rows are dropped before staging, so they don't appear in "rows staged".)

## What each piece does
* `fnToNumber` - trims, strips thousands separators, maps `NA`/`N/A`/`-`/blank to null.
* `fnToDate` - parses with an **explicit** per-region format (no day/month guessing).
* `fnStandardize` - one rulebook for every region: drop blank rows, normalise keys, repair `closing = opening + receipts − sold` and `lost = demand − sold`, flag each repair (`dq_*` columns).
* `Inventory_Clean` - removes duplicate keys, then merges **three** other sources (warehouse by code *or* name, SKU master, supplier master) and adds INR measures.
* `DQ_Log` - audit trail you can show a reviewer.

## Troubleshooting
* **`Formula.Firewall`**: *File → Options → Query Options → Privacy → Ignore the Privacy Levels* (safe for local files).
* **`DataSource.NotFound`**: fix `pFolder` (needs trailing `\`).
* **West file shows one column**: keep `Columns = 9` in `Q_West` - it stops the preamble from fixing the width at 1.
* **Everything is text / errors in numbers**: make sure the `Text.From`/`fnToNumber` steps were not replaced by auto-detected types (turn off *Detect column types* for staging queries).
* **Row count ≠ 74,880**: check `DQ_Log`; `rows_clean` per region should be 18,720 / 18,720 / 18,720 / 12,480 / 6,240.
