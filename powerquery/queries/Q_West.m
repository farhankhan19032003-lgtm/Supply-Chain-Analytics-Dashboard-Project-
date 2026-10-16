// Query name: Q_West         (staging query -> Enable Load OFF)
// Quirks handled: 3 preamble lines above the header (report title, generator line, blank line),
//                 different column names, yyyy/MM/dd dates, warehouse given by NAME ("Bhiwandi DC") not code.
//                 The name -> code translation happens in Inventory_Clean via WH_Lookup.
let
    Source   = Csv.Document(File.Contents(pFolder & "West_Weekly_Stock_FY26.csv"),
                 [Delimiter = ",", Columns = 9, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Skipped  = Table.Skip(Source, 3),
    Promoted = Table.PromoteHeaders(Skipped, [PromoteAllScalars = true]),
    Renamed  = Table.RenameColumns(Promoted, {
                 {"week_start", "week_start_raw"}, {"warehouse", "warehouse_raw"}, {"sku", "sku_raw"},
                 {"open_qty", "opening_stock"}, {"recv_qty", "receipts"}, {"demand_qty", "demand_units"},
                 {"sales_qty", "units_sold"}, {"lost_qty", "lost_units"}, {"close_qty", "closing_stock"}}),
    Std      = fnStandardize(Renamed, "yyyy/MM/dd", "West")
in
    Std
