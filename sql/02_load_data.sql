-- =====================================================================================
-- 02_load_data.sql  |  Loads the CSVs in data/clean/ into MySQL.
--
-- Option A (fast): LOAD DATA LOCAL INFILE  (this file)
--   1. Edit the absolute path in each LOAD DATA statement below to your of the data/clean folder (forward slashes, trailing slash).
--   2. The server must allow local_infile:  SET GLOBAL local_infile = 1;
--      and the client must too (MySQL Workbench: Connection > Advanced > Others: OPT_LOCAL_INFILE=1;
--      mysql CLI: mysql --local-infile=1 -u root -p).
--
-- Option B (no config): MySQL Workbench > right-click table > "Table Data Import Wizard" > pick the CSV.
--   Load in this order: dim_warehouse, dim_supplier, dim_sku, dim_week, dim_asset, cfg_thresholds,
--   fact_inventory_weekly, fact_purchase_orders, fact_asset_monthly.
-- =====================================================================================
USE supply_chain_analytics;

-- EDIT the path in each statement below if the project folder moves (LOAD DATA cannot take a variable
-- file name, and cannot run inside a prepared statement).
SET FOREIGN_KEY_CHECKS = 0;

LOAD DATA LOCAL INFILE 'C:/Users/HP/Downloads/Supply_Chain_Analytics_Platform/Supply_Chain_Analytics_Platform/data/clean/dim_warehouse.csv' INTO TABLE dim_warehouse
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\r\n' IGNORE 1 LINES;

LOAD DATA LOCAL INFILE 'C:/Users/HP/Downloads/Supply_Chain_Analytics_Platform/Supply_Chain_Analytics_Platform/data/clean/dim_supplier.csv' INTO TABLE dim_supplier
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\r\n' IGNORE 1 LINES;

LOAD DATA LOCAL INFILE 'C:/Users/HP/Downloads/Supply_Chain_Analytics_Platform/Supply_Chain_Analytics_Platform/data/clean/dim_sku.csv' INTO TABLE dim_sku
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\r\n' IGNORE 1 LINES;

LOAD DATA LOCAL INFILE 'C:/Users/HP/Downloads/Supply_Chain_Analytics_Platform/Supply_Chain_Analytics_Platform/data/clean/dim_week.csv' INTO TABLE dim_week
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\r\n' IGNORE 1 LINES;

LOAD DATA LOCAL INFILE 'C:/Users/HP/Downloads/Supply_Chain_Analytics_Platform/Supply_Chain_Analytics_Platform/data/clean/dim_asset.csv' INTO TABLE dim_asset
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\r\n' IGNORE 1 LINES;

LOAD DATA LOCAL INFILE 'C:/Users/HP/Downloads/Supply_Chain_Analytics_Platform/Supply_Chain_Analytics_Platform/data/clean/cfg_thresholds.csv' INTO TABLE cfg_thresholds
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\r\n' IGNORE 1 LINES;

LOAD DATA LOCAL INFILE 'C:/Users/HP/Downloads/Supply_Chain_Analytics_Platform/Supply_Chain_Analytics_Platform/data/clean/fact_inventory_weekly.csv' INTO TABLE fact_inventory_weekly
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\r\n' IGNORE 1 LINES;

-- received_date is empty for open POs -> must become NULL, so it is read into a user variable first.
LOAD DATA LOCAL INFILE 'C:/Users/HP/Downloads/Supply_Chain_Analytics_Platform/Supply_Chain_Analytics_Platform/data/clean/fact_purchase_orders.csv' INTO TABLE fact_purchase_orders
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\r\n' IGNORE 1 LINES
  (po_id, warehouse_id, sku_id, supplier_id, order_date, promised_date, @received_date,
   ordered_qty, received_qty, unit_cost_inr, po_value_inr)
  SET received_date = NULLIF(@received_date, '');

LOAD DATA LOCAL INFILE 'C:/Users/HP/Downloads/Supply_Chain_Analytics_Platform/Supply_Chain_Analytics_Platform/data/clean/fact_asset_monthly.csv' INTO TABLE fact_asset_monthly
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\r\n' IGNORE 1 LINES;

SET FOREIGN_KEY_CHECKS = 1;

-- ------------------------------------------------------------------ post-load reconciliation
-- Expected: 12 | 22 | 120 | 104 | 291 | 19 | 149760 | 31991 (652 open) | 6984
SELECT 'dim_warehouse' AS tbl, COUNT(*) AS row_count FROM dim_warehouse
UNION ALL SELECT 'dim_supplier', COUNT(*) FROM dim_supplier
UNION ALL SELECT 'dim_sku', COUNT(*) FROM dim_sku
UNION ALL SELECT 'dim_week', COUNT(*) FROM dim_week
UNION ALL SELECT 'dim_asset', COUNT(*) FROM dim_asset
UNION ALL SELECT 'cfg_thresholds', COUNT(*) FROM cfg_thresholds
UNION ALL SELECT 'fact_inventory_weekly', COUNT(*) FROM fact_inventory_weekly
UNION ALL SELECT 'fact_purchase_orders', COUNT(*) FROM fact_purchase_orders
UNION ALL SELECT 'fact_purchase_orders (open)', COUNT(*) FROM fact_purchase_orders WHERE received_date IS NULL
UNION ALL SELECT 'fact_asset_monthly', COUNT(*) FROM fact_asset_monthly;
