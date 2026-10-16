// Query name: fnToDate
// Parses a date that arrives as text using an explicit format (each region exports a different one).
//   North  dd-MM-yyyy       West  yyyy/MM/dd       South  dd-MMM-yyyy
//   East   dd/MM/yyyy       Central yyyy-MM-dd (value also carries " 00:00:00", which is cut off)
// Explicit formats avoid the classic 03/04/2025 day-vs-month ambiguity.
(x as any, fmt as text) as nullable date =>
let
    t   = if x = null then null else Text.Trim(Text.From(x)),
    t10 = if t = null or t = "" then null
          else if fmt = "yyyy-MM-dd" then Text.Start(t, 10)
          else t,
    d   = if t10 = null then null
          else try Date.FromText(t10, [Format = fmt, Culture = "en-US"]) otherwise null
in
    d
