// Query name: Inventory_Staged   (staging query -> Enable Load OFF)
// Stacks the five standardised regional tables (append). Duplicates are still present at this point,
// so DQ_Log can report how many were removed.
let
    Combined = Table.Combine({Q_North, Q_West, Q_South, Q_East, Q_Central})
in
    Combined
