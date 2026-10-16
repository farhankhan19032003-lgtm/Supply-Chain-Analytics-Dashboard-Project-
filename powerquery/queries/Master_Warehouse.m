// Query name: Master_Warehouse   (staging query -> Enable Load OFF)
let
    Source   = Excel.Workbook(File.Contents(pFolder & "Master_Data_Raw.xlsx"), null, true),
    Sheet    = Source{[Item = "Warehouse_Master", Kind = "Sheet"]}[Data],
    Skipped  = Table.Skip(Sheet, 1),
    Promoted = Table.PromoteHeaders(Skipped, [PromoteAllScalars = true]),
    Renamed  = Table.RenameColumns(Promoted, {
                 {"Code", "warehouse_id"}, {"Name", "warehouse_name"}, {"City", "city"}, {"State", "state"},
                 {"Region", "region"}, {"Lat", "latitude"}, {"Lon", "longitude"}, {"Capacity (units)", "capacity_units"}}),
    Cleaned  = Table.TransformColumns(Renamed, {
                 {"warehouse_id", each Text.Upper(Text.Trim(_)), type text},
                 {"warehouse_name", each Text.Trim(_), type text}}),
    Typed    = Table.TransformColumnTypes(Cleaned, {{"latitude", type number}, {"longitude", type number},
                 {"capacity_units", Int64.Type}})
in
    Typed
