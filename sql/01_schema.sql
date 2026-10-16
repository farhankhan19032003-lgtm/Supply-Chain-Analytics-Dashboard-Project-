-- =====================================================================================
-- 01_schema.sql  |  Supply Chain Analytics Platform  |  MySQL 8.0+
-- Creates the database, dimension tables, fact tables, config table and alert log.
-- Run order: 01_schema -> 02_load_data -> 03_views -> 04_stored_procedures -> 05_analysis_queries
-- =====================================================================================

CREATE DATABASE IF NOT EXISTS supply_chain_analytics
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE supply_chain_analytics;

DROP TABLE IF EXISTS alert_log;
DROP TABLE IF EXISTS fact_asset_monthly;
DROP TABLE IF EXISTS fact_purchase_orders;
DROP TABLE IF EXISTS fact_inventory_weekly;
DROP TABLE IF EXISTS dim_asset;
DROP TABLE IF EXISTS dim_week;
DROP TABLE IF EXISTS dim_sku;
DROP TABLE IF EXISTS dim_supplier;
DROP TABLE IF EXISTS dim_warehouse;
DROP TABLE IF EXISTS cfg_thresholds;

-- ---------------------------------------------------------------- dimensions
CREATE TABLE dim_warehouse (
  warehouse_id    CHAR(4)       NOT NULL,
  warehouse_name  VARCHAR(50)   NOT NULL,
  city            VARCHAR(40)   NOT NULL,
  state           VARCHAR(40)   NOT NULL,
  region          VARCHAR(10)   NOT NULL,
  latitude        DECIMAL(9,6)  NOT NULL,
  longitude       DECIMAL(9,6)  NOT NULL,
  capacity_units  INT           NOT NULL,
  PRIMARY KEY (warehouse_id)
) ENGINE=InnoDB;

CREATE TABLE dim_supplier (
  supplier_id         CHAR(5)      NOT NULL,
  supplier_name       VARCHAR(60)  NOT NULL,
  category            VARCHAR(40)  NOT NULL,
  origin_city         VARCHAR(40)  NOT NULL,
  origin_region       VARCHAR(10)  NOT NULL,
  supplier_tier       VARCHAR(10)  NOT NULL,
  payment_terms_days  INT          NOT NULL,
  PRIMARY KEY (supplier_id)
) ENGINE=InnoDB;

CREATE TABLE dim_sku (
  sku_id               CHAR(6)        NOT NULL,
  sku_name             VARCHAR(60)    NOT NULL,
  category             VARCHAR(40)    NOT NULL,
  unit_cost_inr        DECIMAL(10,2)  NOT NULL,
  unit_price_inr       DECIMAL(10,2)  NOT NULL,
  base_weekly_demand   DECIMAL(10,1)  NOT NULL,
  lead_time_days       INT            NOT NULL,
  shelf_life_days      INT            NOT NULL,   -- 0 = non-perishable
  case_pack            INT            NOT NULL,
  primary_supplier_id  CHAR(5)        NOT NULL,
  abc_class            CHAR(1)        NOT NULL,
  PRIMARY KEY (sku_id),
  CONSTRAINT fk_sku_supplier FOREIGN KEY (primary_supplier_id) REFERENCES dim_supplier (supplier_id)
) ENGINE=InnoDB;

CREATE TABLE dim_week (
  week_start     DATE         NOT NULL,
  week_end       DATE         NOT NULL,
  week_no        INT          NOT NULL,
  calendar_year  INT          NOT NULL,
  month_no       INT          NOT NULL,
  month_name     CHAR(3)      NOT NULL,
  quarter        CHAR(2)      NOT NULL,
  fiscal_year    CHAR(4)      NOT NULL,           -- Indian FY (Apr-Mar)
  season         VARCHAR(20)  NOT NULL,
  PRIMARY KEY (week_start)
) ENGINE=InnoDB;

CREATE TABLE dim_asset (
  asset_id                   CHAR(7)        NOT NULL,
  warehouse_id               CHAR(4)        NOT NULL,
  asset_type                 VARCHAR(30)    NOT NULL,
  purchase_date              DATE           NOT NULL,
  purchase_cost_inr          DECIMAL(12,2)  NOT NULL,
  useful_life_years          INT            NOT NULL,
  rated_hours_per_month      INT            NOT NULL,
  hourly_ownership_cost_inr  DECIMAL(10,2)  NOT NULL,
  hourly_operator_cost_inr   DECIMAL(10,2)  NOT NULL,
  PRIMARY KEY (asset_id),
  CONSTRAINT fk_asset_wh FOREIGN KEY (warehouse_id) REFERENCES dim_warehouse (warehouse_id)
) ENGINE=InnoDB;

CREATE TABLE cfg_thresholds (
  param        VARCHAR(50)   NOT NULL,
  param_value  DECIMAL(12,4) NOT NULL,
  description  VARCHAR(200),
  PRIMARY KEY (param)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- facts
CREATE TABLE fact_inventory_weekly (
  week_start             DATE          NOT NULL,
  week_end               DATE          NOT NULL,
  warehouse_id           CHAR(4)       NOT NULL,
  sku_id                 CHAR(6)       NOT NULL,
  opening_stock          INT           NOT NULL,
  receipts               INT           NOT NULL,
  demand_units           INT           NOT NULL,
  units_sold             INT           NOT NULL,
  lost_units             INT           NOT NULL,
  closing_stock          INT           NOT NULL,
  on_order_units         INT           NOT NULL,
  reorder_point_units    INT           NOT NULL,
  forecast_weekly_units  DECIMAL(10,1) NOT NULL,
  PRIMARY KEY (week_start, warehouse_id, sku_id),
  KEY idx_inv_ws (warehouse_id, sku_id, week_start),
  KEY idx_inv_weekend (week_end),
  CONSTRAINT fk_inv_wh  FOREIGN KEY (warehouse_id) REFERENCES dim_warehouse (warehouse_id),
  CONSTRAINT fk_inv_sku FOREIGN KEY (sku_id)       REFERENCES dim_sku (sku_id)
) ENGINE=InnoDB;

CREATE TABLE fact_purchase_orders (
  po_id          CHAR(9)        NOT NULL,
  warehouse_id   CHAR(4)        NOT NULL,
  sku_id         CHAR(6)        NOT NULL,
  supplier_id    CHAR(5)        NOT NULL,
  order_date     DATE           NOT NULL,
  promised_date  DATE           NOT NULL,
  received_date  DATE           NULL,             -- NULL = still open / in the pipeline
  ordered_qty    INT            NOT NULL,
  received_qty   INT            NOT NULL,
  unit_cost_inr  DECIMAL(10,2)  NOT NULL,
  po_value_inr   DECIMAL(14,2)  NOT NULL,
  PRIMARY KEY (po_id),
  KEY idx_po_pair (warehouse_id, sku_id, promised_date),
  KEY idx_po_supplier (supplier_id, received_date),
  CONSTRAINT fk_po_wh   FOREIGN KEY (warehouse_id) REFERENCES dim_warehouse (warehouse_id),
  CONSTRAINT fk_po_sku  FOREIGN KEY (sku_id)       REFERENCES dim_sku (sku_id),
  CONSTRAINT fk_po_sup  FOREIGN KEY (supplier_id)  REFERENCES dim_supplier (supplier_id)
) ENGINE=InnoDB;

CREATE TABLE fact_asset_monthly (
  asset_id              CHAR(7)        NOT NULL,
  month_start           DATE           NOT NULL,
  scheduled_hours       INT            NOT NULL,
  run_hours             DECIMAL(8,1)   NOT NULL,
  idle_hours            DECIMAL(8,1)   NOT NULL,
  downtime_hours        DECIMAL(8,1)   NOT NULL,
  breakdown_count       INT            NOT NULL,
  maintenance_cost_inr  DECIMAL(12,0)  NOT NULL,
  energy_cost_inr       DECIMAL(12,0)  NOT NULL,
  PRIMARY KEY (asset_id, month_start),
  CONSTRAINT fk_am_asset FOREIGN KEY (asset_id) REFERENCES dim_asset (asset_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- output table for custom alerts
-- Populated by sp_generate_alerts(); Tableau / Excel read from here.
CREATE TABLE alert_log (
  alert_id         BIGINT         NOT NULL AUTO_INCREMENT,
  as_of_date       DATE           NOT NULL,
  alert_type       VARCHAR(20)    NOT NULL,       -- STOCK_DEFICIT | PIPELINE_DELAY | CAPACITY_RISK
  severity         VARCHAR(10)    NOT NULL,       -- CRITICAL | WARNING
  warehouse_id     CHAR(4)        NULL,
  sku_id           CHAR(6)        NULL,
  supplier_id      CHAR(5)        NULL,
  message          VARCHAR(300)   NOT NULL,
  metric_value     DECIMAL(14,3)  NULL,
  threshold_value  DECIMAL(14,3)  NULL,
  created_at       TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (alert_id),
  KEY idx_alert_asof (as_of_date, alert_type, severity)
) ENGINE=InnoDB;
