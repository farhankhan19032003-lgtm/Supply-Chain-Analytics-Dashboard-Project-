// Query name: fnStandardize
// Input : a regional table whose columns have ALREADY been renamed to the standard raw names
//           week_start_raw, warehouse_raw, sku_raw, opening_stock, receipts, demand_units,
//           units_sold, lost_units, closing_stock      (extra columns such as Remarks are dropped)
// Output: one typed, repaired table with the same schema for every region.
// Rules : - fully blank rows removed
//         - dates parsed with the region's explicit format; rows whose date cannot be parsed are dropped
//         - warehouse + SKU keys trimmed and upper-cased (WH03 , sku112 -> WH03, SKU112)
//         - numbers cleaned by fnToNumber
//         - lost_units missing  -> demand_units - units_sold            (flag dq_lost_filled = 1)
//         - closing_stock missing or negative -> opening + receipts - units_sold (flag dq_closing_repaired = 1)
(src as table, dateFmt as text, regionName as text) as table =>
let
    Wanted   = {"week_start_raw", "warehouse_raw", "sku_raw", "opening_stock", "receipts", "demand_units",
                "units_sold", "lost_units", "closing_stock"},
    Keep     = Table.SelectColumns(src, Wanted),

    NonBlank = Table.SelectRows(Keep, each
                 List.NonNullCount(List.Transform(Record.FieldValues(_),
                     each if _ is text and Text.Trim(_) = "" then null else _)) > 0),

    WithDate = Table.AddColumn(NonBlank, "week_start", each fnToDate([week_start_raw], dateFmt), type nullable date),
    WithWh   = Table.AddColumn(WithDate, "warehouse_key", each Text.Upper(Text.Trim(Text.From([warehouse_raw]))), type text),
    WithSku  = Table.AddColumn(WithWh, "sku_id", each Text.Upper(Text.Trim(Text.From([sku_raw]))), type text),

    NumCols  = {"opening_stock", "receipts", "demand_units", "units_sold", "lost_units", "closing_stock"},
    Nums     = Table.TransformColumns(WithSku, List.Transform(NumCols, each {_, fnToNumber, type nullable number})),

    LostFlag = Table.AddColumn(Nums, "dq_lost_filled",
                 each if [lost_units] = null and [demand_units] <> null and [units_sold] <> null then 1 else 0, Int64.Type),
    LostVal  = Table.AddColumn(LostFlag, "lost_clean",
                 each if [lost_units] <> null then [lost_units] else [demand_units] - [units_sold], type number),

    CloseFlag = Table.AddColumn(LostVal, "dq_closing_repaired",
                 each if [closing_stock] = null or [closing_stock] < 0 then 1 else 0, Int64.Type),
    CloseVal  = Table.AddColumn(CloseFlag, "closing_clean",
                 each if [dq_closing_repaired] = 0 then [closing_stock] else [opening_stock] + [receipts] - [units_sold], type number),

    WithRegion = Table.AddColumn(CloseVal, "region_extract", each regionName, type text),
    Dated      = Table.SelectRows(WithRegion, each [week_start] <> null),

    Out     = Table.SelectColumns(Dated, {"week_start", "warehouse_key", "sku_id", "opening_stock", "receipts",
                "demand_units", "units_sold", "lost_clean", "closing_clean", "dq_lost_filled",
                "dq_closing_repaired", "region_extract"}),
    Renamed = Table.RenameColumns(Out, {{"lost_clean", "lost_units"}, {"closing_clean", "closing_stock"}}),
    Typed   = Table.TransformColumnTypes(Renamed, {{"opening_stock", Int64.Type}, {"receipts", Int64.Type},
                {"demand_units", Int64.Type}, {"units_sold", Int64.Type}, {"lost_units", Int64.Type},
                {"closing_stock", Int64.Type}})
in
    Typed
