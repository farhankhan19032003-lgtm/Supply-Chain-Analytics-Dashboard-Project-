# Resume & Interview Guide

## 1. Resume entry (numbers are from this project's outputs)

**Supply Chain Analytics Platform** | SQL · Tableau · Excel · Power Query · *(simulated nationwide distribution dataset)*

* Built a Tableau dashboard suite tracking inventory and demand across **12 warehouses, 120 SKUs and 104 weeks (150K weekly records)**, with rule-based alerts that flag stock deficits and delayed purchase orders (latest week: **398 deficit lines, 182 critical; 71 overdue POs worth ₹2.4 Cr**).
* Automated extraction, cleaning and merging of **5 regional extracts and 3 master-data sheets (~75K rows)** in Excel Power Query - standardising 5 date formats and delimiters, repairing missing/negative values, removing duplicates, and logging every fix - replacing manual copy-paste preparation with a one-click refresh.
* Wrote **8 MySQL stored procedures** (window functions, temp tables, derived-table staging) for root-cause analysis of **₹39.6 Cr in lost sales** (38.6% supplier delay, 31.7% reorder-point gaps) and asset waste; found **48% of stock held at two DCs for 25% of demand**, **₹7.1 Cr above target cover** and **~30 surplus assets (₹2.45 Cr idle cost)**; recommended 236 stock transfers worth ≈₹44.7 lakh net benefit.

**Rules for using these bullets honestly**
* Keep "(simulated dataset)" in the heading, or say it in the first line of the project description. Interviewers ask.
* Do not turn "reducing manual preparation time" into a percentage unless you time it yourself (e.g. "manual: 45 min per refresh, Power Query: < 1 min"). Measure it once and quote *your* number.
* Only claim "Tableau" after you have built the dashboards from `tableau/TABLEAU_BUILD_GUIDE.md`, and "Power Query" after you have run the M queries in Excel; these two pieces are provided as a kit, not as finished files.
* Only claim MySQL after you have run the SQL files on a real MySQL 8 server (30 minutes). Mention which output you matched (`alert_summary.csv`).

**Shorter 2-line version** (for a crowded resume):
* Built an end-to-end supply-chain analytics project (MySQL, Power Query, Tableau, Excel) on a simulated 12-warehouse Indian distribution network: automated data prep, 8 stored procedures for stock-out root cause (₹39.6 Cr lost sales traced to supplier delay and reorder-point gaps), and alerting for stock deficits and delayed POs.

## 2. 30-second pitch
"I built a supply-chain analytics project on a simulated network of 12 Indian warehouses. Raw regional files come in messy, so I clean and merge them with Power Query. In MySQL I wrote stored procedures that raise stock-deficit and PO-delay alerts and trace every stock-out to a root cause. The surprise was that the network wasn't short of stock - it was in the wrong places: two warehouses held almost half the inventory for a quarter of the demand, while two others lost 11–12% of demand. Tableau dashboards and alert rules make that visible, and I produced a transfer plan to rebalance it."

## 3. Likely interview questions (with answer outlines)

1. **Why simulated data?** Real warehouse-level logs are proprietary. I modelled the mechanics (reorder policy, supplier variability, seasonality) so I could test the full pipeline, and I planted known problems to prove my SQL recovers them. I label it simulated everywhere; the approach transfers to a real dataset (see `USING_REAL_DATA.md`).
2. **How do you define a stock-deficit alert?** Weeks of cover = closing stock ÷ 4-week average demand; STOCKOUT at zero, CRITICAL < 0.5 weeks, LOW < 1.5, thresholds in a config table so the business can change them without code. I then add inbound-PO risk: no PO, PO overdue, or stock runs out before the PO is due.
3. **Walk me through the root-cause logic.** Each stock-out week gets one primary cause by precedence: reorder-point gap (structural) → supplier delay (a PO still outstanding past its promise) → short-shipment → demand spike (> 1.5× prior 8-week average) → variability. I also report factor overlap because causes co-occur.
4. **Why that precedence?** Structural planning errors cause repeat events; supplier events are episodic. It's a documented rule - changing the order changes shares, which I'd flag when presenting.
5. **Which window functions did you use and why?** `AVG() OVER (ROWS BETWEEN 3 PRECEDING…)` for rolling demand, `ROW_NUMBER()` to pick the nearest open PO and to match each deficit warehouse to one donor, `SUM() OVER (PARTITION BY donor)` to cap transfers at the donor's surplus.
6. **How did you validate the SQL?** I recomputed headline numbers independently in pandas (23 checks: fill rate, alert counts, RCA flags incl. a 1,500-event brute-force check, transfer caps, idle cost). *(Be honest that you then ran it on MySQL, if you did.)*
7. **Why stored procedures rather than views?** Parameters (as-of date, window), multi-result outputs, temp tables for multi-step logic, and a procedure that writes `alert_log` for scheduling.
8. **Explain the rebalancing method and its weakness.** Surplus = stock above 4 weeks' cover at donors with > 8 weeks; need = top-up to 3 weeks at deficit sites; each receiver picks the nearest-region donor with the biggest surplus; requests are pro-rated so donors aren't over-drawn. Weakness: it doesn't net the receiver's existing inbound POs, uses flat freight rates, and is one-cycle.
9. **What messiness did Power Query fix?** Preamble rows, 5 date formats (explicit formats avoid day/month ambiguity), text numbers with commas, `NA`, trailing spaces, duplicates, blank closing stock rebuilt from opening + receipts − sold, warehouse names vs codes via a two-key lookup. Every repair is flagged and counted in a DQ log.
10. **How would you deploy the alerts?** Schedule `sp_generate_alerts` weekly (MySQL event or cron), connect Tableau live to `alert_log`, and use Tableau data-driven alerts / subscriptions on Cloud or Server.
11. **What did you find that surprised you?** Overstock and stock-outs coexisting - two DCs with ~7 weeks of cover and 99.9% fill while two others sat at 88-89% fill. The fix is parameters and transfers, not more total inventory.
12. **What would you do with more time / real data?** Replace the trailing-average forecast with a seasonal model, net inbound POs in the transfer logic, add service-level-based safety stock, and validate on real demand (M5) and shipment data (USAID).
13. **What are the limitations?** Simulated data with strong planted effects; indicative transfer benefits; carrying-cost 22% is an assumption; root-cause precedence is a rule, not a causal model.

## 4. Portfolio checklist
* [ ] Run SQL on MySQL 8 and match `alert_summary.csv` (398 / 71 / 2 alerts).
* [ ] Run Power Query in Excel and match `expected_results.csv`.
* [ ] Build the four Tableau dashboards; publish to Tableau Public; screenshot your alert setup.
* [ ] Put the project on GitHub with the README (this folder is ready); keep the "simulated" note visible.
* [ ] Time your manual-vs-Power-Query refresh and quote your real number.
