-- =====================================================================================
-- 03_views.sql  |  Reusable semantic layer. Tableau connects to these views directly.
-- All business thresholds live in cfg_thresholds (pivoted to one row by vw_cfg) so that
-- changing a rule never requires editing code.
-- =====================================================================================
USE supply_chain_analytics;

-- --------------------------------------------------------------------- config (one row)
DROP VIEW IF EXISTS vw_cfg;
CREATE VIEW vw_cfg AS
SELECT
  MAX(CASE WHEN param = 'critical_cover_weeks'                THEN param_value END) AS critical_cover_weeks,
  MAX(CASE WHEN param = 'low_cover_weeks'                     THEN param_value END) AS low_cover_weeks,
  MAX(CASE WHEN param = 'excess_cover_weeks'                  THEN param_value END) AS excess_cover_weeks,
  MAX(CASE WHEN param = 'obsolete_cover_weeks'                THEN param_value END) AS obsolete_cover_weeks,
  MAX(CASE WHEN param = 'expiry_cover_share'                  THEN param_value END) AS expiry_cover_share,
  MAX(CASE WHEN param = 'holding_cost_pct_annual'             THEN param_value END) AS holding_cost_pct_annual,
  MAX(CASE WHEN param = 'overdue_warn_days'                   THEN param_value END) AS overdue_warn_days,
  MAX(CASE WHEN param = 'overdue_critical_days'               THEN param_value END) AS overdue_critical_days,
  MAX(CASE WHEN param = 'operator_idle_share'                 THEN param_value END) AS operator_idle_share,
  MAX(CASE WHEN param = 'asset_idle_flag_pct'                 THEN param_value END) AS asset_idle_flag_pct,
  MAX(CASE WHEN param = 'asset_downtime_flag_pct'             THEN param_value END) AS asset_downtime_flag_pct,
  MAX(CASE WHEN param = 'asset_overstretch_util'              THEN param_value END) AS asset_overstretch_util,
  MAX(CASE WHEN param = 'asset_target_util'                   THEN param_value END) AS asset_target_util,
  MAX(CASE WHEN param = 'rebalance_keep_weeks'                THEN param_value END) AS rebalance_keep_weeks,
  MAX(CASE WHEN param = 'rebalance_target_weeks'              THEN param_value END) AS rebalance_target_weeks,
  MAX(CASE WHEN param = 'transfer_cost_same_region_per_unit'  THEN param_value END) AS transfer_cost_same_region_per_unit,
  MAX(CASE WHEN param = 'transfer_cost_cross_region_per_unit' THEN param_value END) AS transfer_cost_cross_region_per_unit,
  MAX(CASE WHEN param = 'capacity_warn_util'                  THEN param_value END) AS capacity_warn_util,
  MAX(CASE WHEN param = 'capacity_critical_util'              THEN param_value END) AS capacity_critical_util
FROM cfg_thresholds;

-- --------------------------------------------------------------------- inventory, enriched
-- One row per week x warehouse x SKU with names, INR values and a rolling 4-week demand average.
DROP VIEW IF EXISTS vw_inventory_enriched;
CREATE VIEW vw_inventory_enriched AS
SELECT
  f.week_start, f.week_end,
  f.warehouse_id, w.warehouse_name, w.city, w.state, w.region, w.latitude, w.longitude,
  f.sku_id, k.sku_name, k.category, k.abc_class, k.primary_supplier_id AS supplier_id,
  f.opening_stock, f.receipts, f.demand_units, f.units_sold, f.lost_units, f.closing_stock,
  f.on_order_units, f.reorder_point_units, f.forecast_weekly_units,
  k.unit_cost_inr, k.unit_price_inr,
  f.closing_stock * k.unit_cost_inr                       AS stock_value_inr,
  f.units_sold    * k.unit_cost_inr                       AS cogs_inr,
  f.lost_units    * k.unit_price_inr                      AS lost_revenue_inr,
  f.lost_units    * (k.unit_price_inr - k.unit_cost_inr)  AS lost_margin_inr,
  AVG(f.demand_units) OVER (PARTITION BY f.warehouse_id, f.sku_id
                            ORDER BY f.week_start
                            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS avg_demand_4w
FROM fact_inventory_weekly f
JOIN dim_warehouse w ON w.warehouse_id = f.warehouse_id
JOIN dim_sku       k ON k.sku_id       = f.sku_id;

-- --------------------------------------------------------------------- stock status (every week)
DROP VIEW IF EXISTS vw_stock_status_all;
CREATE VIEW vw_stock_status_all AS
SELECT
  x.*,
  CASE
    WHEN x.avg_demand_4w IS NULL OR x.avg_demand_4w = 0 THEN 'NO DEMAND'
    WHEN x.closing_stock = 0                              THEN 'STOCKOUT'
    WHEN x.weeks_of_cover < c.critical_cover_weeks        THEN 'CRITICAL'
    WHEN x.weeks_of_cover < c.low_cover_weeks             THEN 'LOW'
    WHEN x.weeks_of_cover > c.excess_cover_weeks          THEN 'EXCESS'
    ELSE 'HEALTHY'
  END AS stock_status
FROM (
  SELECT e.*,
         CASE WHEN e.avg_demand_4w > 0 THEN e.closing_stock * 1.0 / e.avg_demand_4w END AS weeks_of_cover
  FROM vw_inventory_enriched e
) x
CROSS JOIN vw_cfg c;

DROP VIEW IF EXISTS vw_stock_status_latest;
CREATE VIEW vw_stock_status_latest AS
SELECT s.*
FROM vw_stock_status_all s
WHERE s.week_end = (SELECT MAX(week_end) FROM fact_inventory_weekly);

-- --------------------------------------------------------------------- purchase orders, enriched
-- as_of_date = last day of data. Open PO + as_of_date > promised_date  => overdue.
DROP VIEW IF EXISTS vw_po_enriched;
CREATE VIEW vw_po_enriched AS
SELECT
  p.po_id, p.warehouse_id, w.warehouse_name, w.region,
  p.sku_id, k.sku_name, k.category,
  p.supplier_id, s.supplier_name, s.supplier_tier,
  p.order_date, p.promised_date, p.received_date,
  p.ordered_qty, p.received_qty, p.unit_cost_inr, p.po_value_inr,
  a.as_of_date,
  CASE WHEN p.received_date IS NULL THEN 'OPEN' ELSE 'RECEIVED' END AS po_state,
  CASE WHEN p.received_date IS NOT NULL THEN DATEDIFF(p.received_date, p.promised_date)
       ELSE DATEDIFF(a.as_of_date, p.promised_date) END            AS days_vs_promise,
  CASE WHEN p.received_date IS NULL THEN NULL
       WHEN p.received_date <= p.promised_date THEN 1 ELSE 0 END   AS on_time_flag,
  CASE WHEN p.received_date IS NULL AND a.as_of_date > p.promised_date THEN 1 ELSE 0 END AS overdue_open_flag,
  CASE WHEN p.received_date IS NULL THEN NULL ELSE p.ordered_qty - p.received_qty END    AS short_qty
FROM fact_purchase_orders p
JOIN dim_warehouse w ON w.warehouse_id = p.warehouse_id
JOIN dim_sku       k ON k.sku_id       = p.sku_id
JOIN dim_supplier  s ON s.supplier_id  = p.supplier_id
CROSS JOIN (SELECT MAX(week_end) AS as_of_date FROM fact_inventory_weekly) a;

-- --------------------------------------------------------------------- supplier scorecard
DROP VIEW IF EXISTS vw_supplier_scorecard;
CREATE VIEW vw_supplier_scorecard AS
SELECT
  v.supplier_id, v.supplier_name, v.category, v.supplier_tier,
  COUNT(*)                                                                   AS po_count,
  SUM(CASE WHEN v.po_state = 'RECEIVED' THEN 1 ELSE 0 END)                   AS received_pos,
  ROUND(100.0 * SUM(CASE WHEN v.on_time_flag = 1 THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN v.po_state = 'RECEIVED' THEN 1 ELSE 0 END), 0), 1) AS on_time_pct,
  ROUND(AVG(CASE WHEN v.po_state = 'RECEIVED' THEN v.days_vs_promise END), 2) AS avg_days_vs_promise,
  ROUND(AVG(CASE WHEN v.on_time_flag = 0 THEN v.days_vs_promise END), 2)      AS avg_days_late_when_late,
  ROUND(100.0 * SUM(CASE WHEN v.po_state = 'RECEIVED' THEN v.received_qty ELSE 0 END)
        / NULLIF(SUM(CASE WHEN v.po_state = 'RECEIVED' THEN v.ordered_qty ELSE 0 END), 0), 1) AS qty_fill_pct,
  SUM(CASE WHEN v.po_state = 'OPEN' THEN 1 ELSE 0 END)                       AS open_pos,
  SUM(v.overdue_open_flag)                                                   AS overdue_open_pos,
  ROUND(SUM(CASE WHEN v.overdue_open_flag = 1 THEN v.po_value_inr ELSE 0 END), 0) AS overdue_open_value_inr,
  ROUND(SUM(v.po_value_inr), 0)                                              AS total_po_value_inr
FROM vw_po_enriched v
GROUP BY v.supplier_id, v.supplier_name, v.category, v.supplier_tier;

-- --------------------------------------------------------------------- asset usage, enriched
DROP VIEW IF EXISTS vw_asset_monthly_enriched;
CREATE VIEW vw_asset_monthly_enriched AS
SELECT
  m.month_start, a.asset_id, a.asset_type, a.warehouse_id, w.warehouse_name, w.region,
  a.purchase_date, a.useful_life_years,
  m.scheduled_hours, m.run_hours, m.idle_hours, m.downtime_hours, m.breakdown_count,
  m.maintenance_cost_inr, m.energy_cost_inr,
  m.idle_hours * (a.hourly_ownership_cost_inr + c.operator_idle_share * a.hourly_operator_cost_inr) AS idle_cost_inr,
  ROUND(100.0 * m.run_hours      / NULLIF(m.scheduled_hours, 0), 2) AS utilisation_pct,
  ROUND(100.0 * m.idle_hours     / NULLIF(m.scheduled_hours, 0), 2) AS idle_pct,
  ROUND(100.0 * m.downtime_hours / NULLIF(m.scheduled_hours, 0), 2) AS downtime_pct
FROM fact_asset_monthly m
JOIN dim_asset     a ON a.asset_id     = m.asset_id
JOIN dim_warehouse w ON w.warehouse_id = a.warehouse_id
CROSS JOIN vw_cfg c;
