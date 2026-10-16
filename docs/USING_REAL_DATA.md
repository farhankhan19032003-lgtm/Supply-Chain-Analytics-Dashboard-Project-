# Using a real dataset instead (or as well)

The brief for this project asked for real-world data. I could not download external datasets from my build
environment, so the shipped data is simulated. If you want real data behind the same SQL / Power Query / Tableau work,
these public datasets fit different parts of it. **Search for them by name and check the licence and column names after
downloading - I have not opened them, so treat the column names below as a starting point, not a guarantee.**

| Dataset (search term) | Good for | Rough mapping to this project |
|---|---|---|
| **DataCo Smart Supply Chain** (Mendeley Data / Kaggle) | order, shipping and delivery-delay analytics across regions | order lines → `fact_inventory_weekly` demand side; scheduled vs real shipping days → `fact_purchase_orders` promised vs received |
| **USAID Supply Chain Shipment Pricing Data** (Kaggle / data.usaid.gov) | PO-style shipments with scheduled vs delivered dates, vendors, quantities, unit prices | → `fact_purchase_orders` (promised = scheduled delivery, received = delivered date); vendor → `dim_supplier` |
| **M5 Forecasting - Accuracy** (Kaggle, Walmart) | real weekly/daily retail demand by item × store × state | → `demand_units`; run the replenishment simulation on top of real demand |
| Government open-data portals (data.gov.in) | warehouse capacity, regional production/stock statistics | context for `dim_warehouse` |

## Recommended hybrid (honest and strong)
1. Use real **demand** (M5) or real **shipment lead times** (USAID) as the factual backbone.
2. Keep the replenishment simulation for the pieces no public dataset has (warehouse stock levels, asset logs) and label them as simulated.
3. In the README and in interviews, state exactly which tables are real and which are modelled.

## How to swap data in
1. Map the real columns to the CSV schemas in `docs/DATA_DICTIONARY.md` (keep the column names).
2. Write the new CSVs into `data/clean/` (same file names). Dates must be ISO text; open POs have an empty `received_date`.
3. Reload MySQL (`02_load_data.sql`). Views and procedures need **no changes** because thresholds live in `cfg_thresholds`.
4. Re-run `scripts/02_run_sql_pipeline.py`, `06_build_excel.py` and `07_...py` to refresh Excel / Tableau extracts.
5. Update the narrative numbers in `docs/FINDINGS_REPORT.md` - the shipped numbers are specific to the simulated data.
