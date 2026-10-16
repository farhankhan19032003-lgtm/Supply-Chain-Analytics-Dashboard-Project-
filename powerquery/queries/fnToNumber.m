// Query name: fnToNumber
// Cleans a numeric value that arrives as text: trims spaces, removes the thousands separator ("1,689" -> 1689),
// turns NA / N/A / "-" / empty into null. Anything unparseable becomes null (never an error).
(x as any) as nullable number =>
let
    t       = if x = null then null else Text.Trim(Text.From(x)),
    isBlank = t = null or t = "" or Text.Upper(t) = "NA" or Text.Upper(t) = "N/A" or t = "-",
    cleaned = if isBlank then null else Text.Replace(t, ",", ""),
    result  = if cleaned = null then null else try Number.From(cleaned, "en-US") otherwise null
in
    result
