// Query name: Q_East         (staging query -> Enable Load OFF)
// Quirks handled: columns in a different order, dd/MM/yyyy dates, a few negative Closing Stock typos
//                 (repaired as opening + receipts - sold and flagged in dq_closing_repaired).
let
    Source   = Csv.Document(File.Contents(pFolder & "East_Weekly_Stock_FY26.csv"),
                 [Delimiter = ",", Columns = 9, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Renamed  = Table.RenameColumns(Promoted, {
                 {"SKU", "sku_raw"}, {"Warehouse", "warehouse_raw"}, {"Week Commencing", "week_start_raw"},
                 {"Closing Stock", "closing_stock"}, {"Units Sold", "units_sold"}, {"Demand", "demand_units"},
                 {"Lost Units", "lost_units"}, {"Receipts", "receipts"}, {"Opening Stock", "opening_stock"}}),
    Std      = fnStandardize(Renamed, "dd/MM/yyyy", "East")
in
    Std
