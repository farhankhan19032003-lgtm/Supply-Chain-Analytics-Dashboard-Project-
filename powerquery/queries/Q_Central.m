// Query name: Q_Central      (staging query -> Enable Load OFF)
// Quirks handled: date column carries a time stamp ("2025-10-06 00:00:00"), closing_stock blank on ~12% of
//                 rows (rebuilt from opening + receipts - sold), a few blank lost_units.
let
    Source   = Csv.Document(File.Contents(pFolder & "Central_Weekly_Stock_FY26.csv"),
                 [Delimiter = ",", Columns = 9, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Renamed  = Table.RenameColumns(Promoted, {
                 {"week_start", "week_start_raw"}, {"warehouse_id", "warehouse_raw"}, {"sku_id", "sku_raw"}}),
    Std      = fnStandardize(Renamed, "yyyy-MM-dd", "Central")
in
    Std
