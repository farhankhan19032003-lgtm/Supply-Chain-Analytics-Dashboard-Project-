// Query name: DQ_Log            (OUTPUT -> load to a worksheet; this is your data-quality audit trail)
// One row per source region: rows staged, rows kept, duplicates removed, values repaired.
let
    Staged  = Table.Group(Inventory_Staged, {"region_extract"}, {
                {"rows_staged_non_blank", each Table.RowCount(_), Int64.Type},
                {"closing_stock_repaired", each List.Sum([dq_closing_repaired]), Int64.Type},
                {"lost_units_filled", each List.Sum([dq_lost_filled]), Int64.Type}}),
    Kept    = Table.Group(Inventory_Clean, {"region_extract"}, {{"rows_clean", each Table.RowCount(_), Int64.Type}}),
    Joined  = Table.NestedJoin(Staged, {"region_extract"}, Kept, {"region_extract"}, "k", JoinKind.LeftOuter),
    Expanded = Table.ExpandTableColumn(Joined, "k", {"rows_clean"}),
    WithDup = Table.AddColumn(Expanded, "duplicates_removed", each [rows_staged_non_blank] - [rows_clean], Int64.Type)
in
    WithDup
