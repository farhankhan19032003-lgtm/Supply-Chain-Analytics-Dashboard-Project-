# Data Dictionary

Currency: INR. Dates: ISO `YYYY-MM-DD`. Weeks run Monday → Sunday (`week_start` is the Monday).
Row counts are for the shipped dataset (as-of **2026-10-04**).

## Dimensions
**dim_warehouse** (12) - `warehouse_id` PK (WH01-WH12), `warehouse_name`, `city`, `state`, `region` (North/West/South/East/Central), `latitude`, `longitude`, `capacity_units` (storage capacity).

**dim_supplier** (22, fictional) - `supplier_id` PK, `supplier_name`, `category`, `origin_city`, `origin_region`, `supplier_tier` (Tier 1/2/3 by reliability), `payment_terms_days`.

**dim_sku** (120) - `sku_id` PK, `sku_name`, `category` (8), `unit_cost_inr`, `unit_price_inr`, `base_weekly_demand`, `lead_time_days` (promised), `shelf_life_days` (0 = non-perishable), `case_pack`, `primary_supplier_id` FK, `abc_class` (A = top 70% of revenue, B = next 20%, C = last 10%).

**dim_week** (104) - `week_start` PK, `week_end`, `week_no`, `calendar_year`, `month_no`, `month_name`, `quarter`, `fiscal_year` (Indian FY, Apr-Mar), `season` (Festive (Diwali) / Monsoon / Summer / Winter / Regular).

**dim_asset** (291) - `asset_id` PK, `warehouse_id` FK, `asset_type` (Forklift (Electric), Reach Truck, Electric Pallet Jack, Conveyor Line, Delivery Truck), `purchase_date`, `purchase_cost_inr`, `useful_life_years`, `rated_hours_per_month`, `hourly_ownership_cost_inr` (cost ÷ life ÷ rated hours), `hourly_operator_cost_inr`.

**cfg_thresholds** (19) - `param` PK, `param_value`, `description`. Every business rule in the views/procedures is read from here.

## Facts
**fact_inventory_weekly** (149,760) - grain: week × warehouse × SKU. `opening_stock`, `receipts`, `demand_units` (what customers wanted), `units_sold` (= min(available, demand)), `lost_units` (= demand − sold), `closing_stock` (= opening + receipts − sold), `on_order_units` (open PO quantity at week end), `reorder_point_units` and `forecast_weekly_units` (the planning values used that week).

**fact_purchase_orders** (31,991; 652 open) - `po_id` PK, `warehouse_id`, `sku_id`, `supplier_id`, `order_date`, `promised_date`, `received_date` (**NULL = still open**), `ordered_qty`, `received_qty` (0 while open; lower than ordered = short-shipment), `unit_cost_inr`, `po_value_inr`.

**fact_asset_monthly** (6,984) - grain: asset × month. `scheduled_hours`, `run_hours`, `idle_hours`, `downtime_hours` (breakdown + maintenance), `breakdown_count`, `maintenance_cost_inr`, `energy_cost_inr`.

**alert_log** (output of `sp_generate_alerts`) - `alert_type` (STOCK_DEFICIT / PIPELINE_DELAY / CAPACITY_RISK), `severity` (CRITICAL / WARNING), keys, human-readable `message`, `metric_value`, `threshold_value`.

## Views
| View | Purpose |
|---|---|
| `vw_cfg` | thresholds pivoted to one row |
| `vw_inventory_enriched` | facts joined to names, INR values, 4-week average demand |
| `vw_stock_status_all` / `_latest` | adds `weeks_of_cover` and `stock_status` (STOCKOUT, CRITICAL, LOW, HEALTHY, EXCESS, NO DEMAND) |
| `vw_po_enriched` | PO state (OPEN / RECEIVED), `days_vs_promise`, `on_time_flag`, `overdue_open_flag`, `short_qty` |
| `vw_supplier_scorecard` | on-time %, delay, quantity fill, overdue open POs per supplier |
| `vw_asset_monthly_enriched` | assets with utilisation / idle / downtime % and idle cost |

## Stored procedures
| Procedure | Inputs | Returns |
|---|---|---|
| `sp_regional_kpis` | start, end | KPI per warehouse; inbound PO performance per warehouse |
| `sp_stock_deficit_alerts` | as-of | deficit lines + inbound risk (`NO INBOUND PO` / `INBOUND OVERDUE` / `GAP BEFORE ARRIVAL` / `COVERED BY INBOUND`) |
| `sp_pipeline_delay_alerts` | as-of | open POs ≥ warn days overdue + stock exposure |
| `sp_stockout_root_cause` | start, end | cause summary; warehouse × cause; factor overlap; event detail |
| `sp_excess_inventory_waste` | as-of | by warehouse; by category; line detail |
| `sp_regional_rebalance` | as-of | transfer lines; donor → receiver flow matrix |
| `sp_asset_waste_rca` | start, end | warehouse × asset-type diagnosis; warehouse roll-up |
| `sp_generate_alerts` | as-of | writes `alert_log`; returns counts |

## Key metric definitions
* **Fill rate** = Σ units_sold ÷ Σ demand_units. **Stock-out rate** = share of SKU-weeks with lost_units > 0.
* **Weeks of cover** = closing_stock ÷ 4-week average demand. Status thresholds from `cfg_thresholds` (0.5 / 1.5 / 8).
* **Inventory turns (annualised)** = (Σ units_sold × unit_cost × 52 ÷ weeks) ÷ average weekly stock value.
* **Weekly margin at risk** = avg weekly demand × (price − cost) for a deficit line.
* **Idle cost** = idle_hours × (hourly_ownership_cost + 25% × hourly_operator_cost).
* **Surplus assets** = assets − round(assets × utilisation ÷ 70% target).
