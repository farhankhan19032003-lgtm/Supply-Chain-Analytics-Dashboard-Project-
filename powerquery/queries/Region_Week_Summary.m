// Query name: Region_Week_Summary   (OUTPUT -> table that feeds the Excel KPI charts)
let
    Src     = Inventory_Clean,
    Grouped = Table.Group(Src, {"region", "week_start"}, {
                {"demand_units", each List.Sum([demand_units]), Int64.Type},
                {"units_sold", each List.Sum([units_sold]), Int64.Type},
                {"lost_units", each List.Sum([lost_units]), Int64.Type},
                {"stock_value_inr", each List.Sum([stock_value_inr]), type number},
                {"lost_revenue_inr", each List.Sum([lost_revenue_inr]), type number}}),
    WithFill = Table.AddColumn(Grouped, "fill_rate_pct", each Number.Round(100 * [units_sold] / [demand_units], 2), type number),
    Sorted   = Table.Sort(WithFill, {{"week_start", Order.Ascending}, {"region", Order.Ascending}})
in
    Sorted
