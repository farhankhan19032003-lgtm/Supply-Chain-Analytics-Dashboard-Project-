-- =====================================================================================
-- 05_analysis_queries.sql  |  Ad-hoc exploration queries that led to the findings.
-- Each block is independent. Run them in MySQL Workbench one at a time.
-- =====================================================================================
USE supply_chain_analytics;

-- Q1: Top 10 SKUs by revenue lost to stock-outs (full 104 weeks)
SELECT e.sku_id, e.sku_name, e.category, e.abc_class,
       SUM(e.lost_units)                  AS lost_units,
       ROUND(SUM(e.lost_revenue_inr), 0)  AS lost_revenue_inr
FROM vw_inventory_enriched e
GROUP BY e.sku_id, e.sku_name, e.category, e.abc_class
ORDER BY SUM(e.lost_revenue_inr) DESC
LIMIT 10;

-- Q2: Supplier on-time delivery by month received (does the monsoon hurt?)
SELECT SUBSTR(v.received_date, 1, 7)                                   AS receipt_month,
       COUNT(*)                                                        AS pos_received,
       ROUND(100.0 * SUM(v.on_time_flag) / COUNT(*), 1)                AS on_time_pct,
       ROUND(AVG(v.days_vs_promise), 2)                                AS avg_days_vs_promise
FROM vw_po_enriched v
WHERE v.po_state = 'RECEIVED'
GROUP BY SUBSTR(v.received_date, 1, 7)
ORDER BY receipt_month;

-- Q3: Stock-out rate and fill rate by season and region
SELECT d.season, e.region,
       ROUND(100.0 * SUM(CASE WHEN e.lost_units > 0 THEN 1 ELSE 0 END) / COUNT(*), 2) AS stockout_rate_pct,
       ROUND(100.0 * SUM(e.units_sold) / SUM(e.demand_units), 2)                       AS fill_rate_pct
FROM vw_inventory_enriched e
JOIN dim_week d ON d.week_start = e.week_start
GROUP BY d.season, e.region
ORDER BY d.season, e.region;

-- Q4: Fill rate by category x region
SELECT e.category, e.region,
       ROUND(100.0 * SUM(e.units_sold) / SUM(e.demand_units), 2) AS fill_rate_pct,
       ROUND(SUM(e.lost_revenue_inr), 0)                          AS lost_revenue_inr
FROM vw_inventory_enriched e
GROUP BY e.category, e.region
ORDER BY e.category, e.region;

-- Q5: ABC class performance (A = top 70% of revenue, B = next 20%, C = last 10%)
SELECT e.abc_class,
       COUNT(DISTINCT e.sku_id)                                   AS skus,
       ROUND(100.0 * SUM(e.units_sold) / SUM(e.demand_units), 2)  AS fill_rate_pct,
       ROUND(SUM(e.lost_revenue_inr), 0)                          AS lost_revenue_inr,
       ROUND(SUM(e.stock_value_inr) / COUNT(DISTINCT e.week_start), 0) AS avg_inventory_value_inr
FROM vw_inventory_enriched e
GROUP BY e.abc_class
ORDER BY e.abc_class;

-- Q6: Stock concentration vs demand share, latest week (is stock where the demand is?)
SELECT s.warehouse_id, s.warehouse_name, s.region,
       ROUND(SUM(s.stock_value_inr), 0)                                                              AS stock_value_inr,
       ROUND(100.0 * SUM(s.stock_value_inr) / SUM(SUM(s.stock_value_inr)) OVER (), 1)                AS pct_of_network_stock,
       ROUND(100.0 * SUM(s.avg_demand_4w * s.unit_cost_inr) / SUM(SUM(s.avg_demand_4w * s.unit_cost_inr)) OVER (), 1) AS pct_of_network_demand
FROM vw_stock_status_latest s
GROUP BY s.warehouse_id, s.warehouse_name, s.region
ORDER BY pct_of_network_stock DESC;

-- Q7: Festive preparedness - lost revenue per SKU-week, Diwali weeks vs other weeks, by category
SELECT e.category,
       ROUND(AVG(CASE WHEN d.season = 'Festive (Diwali)'  THEN e.lost_revenue_inr END), 1) AS lost_rev_per_row_festive,
       ROUND(AVG(CASE WHEN d.season <> 'Festive (Diwali)' THEN e.lost_revenue_inr END), 1) AS lost_rev_per_row_other,
       ROUND(AVG(CASE WHEN d.season = 'Festive (Diwali)'  THEN e.lost_revenue_inr END)
             / NULLIF(AVG(CASE WHEN d.season <> 'Festive (Diwali)' THEN e.lost_revenue_inr END), 0), 2) AS festive_multiple
FROM vw_inventory_enriched e
JOIN dim_week d ON d.week_start = e.week_start
GROUP BY e.category
ORDER BY festive_multiple DESC;

-- Q8: Promised vs actual lead time by supplier tier (received POs only)
SELECT v.supplier_tier,
       COUNT(*)                                                         AS pos,
       ROUND(AVG(DATEDIFF(v.promised_date, v.order_date)), 1)           AS avg_promised_lead_days,
       ROUND(AVG(DATEDIFF(v.received_date, v.order_date)), 1)           AS avg_actual_lead_days,
       ROUND(100.0 * SUM(v.on_time_flag) / COUNT(*), 1)                 AS on_time_pct
FROM vw_po_enriched v
WHERE v.po_state = 'RECEIVED'
GROUP BY v.supplier_tier
ORDER BY v.supplier_tier;

-- Q9: Reorder-policy audit. Ratio of the reorder point actually used to (forecast x (lead weeks + 1)).
--     ~1.0 = neutral; well below 1 = under-protected (stock-outs); well above 1 = over-protected (excess).
SELECT w.warehouse_id, w.warehouse_name, w.region,
       ROUND(AVG(f.reorder_point_units * 1.0
                 / NULLIF(f.forecast_weekly_units * (CEILING(k.lead_time_days / 7.0) + 1), 0)), 2) AS reorder_policy_ratio,
       ROUND(100.0 * SUM(f.units_sold) / SUM(f.demand_units), 2)                                  AS fill_rate_pct
FROM fact_inventory_weekly f
JOIN dim_warehouse w ON w.warehouse_id = f.warehouse_id
JOIN dim_sku       k ON k.sku_id       = f.sku_id
WHERE f.forecast_weekly_units > 0
GROUP BY w.warehouse_id, w.warehouse_name, w.region
ORDER BY reorder_policy_ratio;
