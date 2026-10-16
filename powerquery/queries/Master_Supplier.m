// Query name: Master_Supplier   (staging query -> Enable Load OFF)
// Quirks handled: 1 title row, supplier names that are UPPER-CASE or padded with spaces.
let
    Source   = Excel.Workbook(File.Contents(pFolder & "Master_Data_Raw.xlsx"), null, true),
    Sheet    = Source{[Item = "Supplier_Master", Kind = "Sheet"]}[Data],
    Skipped  = Table.Skip(Sheet, 1),
    Promoted = Table.PromoteHeaders(Skipped, [PromoteAllScalars = true]),
    Renamed  = Table.RenameColumns(Promoted, {
                 {"Supplier Code", "supplier_id"}, {"Supplier Name", "supplier_name"}, {"Category", "supplier_category"},
                 {"Origin City", "origin_city"}, {"Origin Region", "origin_region"},
                 {"Payment Terms (days)", "payment_terms_days"}}),
    Cleaned  = Table.TransformColumns(Renamed, {
                 {"supplier_id", each Text.Upper(Text.Trim(_)), type text},
                 {"supplier_name", each Text.Proper(Text.Trim(_)), type text}}),
    Typed    = Table.TransformColumnTypes(Cleaned, {{"payment_terms_days", Int64.Type}})
in
    Typed
