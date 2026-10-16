// Query name: Q_North        (staging query -> right-click > Enable Load OFF)
// Quirks handled: dd-MM-yyyy dates, trailing spaces in WH Code, lower-case SKU codes, "1,689" text numbers,
//                 duplicate rows (removed later), empty rows, free-text Remarks column.
let
    Source   = Csv.Document(File.Contents(pFolder & "North_Weekly_Stock_FY26.csv"),
                 [Delimiter = ",", Columns = 10, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Renamed  = Table.RenameColumns(Promoted, {
                 {"Wk Start", "week_start_raw"}, {"WH Code", "warehouse_raw"}, {"SKU Code", "sku_raw"},
                 {"Opening Stock", "opening_stock"}, {"Receipts", "receipts"}, {"Demand", "demand_units"},
                 {"Sold", "units_sold"}, {"Lost", "lost_units"}, {"Closing Stock", "closing_stock"}}),
    Std      = fnStandardize(Renamed, "dd-MM-yyyy", "North")
in
    Std
