// Query name: Q_South        (staging query -> Enable Load OFF)
// Quirks handled: semicolon delimiter, dd-MMM-yyyy dates ("06-Oct-2025"), the text "NA" inside the
//                 Lost Sales column (-> filled as demand - sold).
let
    Source   = Csv.Document(File.Contents(pFolder & "South_Weekly_Stock_FY26.csv"),
                 [Delimiter = ";", Columns = 9, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Renamed  = Table.RenameColumns(Promoted, {
                 {"Week", "week_start_raw"}, {"Warehouse_ID", "warehouse_raw"}, {"Item", "sku_raw"},
                 {"Opening", "opening_stock"}, {"Inbound", "receipts"}, {"Demand", "demand_units"},
                 {"Units Sold", "units_sold"}, {"Lost Sales", "lost_units"}, {"Closing", "closing_stock"}}),
    Std      = fnStandardize(Renamed, "dd-MMM-yyyy", "South")
in
    Std
