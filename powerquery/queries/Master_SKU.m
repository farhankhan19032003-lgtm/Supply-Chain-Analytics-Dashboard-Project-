// Query name: Master_SKU     (staging query -> Enable Load OFF)
// Quirks handled: 2 title rows above the header, lower-case SKU codes, padded UPPER-CASE descriptions.
let
    Source   = Excel.Workbook(File.Contents(pFolder & "Master_Data_Raw.xlsx"), null, true),
    Sheet    = Source{[Item = "SKU_Master", Kind = "Sheet"]}[Data],
    Skipped  = Table.Skip(Sheet, 2),
    Promoted = Table.PromoteHeaders(Skipped, [PromoteAllScalars = true]),
    Renamed  = Table.RenameColumns(Promoted, {
                 {"SKU Code", "sku_id"}, {"Item Description", "sku_name"}, {"Category", "category"},
                 {"Unit Cost (INR)", "unit_cost_inr"}, {"Unit Price (INR)", "unit_price_inr"},
                 {"Lead Time (days)", "lead_time_days"}, {"Primary Supplier Code", "primary_supplier_id"},
                 {"ABC", "abc_class"}}),
    Cleaned  = Table.TransformColumns(Renamed, {
                 {"sku_id", each Text.Upper(Text.Trim(_)), type text},
                 {"sku_name", each Text.Proper(Text.Trim(_)), type text},
                 {"category", each Text.Trim(_), type text},
                 {"primary_supplier_id", each Text.Upper(Text.Trim(_)), type text},
                 {"abc_class", each Text.Upper(Text.Trim(_)), type text}}),
    Typed    = Table.TransformColumnTypes(Cleaned, {{"unit_cost_inr", type number}, {"unit_price_inr", type number},
                 {"lead_time_days", Int64.Type}})
in
    Typed
