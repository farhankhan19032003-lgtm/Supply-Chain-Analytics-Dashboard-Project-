// Query name: Inventory_Clean    (OUTPUT -> Close & Load To... > Table (or Only Create Connection + Data Model))
// De-duplicates, merges four sources (regional extracts + warehouse / SKU / supplier masters) and adds measures.
// Expected result: 74,880 rows (52 weeks x 12 warehouses x 120 SKUs). See powerquery/expected_results.csv.
let
    Source   = Inventory_Staged,

    // 1. remove exact duplicate keys (same week + warehouse + SKU)
    Dedup    = Table.Distinct(Source, {"week_start", "warehouse_key", "sku_id"}),

    // 2. merge warehouse master (works for codes AND names via WH_Lookup)
    WhJoin   = Table.NestedJoin(Dedup, {"warehouse_key"}, WH_Lookup, {"warehouse_key"}, "wh", JoinKind.LeftOuter),
    WhExp    = Table.ExpandTableColumn(WhJoin, "wh", {"warehouse_id", "warehouse_name", "city", "state", "region"}),

    // 3. merge SKU master
    SkuJoin  = Table.NestedJoin(WhExp, {"sku_id"}, Master_SKU, {"sku_id"}, "sku", JoinKind.LeftOuter),
    SkuExp   = Table.ExpandTableColumn(SkuJoin, "sku",
                 {"sku_name", "category", "abc_class", "unit_cost_inr", "unit_price_inr", "primary_supplier_id"}),

    // 4. merge supplier master (via the SKU's primary supplier)
    SupJoin  = Table.NestedJoin(SkuExp, {"primary_supplier_id"}, Master_Supplier, {"supplier_id"}, "sup", JoinKind.LeftOuter),
    SupExp   = Table.ExpandTableColumn(SupJoin, "sup", {"supplier_name", "origin_region"}, {"supplier_name", "supplier_origin_region"}),

    // 5. calendar + measures
    WeekEnd  = Table.AddColumn(SupExp, "week_end", each Date.AddDays([week_start], 6), type date),
    FY       = Table.AddColumn(WeekEnd, "fiscal_year",
                 each if Date.Month([week_start]) >= 4
                      then "FY" & Text.End(Text.From(Date.Year([week_start]) + 1), 2)
                      else "FY" & Text.End(Text.From(Date.Year([week_start])), 2), type text),
    StockVal = Table.AddColumn(FY, "stock_value_inr", each [closing_stock] * [unit_cost_inr], type number),
    Cogs     = Table.AddColumn(StockVal, "cogs_inr", each [units_sold] * [unit_cost_inr], type number),
    LostRev  = Table.AddColumn(Cogs, "lost_revenue_inr", each [lost_units] * [unit_price_inr], type number),
    LostMar  = Table.AddColumn(LostRev, "lost_margin_inr", each [lost_units] * ([unit_price_inr] - [unit_cost_inr]), type number),

    // 6. final column order
    Ordered  = Table.SelectColumns(LostMar, {"week_start", "week_end", "fiscal_year", "region", "warehouse_id", "warehouse_name",
                 "city", "state", "sku_id", "sku_name", "category", "abc_class", "primary_supplier_id", "supplier_name",
                 "supplier_origin_region", "opening_stock", "receipts", "demand_units", "units_sold", "lost_units",
                 "closing_stock", "unit_cost_inr", "unit_price_inr", "stock_value_inr", "cogs_inr", "lost_revenue_inr",
                 "lost_margin_inr", "dq_lost_filled", "dq_closing_repaired", "region_extract"})
in
    Ordered
