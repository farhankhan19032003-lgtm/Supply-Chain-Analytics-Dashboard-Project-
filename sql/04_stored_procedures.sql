-- =====================================================================================
-- 04_stored_procedures.sql  |  MySQL 8.0+
--
--   sp_regional_kpis           KPI scorecard by warehouse (fill rate, stock-out rate, turns, on-time PO)
--   sp_stock_deficit_alerts    SKU x warehouse deficits + inbound-PO risk (the "stock deficit" alert)
--   sp_pipeline_delay_alerts   Open POs past promise date + stock exposure (the "pipeline delay" alert)
--   sp_stockout_root_cause     Root-cause classification of every historical stock-out event
--   sp_excess_inventory_waste  Excess / obsolescence / expiry-risk stock and carrying cost
--   sp_regional_rebalance      Surplus -> deficit stock-transfer recommendations (warehouse alignment)
--   sp_asset_waste_rca         Idle / overstretched / ageing asset diagnosis by warehouse
--   sp_generate_alerts         Writes every alert into alert_log (what Tableau reads)
--
-- Usage:   SET @asof = (SELECT MAX(week_end) FROM fact_inventory_weekly);
--          CALL sp_stock_deficit_alerts(@asof);
--          CALL sp_stockout_root_cause('2024-10-07', '2026-09-28');
--
-- Conventions: thresholds come from cfg_thresholds (via vw_cfg); no hard-coded business numbers
-- except the RCA test multipliers documented inline.
-- =====================================================================================
USE supply_chain_analytics;

DELIMITER //

-- -------------------------------------------------------------------------------------
-- 1. KPI scorecard by warehouse for a date window (week_start between p_start and p_end)
-- -------------------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_regional_kpis //
CREATE PROCEDURE sp_regional_kpis(IN p_start DATE, IN p_end DATE)
BEGIN
  -- result set 1: inventory KPIs
  SELECT
    e.warehouse_id, e.warehouse_name, e.region,
    SUM(e.demand_units)                                                       AS demand_units,
    SUM(e.units_sold)                                                         AS units_sold,
    SUM(e.lost_units)                                                         AS lost_units,
    ROUND(100.0 * SUM(e.units_sold) / NULLIF(SUM(e.demand_units), 0), 2)      AS fill_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN e.lost_units > 0 THEN 1 ELSE 0 END) / COUNT(*), 2) AS stockout_rate_pct,
    ROUND(SUM(e.stock_value_inr) / COUNT(DISTINCT e.week_start), 0)           AS avg_inventory_value_inr,
    ROUND( (SUM(e.cogs_inr) * 52.0 / COUNT(DISTINCT e.week_start))
           / NULLIF(SUM(e.stock_value_inr) / COUNT(DISTINCT e.week_start), 0), 2) AS inventory_turns_annualised,
    ROUND(AVG(e.weeks_of_cover), 2)                                           AS avg_weeks_of_cover,
    ROUND(SUM(e.lost_revenue_inr), 0)                                         AS lost_revenue_inr,
    ROUND(SUM(e.lost_margin_inr), 0)                                          AS lost_margin_inr
  FROM vw_stock_status_all e
  WHERE e.week_start BETWEEN p_start AND p_end
  GROUP BY e.warehouse_id, e.warehouse_name, e.region
  ORDER BY e.warehouse_id;

  -- result set 2: supplier delivery performance into each warehouse (POs ordered in window, already received)
  SELECT
    v.warehouse_id, v.warehouse_name, v.region,
    COUNT(*)                                                                  AS received_pos,
    ROUND(100.0 * SUM(CASE WHEN v.on_time_flag = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_pct,
    ROUND(AVG(v.days_vs_promise), 2)                                          AS avg_days_vs_promise,
    ROUND(100.0 * SUM(v.received_qty) / NULLIF(SUM(v.ordered_qty), 0), 1)     AS qty_fill_pct
  FROM vw_po_enriched v
  WHERE v.po_state = 'RECEIVED' AND v.order_date BETWEEN p_start AND p_end
  GROUP BY v.warehouse_id, v.warehouse_name, v.region
  ORDER BY v.warehouse_id;
END //

-- -------------------------------------------------------------------------------------
-- 2. Stock-deficit alerts as of a given week-end, enriched with inbound PO risk
-- -------------------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_stock_deficit_alerts //
CREATE PROCEDURE sp_stock_deficit_alerts(IN p_asof DATE)
BEGIN
  SELECT
    t.warehouse_id, t.warehouse_name, t.region, t.sku_id, t.sku_name, t.category, t.abc_class,
    t.stock_status,
    ROUND(t.weeks_of_cover, 2)                                    AS weeks_of_cover,
    t.closing_stock,
    ROUND(t.avg_demand_4w, 1)                                     AS avg_weekly_demand,
    COALESCE(i.inbound_qty, 0)                                    AS inbound_open_qty,
    i.next_po_id,
    i.next_promised_date,
    CASE
      WHEN i.next_po_id IS NULL                                               THEN 'NO INBOUND PO'
      WHEN DATEDIFF(i.next_promised_date, p_asof) < 0                         THEN 'INBOUND OVERDUE'
      WHEN COALESCE(t.weeks_of_cover, 0) * 7 < DATEDIFF(i.next_promised_date, p_asof) THEN 'GAP BEFORE ARRIVAL'
      ELSE 'COVERED BY INBOUND'
    END                                                           AS inbound_risk,
    ROUND(t.avg_demand_4w * (t.unit_price_inr - t.unit_cost_inr), 0) AS weekly_margin_at_risk_inr
  FROM vw_stock_status_all t
  LEFT JOIN (
      SELECT q.warehouse_id, q.sku_id,
             SUM(q.ordered_qty)                                  AS inbound_qty,
             MAX(CASE WHEN q.rn = 1 THEN q.po_id END)            AS next_po_id,
             MAX(CASE WHEN q.rn = 1 THEN q.promised_date END)    AS next_promised_date
      FROM (
          SELECT p.warehouse_id, p.sku_id, p.po_id, p.promised_date, p.ordered_qty,
                 ROW_NUMBER() OVER (PARTITION BY p.warehouse_id, p.sku_id
                                    ORDER BY p.promised_date, p.po_id) AS rn
          FROM fact_purchase_orders p
          WHERE p.order_date <= p_asof
            AND (p.received_date IS NULL OR p.received_date > p_asof)
      ) q
      GROUP BY q.warehouse_id, q.sku_id
  ) i ON i.warehouse_id = t.warehouse_id AND i.sku_id = t.sku_id
  WHERE t.week_end = p_asof
    AND t.stock_status IN ('STOCKOUT', 'CRITICAL', 'LOW')
  ORDER BY CASE t.stock_status WHEN 'STOCKOUT' THEN 1 WHEN 'CRITICAL' THEN 2 ELSE 3 END,
           weekly_margin_at_risk_inr DESC;
END //

-- -------------------------------------------------------------------------------------
-- 3. Pipeline-delay alerts: open POs past their promise date, with stock exposure
-- -------------------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_pipeline_delay_alerts //
CREATE PROCEDURE sp_pipeline_delay_alerts(IN p_asof DATE)
BEGIN
  SELECT
    p.po_id, p.warehouse_id, w.warehouse_name, w.region,
    p.sku_id, k.sku_name, k.category,
    p.supplier_id, s.supplier_name, s.supplier_tier,
    p.order_date, p.promised_date,
    DATEDIFF(p_asof, p.promised_date)                         AS days_overdue,
    p.ordered_qty,
    ROUND(p.po_value_inr, 0)                                  AS po_value_inr,
    COALESCE(h.closing_stock, 0)                              AS closing_stock_now,
    ROUND(h.weeks_of_cover, 2)                                AS weeks_of_cover_now,
    h.stock_status,
    CASE WHEN DATEDIFF(p_asof, p.promised_date) >= c.overdue_critical_days
         THEN 'CRITICAL' ELSE 'WARNING' END                   AS severity,
    CASE WHEN h.stock_status IN ('STOCKOUT', 'CRITICAL') THEN 'STOCK-OUT EXPOSURE'
         WHEN h.stock_status = 'LOW'                     THEN 'LOW-STOCK EXPOSURE'
         ELSE 'NO IMMEDIATE EXPOSURE' END                     AS exposure
  FROM fact_purchase_orders p
  JOIN dim_warehouse w ON w.warehouse_id = p.warehouse_id
  JOIN dim_sku       k ON k.sku_id       = p.sku_id
  JOIN dim_supplier  s ON s.supplier_id  = p.supplier_id
  CROSS JOIN vw_cfg c
  LEFT JOIN vw_stock_status_all h
         ON h.warehouse_id = p.warehouse_id AND h.sku_id = p.sku_id AND h.week_end = p_asof
  WHERE p.order_date <= p_asof
    AND (p.received_date IS NULL OR p.received_date > p_asof)
    AND DATEDIFF(p_asof, p.promised_date) >= c.overdue_warn_days
  ORDER BY CASE WHEN DATEDIFF(p_asof, p.promised_date) >= c.overdue_critical_days THEN 1 ELSE 2 END,
           DATEDIFF(p_asof, p.promised_date) DESC,
           p.po_value_inr DESC;
END //

-- -------------------------------------------------------------------------------------
-- 4. Root-cause analysis of stock-out events (weeks with lost sales)
--    Every event gets ONE primary cause, chosen by precedence (structural causes first):
--      1 POLICY GAP    reorder point < 75% of what recent demand over (lead time + 1 wk) required
--      2 SUPPLIER LATE a PO for the same SKU/warehouse was still outstanding past its promise date
--                      during (or crossing into) the stock-out week
--      3 SHORT-SHIP    a PO received in the prior 4 weeks was < 90% of the quantity ordered
--      4 DEMAND SPIKE  demand > 1.5x the prior 8-week average
--      5 VARIABILITY   none of the above (normal demand noise vs safety stock)
--    All four flags are also returned (result set 3) because causes overlap.
-- -------------------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_stockout_root_cause //
CREATE PROCEDURE sp_stockout_root_cause(IN p_start DATE, IN p_end DATE)
BEGIN
  DROP TEMPORARY TABLE IF EXISTS tmp_rca_events;

  CREATE TEMPORARY TABLE tmp_rca_events AS
  SELECT
    y.*,
    CASE WHEN y.f_policy_gap = 1 THEN '1 Planning policy gap (reorder point too low)'
         WHEN y.f_late_po    = 1 THEN '2 Supplier delay'
         WHEN y.f_short_ship = 1 THEN '3 Supplier short-shipment'
         WHEN y.f_spike      = 1 THEN '4 Unforecast demand spike'
         ELSE                         '5 Demand variability / thin safety stock'
    END AS primary_cause
  FROM (
    SELECT
      b.week_start, b.week_end, b.warehouse_id, w.warehouse_name, w.region, b.sku_id, k.category, k.abc_class,
      b.demand_units, b.lost_units,
      b.lost_units * k.unit_price_inr                                   AS lost_revenue_inr,
      b.lost_units * (k.unit_price_inr - k.unit_cost_inr)               AS lost_margin_inr,
      CASE WHEN b.prior4_avg IS NOT NULL
            AND b.reorder_point_units < 0.75 * b.prior4_avg * (CEILING(k.lead_time_days / 7.0) + 1)
           THEN 1 ELSE 0 END                                            AS f_policy_gap,
      CASE WHEN EXISTS (
             SELECT 1 FROM fact_purchase_orders p
             WHERE p.warehouse_id = b.warehouse_id AND p.sku_id = b.sku_id
               AND p.order_date    <  b.week_start
               AND p.promised_date <= b.week_end
               AND (p.received_date IS NULL
                    OR (p.received_date >= b.week_start AND p.received_date > p.promised_date))
           ) THEN 1 ELSE 0 END                                          AS f_late_po,
      CASE WHEN EXISTS (
             SELECT 1 FROM fact_purchase_orders p
             WHERE p.warehouse_id = b.warehouse_id AND p.sku_id = b.sku_id
               AND p.received_date IS NOT NULL
               AND p.received_date <= b.week_end
               AND DATEDIFF(b.week_end, p.received_date) <= 27
               AND p.received_qty < 0.9 * p.ordered_qty
           ) THEN 1 ELSE 0 END                                          AS f_short_ship,
      CASE WHEN b.prior8_avg IS NOT NULL AND b.demand_units > 1.5 * b.prior8_avg
           THEN 1 ELSE 0 END                                            AS f_spike
    FROM (
      SELECT f.*,
             AVG(f.demand_units) OVER (PARTITION BY f.warehouse_id, f.sku_id ORDER BY f.week_start
                                       ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING) AS prior8_avg,
             AVG(f.demand_units) OVER (PARTITION BY f.warehouse_id, f.sku_id ORDER BY f.week_start
                                       ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING) AS prior4_avg
      FROM fact_inventory_weekly f
    ) b
    JOIN dim_warehouse w ON w.warehouse_id = b.warehouse_id
    JOIN dim_sku       k ON k.sku_id       = b.sku_id
    WHERE b.week_start BETWEEN p_start AND p_end
      AND b.lost_units > 0
  ) y;

  -- result set 1: primary-cause summary
  SELECT
    primary_cause,
    COUNT(*)                                                           AS stockout_events,
    SUM(lost_units)                                                    AS lost_units,
    ROUND(SUM(lost_revenue_inr), 0)                                    AS lost_revenue_inr,
    ROUND(SUM(lost_margin_inr), 0)                                     AS lost_margin_inr,
    ROUND(100.0 * SUM(lost_revenue_inr) / SUM(SUM(lost_revenue_inr)) OVER (), 1) AS pct_of_lost_revenue
  FROM tmp_rca_events
  GROUP BY primary_cause
  ORDER BY primary_cause;

  -- result set 2: warehouse x cause (lost revenue INR), one row per warehouse
  SELECT
    warehouse_id, warehouse_name, region,
    COUNT(*)                                                                                       AS stockout_events,
    ROUND(SUM(CASE WHEN f_policy_gap = 1 THEN lost_revenue_inr ELSE 0 END), 0)                     AS policy_gap_inr,
    ROUND(SUM(CASE WHEN f_policy_gap = 0 AND f_late_po = 1 THEN lost_revenue_inr ELSE 0 END), 0)   AS supplier_delay_inr,
    ROUND(SUM(CASE WHEN f_policy_gap = 0 AND f_late_po = 0 AND f_short_ship = 1 THEN lost_revenue_inr ELSE 0 END), 0) AS short_ship_inr,
    ROUND(SUM(CASE WHEN f_policy_gap = 0 AND f_late_po = 0 AND f_short_ship = 0 AND f_spike = 1 THEN lost_revenue_inr ELSE 0 END), 0) AS demand_spike_inr,
    ROUND(SUM(CASE WHEN f_policy_gap = 0 AND f_late_po = 0 AND f_short_ship = 0 AND f_spike = 0 THEN lost_revenue_inr ELSE 0 END), 0) AS variability_inr,
    ROUND(SUM(lost_revenue_inr), 0)                                                                AS total_lost_revenue_inr
  FROM tmp_rca_events
  GROUP BY warehouse_id, warehouse_name, region
  ORDER BY SUM(lost_revenue_inr) DESC;

  -- result set 3: how often each factor was present (events can have several)
  SELECT
    COUNT(*)                                       AS stockout_events,
    ROUND(100.0 * SUM(f_policy_gap) / COUNT(*), 1) AS pct_with_policy_gap,
    ROUND(100.0 * SUM(f_late_po)    / COUNT(*), 1) AS pct_with_late_po,
    ROUND(100.0 * SUM(f_short_ship) / COUNT(*), 1) AS pct_with_short_ship,
    ROUND(100.0 * SUM(f_spike)      / COUNT(*), 1) AS pct_with_demand_spike
  FROM tmp_rca_events;

  -- result set 4: event-level detail (feeds the Tableau root-cause dashboard)
  SELECT
    week_start, week_end, warehouse_id, warehouse_name, region, sku_id, category, abc_class,
    demand_units, lost_units,
    ROUND(lost_revenue_inr, 0) AS lost_revenue_inr, ROUND(lost_margin_inr, 0) AS lost_margin_inr,
    f_policy_gap, f_late_po, f_short_ship, f_spike, primary_cause
  FROM tmp_rca_events
  ORDER BY week_start, warehouse_id, sku_id;

  DROP TEMPORARY TABLE IF EXISTS tmp_rca_events;
END //

-- -------------------------------------------------------------------------------------
-- 5. Excess / obsolescence / expiry-risk inventory and its carrying cost
-- -------------------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_excess_inventory_waste //
CREATE PROCEDURE sp_excess_inventory_waste(IN p_asof DATE)
BEGIN
  DROP TEMPORARY TABLE IF EXISTS tmp_excess;

  CREATE TEMPORARY TABLE tmp_excess AS
  SELECT
    t.warehouse_id, t.warehouse_name, t.region, t.sku_id, t.sku_name, t.category, t.abc_class,
    t.closing_stock, t.avg_demand_4w, t.weeks_of_cover, t.unit_cost_inr, t.stock_value_inr,
    k.shelf_life_days, c.holding_cost_pct_annual,
    CASE WHEN t.stock_status = 'EXCESS'
         THEN GREATEST(0, t.closing_stock - c.excess_cover_weeks * t.avg_demand_4w) ELSE 0 END AS excess_units,
    GREATEST(0, t.closing_stock - c.rebalance_keep_weeks * t.avg_demand_4w)                     AS above_target_units,
    CASE WHEN t.weeks_of_cover > c.obsolete_cover_weeks THEN 1 ELSE 0 END AS obsolescence_flag,
    CASE WHEN k.shelf_life_days > 0
          AND t.weeks_of_cover * 7 > c.expiry_cover_share * k.shelf_life_days THEN 1 ELSE 0 END AS expiry_flag
  FROM vw_stock_status_all t
  JOIN dim_sku k ON k.sku_id = t.sku_id
  CROSS JOIN vw_cfg c
  WHERE t.week_end = p_asof AND t.avg_demand_4w > 0;

  -- result set 1: by warehouse
  SELECT
    warehouse_id, warehouse_name, region,
    ROUND(SUM(stock_value_inr), 0)                                                    AS total_stock_value_inr,
    ROUND(SUM(excess_units * unit_cost_inr), 0)                                       AS excess_value_inr,
    ROUND(100.0 * SUM(excess_units * unit_cost_inr) / NULLIF(SUM(stock_value_inr), 0), 1) AS excess_pct_of_stock,
    ROUND(SUM(excess_units * unit_cost_inr * holding_cost_pct_annual), 0)             AS annual_carrying_cost_on_excess_inr,
    ROUND(SUM(above_target_units * unit_cost_inr), 0)                                 AS above_target_cover_value_inr,
    ROUND(100.0 * SUM(above_target_units * unit_cost_inr) / NULLIF(SUM(stock_value_inr), 0), 1) AS above_target_pct_of_stock,
    ROUND(SUM(above_target_units * unit_cost_inr * holding_cost_pct_annual), 0)       AS annual_carrying_cost_above_target_inr,
    SUM(obsolescence_flag)                                                            AS obsolescence_risk_skus,
    ROUND(SUM(CASE WHEN obsolescence_flag = 1 THEN stock_value_inr ELSE 0 END), 0)    AS obsolescence_risk_value_inr,
    SUM(expiry_flag)                                                                  AS expiry_risk_skus,
    ROUND(SUM(CASE WHEN expiry_flag = 1 THEN stock_value_inr ELSE 0 END), 0)          AS expiry_risk_value_inr
  FROM tmp_excess
  GROUP BY warehouse_id, warehouse_name, region
  ORDER BY SUM(excess_units * unit_cost_inr) DESC;

  -- result set 2: by category
  SELECT
    category,
    ROUND(SUM(stock_value_inr), 0)                                                    AS total_stock_value_inr,
    ROUND(SUM(excess_units * unit_cost_inr), 0)                                       AS excess_value_inr,
    ROUND(100.0 * SUM(excess_units * unit_cost_inr) / NULLIF(SUM(stock_value_inr), 0), 1) AS excess_pct_of_stock,
    ROUND(SUM(excess_units * unit_cost_inr * holding_cost_pct_annual), 0)             AS annual_carrying_cost_on_excess_inr,
    ROUND(SUM(above_target_units * unit_cost_inr), 0)                                 AS above_target_cover_value_inr,
    ROUND(SUM(CASE WHEN expiry_flag = 1 THEN stock_value_inr ELSE 0 END), 0)          AS expiry_risk_value_inr
  FROM tmp_excess
  GROUP BY category
  ORDER BY SUM(excess_units * unit_cost_inr) DESC;

  -- result set 3: line detail (every excess / obsolescence / expiry-risk SKU x warehouse)
  SELECT
    warehouse_id, warehouse_name, region, sku_id, sku_name, category, abc_class,
    closing_stock, ROUND(avg_demand_4w, 1) AS avg_weekly_demand, ROUND(weeks_of_cover, 1) AS weeks_of_cover,
    ROUND(excess_units, 0)                         AS excess_units,
    ROUND(excess_units * unit_cost_inr, 0)         AS excess_value_inr,
    ROUND(stock_value_inr, 0)                      AS stock_value_inr,
    obsolescence_flag, expiry_flag
  FROM tmp_excess
  WHERE excess_units > 0 OR obsolescence_flag = 1 OR expiry_flag = 1
  ORDER BY excess_units * unit_cost_inr DESC;

  DROP TEMPORARY TABLE IF EXISTS tmp_excess;
END //

-- -------------------------------------------------------------------------------------
-- 6. Regional rebalancing: move surplus stock from over-stocked to deficit warehouses
--    Donor   : EXCESS rows; may give down to rebalance_keep_weeks of cover
--    Receiver: STOCKOUT / CRITICAL / LOW rows; topped up to rebalance_target_weeks of cover
--    Each receiver is matched to ONE donor per SKU (same region preferred, then largest surplus).
--    When several receivers want the same donor, requests are scaled down pro-rata so a donor is
--    never asked for more than its surplus.   Benefit figures are indicative, one replenishment cycle.
-- -------------------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_regional_rebalance //
CREATE PROCEDURE sp_regional_rebalance(IN p_asof DATE)
BEGIN
  DROP TEMPORARY TABLE IF EXISTS tmp_donor;
  DROP TEMPORARY TABLE IF EXISTS tmp_receiver;
  DROP TEMPORARY TABLE IF EXISTS tmp_match;
  DROP TEMPORARY TABLE IF EXISTS tmp_transfer;

  CREATE TEMPORARY TABLE tmp_donor AS
  SELECT t.sku_id, t.warehouse_id, t.region,
         FLOOR(t.closing_stock - c.rebalance_keep_weeks * t.avg_demand_4w) AS surplus_units
  FROM vw_stock_status_all t
  CROSS JOIN vw_cfg c
  WHERE t.week_end = p_asof
    AND t.stock_status = 'EXCESS'
    AND t.closing_stock - c.rebalance_keep_weeks * t.avg_demand_4w >= 1;

  CREATE TEMPORARY TABLE tmp_receiver AS
  SELECT t.sku_id, t.warehouse_id, t.region, t.stock_status, t.unit_cost_inr, t.unit_price_inr,
         CEILING(c.rebalance_target_weeks * t.avg_demand_4w - t.closing_stock) AS need_units
  FROM vw_stock_status_all t
  CROSS JOIN vw_cfg c
  WHERE t.week_end = p_asof
    AND t.stock_status IN ('STOCKOUT', 'CRITICAL', 'LOW')
    AND c.rebalance_target_weeks * t.avg_demand_4w - t.closing_stock >= 1;

  CREATE TEMPORARY TABLE tmp_match AS
  SELECT m.sku_id, m.to_warehouse_id, m.from_warehouse_id, m.to_region, m.from_region,
         m.receiver_status, m.unit_cost_inr, m.unit_price_inr, m.need_units, m.surplus_units,
         CASE WHEN m.need_units < m.surplus_units THEN m.need_units ELSE m.surplus_units END AS requested_units
  FROM (
    SELECT r.sku_id, r.warehouse_id AS to_warehouse_id, d.warehouse_id AS from_warehouse_id,
           r.region AS to_region, d.region AS from_region, r.stock_status AS receiver_status,
           r.unit_cost_inr, r.unit_price_inr, r.need_units, d.surplus_units,
           ROW_NUMBER() OVER (PARTITION BY r.sku_id, r.warehouse_id
                              ORDER BY CASE WHEN r.region = d.region THEN 0 ELSE 1 END,
                                       d.surplus_units DESC, d.warehouse_id) AS rnk
    FROM tmp_receiver r
    JOIN tmp_donor d ON d.sku_id = r.sku_id AND d.warehouse_id <> r.warehouse_id
  ) m
  WHERE m.rnk = 1;

  CREATE TEMPORARY TABLE tmp_transfer AS
  SELECT z.*,
         FLOOR(z.requested_units *
               (CASE WHEN z.surplus_units * 1.0 / z.donor_requested_total < 1.0
                     THEN z.surplus_units * 1.0 / z.donor_requested_total ELSE 1.0 END)) AS transfer_units
  FROM (
    SELECT g.*,
           SUM(g.requested_units) OVER (PARTITION BY g.sku_id, g.from_warehouse_id) AS donor_requested_total
    FROM tmp_match g
  ) z;

  -- result set 1: transfer lines
  SELECT
    k.sku_id, k.sku_name, k.category,
    fw.warehouse_id AS from_warehouse_id, fw.warehouse_name AS from_warehouse, fw.region AS from_region,
    tw.warehouse_id AS to_warehouse_id,   tw.warehouse_name AS to_warehouse,   tw.region AS to_region,
    x.receiver_status,
    x.transfer_units,
    CASE WHEN x.from_region = x.to_region THEN 1 ELSE 0 END                          AS same_region,
    ROUND(x.transfer_units * x.unit_cost_inr, 0)                                     AS stock_value_moved_inr,
    ROUND(x.transfer_units * (CASE WHEN x.from_region = x.to_region
                                   THEN c.transfer_cost_same_region_per_unit
                                   ELSE c.transfer_cost_cross_region_per_unit END), 0) AS est_freight_inr,
    ROUND(x.transfer_units * (x.unit_price_inr - x.unit_cost_inr), 0)                AS margin_protected_inr,
    ROUND(x.transfer_units * (x.unit_price_inr - x.unit_cost_inr)
          - x.transfer_units * (CASE WHEN x.from_region = x.to_region
                                     THEN c.transfer_cost_same_region_per_unit
                                     ELSE c.transfer_cost_cross_region_per_unit END), 0) AS est_net_benefit_inr
  FROM tmp_transfer x
  JOIN dim_sku k        ON k.sku_id = x.sku_id
  JOIN dim_warehouse fw ON fw.warehouse_id = x.from_warehouse_id
  JOIN dim_warehouse tw ON tw.warehouse_id = x.to_warehouse_id
  CROSS JOIN vw_cfg c
  WHERE x.transfer_units >= 1
  ORDER BY est_net_benefit_inr DESC;

  -- result set 2: flow matrix, donor warehouse -> receiving warehouse
  SELECT
    x.from_warehouse_id, x.to_warehouse_id,
    COUNT(*)                                                       AS transfer_lines,
    SUM(x.transfer_units)                                          AS units,
    ROUND(SUM(x.transfer_units * x.unit_cost_inr), 0)              AS stock_value_moved_inr,
    ROUND(SUM(x.transfer_units * (x.unit_price_inr - x.unit_cost_inr)), 0) AS margin_protected_inr
  FROM tmp_transfer x
  WHERE x.transfer_units >= 1
  GROUP BY x.from_warehouse_id, x.to_warehouse_id
  ORDER BY SUM(x.transfer_units * x.unit_cost_inr) DESC;

  DROP TEMPORARY TABLE IF EXISTS tmp_donor;
  DROP TEMPORARY TABLE IF EXISTS tmp_receiver;
  DROP TEMPORARY TABLE IF EXISTS tmp_match;
  DROP TEMPORARY TABLE IF EXISTS tmp_transfer;
END //

-- -------------------------------------------------------------------------------------
-- 7. Asset waste RCA (forklifts, reach trucks, conveyors, trucks) for months in [p_start, p_end]
--    Diagnosis precedence: RELIABILITY -> UNDER-PROVISIONED -> OVER-PROVISIONED -> OK
-- -------------------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_asset_waste_rca //
CREATE PROCEDURE sp_asset_waste_rca(IN p_start DATE, IN p_end DATE)
BEGIN
  DROP TEMPORARY TABLE IF EXISTS tmp_asset_rca;

  CREATE TEMPORARY TABLE tmp_asset_rca AS
  SELECT
    w.warehouse_id, w.warehouse_name, w.region, a.asset_type,
    COUNT(DISTINCT a.asset_id)                                   AS asset_count,
    SUM(m.scheduled_hours)                                       AS scheduled_hours,
    SUM(m.run_hours)                                             AS run_hours,
    SUM(m.idle_hours)                                            AS idle_hours,
    SUM(m.downtime_hours)                                        AS downtime_hours,
    SUM(m.breakdown_count)                                       AS breakdowns,
    SUM(m.maintenance_cost_inr)                                  AS maintenance_cost_inr,
    SUM(m.idle_hours * (a.hourly_ownership_cost_inr + c.operator_idle_share * a.hourly_operator_cost_inr)) AS idle_cost_inr,
    AVG(DATEDIFF(p_end, a.purchase_date) / 365.25)               AS avg_age_years
  FROM fact_asset_monthly m
  JOIN dim_asset     a ON a.asset_id     = m.asset_id
  JOIN dim_warehouse w ON w.warehouse_id = a.warehouse_id
  CROSS JOIN vw_cfg c
  WHERE m.month_start BETWEEN p_start AND p_end
  GROUP BY w.warehouse_id, w.warehouse_name, w.region, a.asset_type;

  -- result set 1: warehouse x asset type diagnosis
  SELECT
    r.warehouse_id, r.warehouse_name, r.region, r.asset_type, r.asset_count,
    ROUND(r.avg_age_years, 1)                                              AS avg_age_years,
    ROUND(100.0 * r.run_hours      / r.scheduled_hours, 1)                 AS utilisation_pct,
    ROUND(100.0 * r.idle_hours     / r.scheduled_hours, 1)                 AS idle_pct,
    ROUND(100.0 * r.downtime_hours / r.scheduled_hours, 1)                 AS downtime_pct,
    r.breakdowns,
    ROUND(r.maintenance_cost_inr, 0)                                       AS maintenance_cost_inr,
    ROUND(r.maintenance_cost_inr / NULLIF(r.run_hours, 0), 1)              AS maintenance_cost_per_run_hour_inr,
    ROUND(r.idle_cost_inr, 0)                                              AS idle_cost_inr,
    r.asset_count - ROUND(r.asset_count * (r.run_hours / r.scheduled_hours) / c.asset_target_util, 0) AS surplus_assets,
    CASE
      WHEN r.downtime_hours / r.scheduled_hours > c.asset_downtime_flag_pct  THEN 'RELIABILITY (ageing / breakdowns)'
      WHEN r.run_hours      / r.scheduled_hours > c.asset_overstretch_util   THEN 'UNDER-PROVISIONED (overstretched)'
      WHEN r.idle_hours     / r.scheduled_hours > c.asset_idle_flag_pct      THEN 'OVER-PROVISIONED (idle capacity)'
      ELSE 'OK'
    END                                                                    AS diagnosis
  FROM tmp_asset_rca r
  CROSS JOIN vw_cfg c
  ORDER BY r.warehouse_id, r.asset_type;

  -- result set 2: warehouse roll-up
  SELECT
    r.warehouse_id, r.warehouse_name, r.region,
    SUM(r.asset_count)                                                      AS assets,
    ROUND(100.0 * SUM(r.run_hours)      / SUM(r.scheduled_hours), 1)        AS utilisation_pct,
    ROUND(100.0 * SUM(r.idle_hours)     / SUM(r.scheduled_hours), 1)        AS idle_pct,
    ROUND(100.0 * SUM(r.downtime_hours) / SUM(r.scheduled_hours), 1)        AS downtime_pct,
    SUM(r.breakdowns)                                                       AS breakdowns,
    ROUND(SUM(r.maintenance_cost_inr), 0)                                   AS maintenance_cost_inr,
    ROUND(SUM(r.idle_cost_inr), 0)                                          AS idle_cost_inr,
    SUM(r.asset_count - ROUND(r.asset_count * (r.run_hours / r.scheduled_hours) / c.asset_target_util, 0)) AS net_surplus_assets
  FROM tmp_asset_rca r
  CROSS JOIN vw_cfg c
  GROUP BY r.warehouse_id, r.warehouse_name, r.region
  ORDER BY SUM(r.idle_cost_inr) DESC;

  DROP TEMPORARY TABLE IF EXISTS tmp_asset_rca;
END //

-- -------------------------------------------------------------------------------------
-- 8. Write every current alert into alert_log (idempotent for a given as-of date)
-- -------------------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_generate_alerts //
CREATE PROCEDURE sp_generate_alerts(IN p_asof DATE)
BEGIN
  DELETE FROM alert_log WHERE as_of_date = p_asof;

  -- stock deficits
  INSERT INTO alert_log (as_of_date, alert_type, severity, warehouse_id, sku_id, supplier_id, message, metric_value, threshold_value)
  SELECT p_asof, 'STOCK_DEFICIT',
         CASE WHEN t.stock_status IN ('STOCKOUT', 'CRITICAL') THEN 'CRITICAL' ELSE 'WARNING' END,
         t.warehouse_id, t.sku_id, t.supplier_id,
         CONCAT(t.warehouse_name, ' | ', t.sku_name, ' | ', t.stock_status, ' | cover ',
                ROUND(COALESCE(t.weeks_of_cover, 0), 2), ' wks'),
         ROUND(COALESCE(t.weeks_of_cover, 0), 2),
         c.low_cover_weeks
  FROM vw_stock_status_all t
  CROSS JOIN vw_cfg c
  WHERE t.week_end = p_asof
    AND t.stock_status IN ('STOCKOUT', 'CRITICAL', 'LOW');

  -- pipeline delays (open POs past promise date)
  INSERT INTO alert_log (as_of_date, alert_type, severity, warehouse_id, sku_id, supplier_id, message, metric_value, threshold_value)
  SELECT p_asof, 'PIPELINE_DELAY',
         CASE WHEN DATEDIFF(p_asof, p.promised_date) >= c.overdue_critical_days THEN 'CRITICAL' ELSE 'WARNING' END,
         p.warehouse_id, p.sku_id, p.supplier_id,
         CONCAT(p.po_id, ' | ', s.supplier_name, ' | ', DATEDIFF(p_asof, p.promised_date), ' days past promise | INR ',
                ROUND(p.po_value_inr, 0)),
         DATEDIFF(p_asof, p.promised_date),
         c.overdue_warn_days
  FROM fact_purchase_orders p
  JOIN dim_supplier s ON s.supplier_id = p.supplier_id
  CROSS JOIN vw_cfg c
  WHERE p.order_date <= p_asof
    AND (p.received_date IS NULL OR p.received_date > p_asof)
    AND DATEDIFF(p_asof, p.promised_date) >= c.overdue_warn_days;

  -- storage capacity risk
  INSERT INTO alert_log (as_of_date, alert_type, severity, warehouse_id, sku_id, supplier_id, message, metric_value, threshold_value)
  SELECT p_asof, 'CAPACITY_RISK',
         CASE WHEN u.util >= c.capacity_critical_util THEN 'CRITICAL' ELSE 'WARNING' END,
         u.warehouse_id, NULL, NULL,
         CONCAT(u.warehouse_name, ' | storage utilisation ', ROUND(100 * u.util, 1), '%'),
         ROUND(u.util, 3),
         c.capacity_warn_util
  FROM (
    SELECT t.warehouse_id, t.warehouse_name, SUM(t.closing_stock) * 1.0 / w.capacity_units AS util
    FROM vw_stock_status_all t
    JOIN dim_warehouse w ON w.warehouse_id = t.warehouse_id
    WHERE t.week_end = p_asof
    GROUP BY t.warehouse_id, t.warehouse_name, w.capacity_units
  ) u
  CROSS JOIN vw_cfg c
  WHERE u.util >= c.capacity_warn_util;

  SELECT alert_type, severity, COUNT(*) AS alerts
  FROM alert_log
  WHERE as_of_date = p_asof
  GROUP BY alert_type, severity
  ORDER BY alert_type, severity;
END //

DELIMITER ;
