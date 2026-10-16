// Query name: WH_Lookup      (staging query -> Enable Load OFF)
// The regional files identify a warehouse either by CODE (WH07) or by NAME (Bhiwandi DC).
// This lookup holds both spellings as keys so a single merge resolves either one.
let
    ByCode   = Table.AddColumn(Master_Warehouse, "warehouse_key", each Text.Upper([warehouse_id]), type text),
    ByName   = Table.AddColumn(Master_Warehouse, "warehouse_key", each Text.Upper([warehouse_name]), type text),
    Combined = Table.Combine({ByCode, ByName})
in
    Combined
