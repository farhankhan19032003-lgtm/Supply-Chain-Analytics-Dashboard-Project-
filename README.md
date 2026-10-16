# Supply Chain Analytics Platform
**SQL · Tableau · Excel · Power Query** — nationwide (India) inventory, pipeline and asset analytics

A complete, runnable portfolio project: a 12-warehouse / 120-SKU / 104-week distribution network, an
MySQL analytics layer with 8 stored procedures, an Excel Power Query data-prep workflow, an Excel KPI
workbook, and a Tableau build kit with alert logic.

> ## Read this first - what is real and what is simulated
> * **The data is simulated.** Real warehouse-level inventory, PO and asset logs are proprietary and cannot be
>   downloaded openly (and my build environment could not fetch external datasets). `scripts/01_generate_data.py`
>   simulates a realistic Indian FMCG/consumer-goods network (replenishment policy, supplier lead-time variability,
>   Diwali / monsoon seasonality, ageing fleets). Supplier names are fictional.
> * **The problems the analysis "discovers" were planted** in the simulator (e.g. Chennai's reorder points are set low,
>   Bhiwandi's are set high, four suppliers are unreliable). That shows the *method* works - the procedures recover
>   each planted cause - but these are not findings about a real company. Never present the numbers as a real
>   employer's results. `docs/USING_REAL_DATA.md` shows how to point the same project at a real dataset.
> * **Verification status** (details in "Verification" below): SQL logic was executed and independently reconciled
>   (23 checks pass) through a SQLite harness, **not on a live MySQL server**. The Power Query M code **has not been run
>   in Excel** (its rules were replicated and verified in Python). Tableau needs you to build the workbook from the
>   guide - no `.twbx` is included.

## Headline results (from the stored procedures, as of week ending 4-Oct-2026)

| Finding | Number |
|---|---|
| Network fill rate, 104 weeks | **97.25%** |
| Revenue lost to stock-outs, 104 weeks | **₹39.6 Cr** (Chennai + Guwahati = 51% of it) |
| Chennai / Guwahati fill rate | **89.1% / 87.9%** vs 98%+ at most other sites |
| Stock held by Bhiwandi + Gurugram | **48% of network stock vs 25% of demand** |
| Stock above 4-week target cover | **₹7.07 Cr** (Bhiwandi 41% of its stock, Gurugram 40%) → ₹1.56 Cr/yr carrying cost at 22% |
| Root cause of lost sales | **38.6% supplier delay · 31.7% reorder-point gap · 12.5% demand spike · 15.0% variability · 2.1% short-ship** |
| Unreliable suppliers | 4 suppliers on-time **38–50%** (network 71%); on-time falls in monsoon months |
| Live alerts, latest week | **398** stock-deficit lines (182 critical) · **71** overdue POs (28 critical, ₹2.44 Cr) · 2 capacity warnings |
| Stock-transfer recommendations | **236 lines, 1.37 lakh units, ≈₹44.7 lakh net benefit** (indicative, one cycle) |
| Asset waste | Pune + Jaipur: **~30 surplus assets, ₹2.45 Cr idle cost** in 24 months; Kolkata/Lucknow downtime 8–9% (ageing); Chennai fleet 93% utilised |

Full write-up: `docs/FINDINGS_REPORT.md`.

## Architecture

```
01_generate_data.py ──► data/clean/*.csv ──► MySQL (sql/01..05) ──► views + 8 stored procedures
                                  │                                        │
                                  │                                        ├──► alert_log table ──► Tableau (live alerts)
03_make_raw_extracts.py           │                                        └──► outputs/sql_results/*.csv
   └─► data/raw_regional_extracts │                                                   │
          (5 messy CSV + xlsx)    │                                                   ├──► Excel KPI workbook (excel/)
              │                   │                                                   └──► Tableau extracts + guide (tableau/)
              └─► Excel Power Query (powerquery/) ──► clean 74,880-row table
```

## Folder map

| Path | What it is |
|---|---|
| `data/clean/` | 9 clean tables (dims, facts, thresholds). Load these into MySQL. |
| `data/raw_regional_extracts/` | 5 deliberately messy regional CSVs + `Master_Data_Raw.xlsx` - the Power Query input |
| `sql/01_schema.sql` … `05_analysis_queries.sql` | MySQL 8 schema, load script, 7 views, **8 stored procedures**, 9 analysis queries |
| `powerquery/` | 17 M queries (`queries/*.m`), step-by-step README, expected checksums |
| `excel/Supply_Chain_KPI_Workbook.xlsx` | 13-sheet KPI workbook, 6,027 live formulas, thresholds editable in `Config` |
| `tableau/` | build guide, calculated fields, alert setup, 12 CSV extracts, 4 dashboard preview images |
| `outputs/` | every procedure result as CSV, `validation_report.txt`, analysis-query results |
| `scripts/` | generators, SQL runner, validators, builders (run order below) |
| `docs/` | findings report, data dictionary, resume & interview guide, real-data guide |

## How to run it (about 2-3 hours end to end)

**0. Regenerate everything (optional - results are already in the folder).** Python 3.10+, `pandas numpy openpyxl matplotlib`:
```
python scripts/01_generate_data.py data/clean
python scripts/02_run_sql_pipeline.py        # executes the SQL files, writes outputs/
python scripts/03_make_raw_extracts.py
python scripts/04_validate_results.py        # 23 independent checks
python scripts/05_verify_powerquery_logic.py
python scripts/06_build_excel.py
python scripts/07_tableau_extracts_and_previews.py
```
**1. MySQL (the real thing - do this).** In MySQL Workbench run `sql/01_schema.sql`, edit the path in
`02_load_data.sql` and run it (or use the Table Data Import Wizard), then `03_views.sql`, `04_stored_procedures.sql`.
Test: `SET @asof = (SELECT MAX(week_end) FROM fact_inventory_weekly); CALL sp_generate_alerts(@asof);`
Expected: 398 deficit / 71 pipeline / 2 capacity alerts (compare `outputs/sql_results/alert_summary.csv`).
**2. Power Query.** Follow `powerquery/README_PowerQuery.md` (30-45 min). Compare with `powerquery/expected_results.csv`.
**3. Excel.** Open `excel/Supply_Chain_KPI_Workbook.xlsx`. Change a threshold on `Config` and watch the statuses move.
**4. Tableau.** Follow `tableau/TABLEAU_BUILD_GUIDE.md` (60-90 min) using `tableau/extracts/` or a live MySQL connection.

## Verification - exactly what was and wasn't tested

| Component | How it was checked | Not checked |
|---|---|---|
| Data generator | Re-run is deterministic; distributions reviewed (fill rate, cover, delay rates, utilisation) | - |
| SQL views and procedures | Same SQL text executed in SQLite with MySQL function shims (`DATEDIFF`, `GREATEST`, `CEILING`, …); `outputs/validation_report.txt`: **23/23 independent pandas reconciliations pass** (fill rate, lost revenue, alert counts, RCA flags incl. a 1,500-event brute-force check, transfer caps, asset idle cost, supplier on-time) | **Not run on a live MySQL server.** Expect to fix, at worst, small dialect issues (see Troubleshooting) |
| Schema ↔ CSV ↔ `LOAD DATA` | Script compares every table's column list to the CSV headers and the PO load column list | `LOAD DATA LOCAL` server settings on your machine |
| Power Query | Cleaning rules re-implemented in pandas and shown to reproduce the clean data exactly (0 mismatches over 74,880 rows) | **M syntax not run in Excel** |
| Excel workbook | LibreOffice recalculation: 0 formula errors; KPI cells equal the pandas numbers | Visual check in desktop Excel |
| Tableau | Extract columns and calculated-field logic prepared; preview PNGs rendered from the same numbers | **No `.twbx`; alerts need Tableau Cloud/Server** |

### Troubleshooting MySQL (most likely issues)
* `ERROR 3948 Loading local data is disabled` → `SET GLOBAL local_infile = 1;` and connect with `OPT_LOCAL_INFILE=1`, or use the import wizard.
* `ERROR 1290 --secure-file-priv` applies only to non-LOCAL loads; keep `LOCAL`.
* If a procedure errors on `ONLY_FULL_GROUP_BY`, tell me the line - the code was written to comply, but this is the first thing a live server could flag.
* MySQL < 8.0 has no window functions or CTEs; upgrade to 8.0+.

## Reproducibility
Fixed seeds (`SEED = 2026` generator, `7` raw extracts). Regenerating yields byte-identical CSVs.
