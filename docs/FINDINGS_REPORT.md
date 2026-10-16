# Findings Report - Supply Chain Analytics Platform

**Scope:** 12 regional distribution centres, 120 SKUs in 8 categories, 104 weeks (7-Oct-2024 → 4-Oct-2026),
149,760 weekly stock records, 31,991 purchase orders, 291 warehouse assets.
**Data note:** simulated dataset (see README). The causes below were planted in the simulator; the report
demonstrates that the stored-procedure methodology recovers them. All figures come from
`outputs/sql_results/` and were reconciled by `scripts/04_validate_results.py`.

## Executive summary

1. **The network is stocked in the wrong places.** Bhiwandi and Gurugram hold **48% of network stock value for 25%
   of demand** and almost never stock out (fill 99.9%+). Chennai and Guwahati hold 5.6% of stock for 13.7% of demand and
   lose **11-12% of demand**.
2. **₹39.6 Cr of revenue was lost to stock-outs in 104 weeks**, 51% of it in Chennai and Guwahati.
3. **Two causes explain 70% of lost sales:** supplier delay (38.6%) and reorder points set too low (31.7%).
   Unforecast demand spikes (12.5%), thin safety stock (15.0%) and short-shipments (2.1%) are secondary.
4. **₹7.07 Cr of stock sits above a 4-week cover target**, almost all in Bhiwandi (₹3.21 Cr) and Gurugram (₹2.11 Cr) - about
   **₹1.56 Cr a year in carrying cost** at 22%. A further ₹0.64 Cr is at expiry risk (cover > half the shelf life).
5. **Four suppliers deliver on time only 38-50% of the time** versus 71% network-wide, and delivery reliability drops in
   monsoon months.
6. **Asset waste follows the same misalignment.** Pune and Jaipur hold ~30 more assets than their workload needs
   (₹2.45 Cr idle cost over 24 months) while Chennai's fleet runs at 93% utilisation; Kolkata and Lucknow fleets are ageing
   (8-9% downtime vs 4-5% at most sites; Kolkata logged 1,032 breakdowns vs 179-782 at every other site).
7. **Today's exposure (week ending 4-Oct-2026):** 398 SKU-warehouse lines are in deficit (124 stocked out, 58 critical, 216 low);
   they carry ₹53 lakh of weekly margin at risk. 71 purchase orders are 3+ days overdue (₹2.44 Cr, 28 critical).

## 1. Where is stock vs where is demand? (Q6, `sp_regional_kpis`)

| Warehouse | Fill rate | Stock-out rate | Avg cover (wks) | Share of stock | Share of demand |
|---|---|---|---|---|---|
| Bhiwandi | 99.97% | 0.1% | 7.0 | 28.4% | 14.7% |
| Gurugram | 99.94% | 0.2% | 6.7 | 19.4% | 10.4% |
| Chennai | **89.14%** | **21.2%** | 1.6 | 3.0% | 9.7% |
| Guwahati | **87.86%** | **17.1%** | 4.0 | 2.6% | 4.0% |
| Rest of network | 96.8-98.9% | 2.7-7.4% | 2.5-4.4 | - | - |

Reorder-policy audit (Q9): the reorder point actually used, relative to demand over lead time, is **0.71× at Chennai and
0.74× at Guwahati** (under-protected) versus **2.07× at Bhiwandi and 1.97× at Gurugram** (over-protected); every other
warehouse is 1.0-1.2×. Planners in two sites are systematically too lean, in two others too generous.

## 2. Why did stock-outs happen? (`sp_stockout_root_cause`, 9,178 events)

| Primary cause (precedence order) | Events | Lost revenue | Share |
|---|---|---|---|
| 1 Planning-policy gap (reorder point < 75% of need) | 3,171 | ₹12.57 Cr | 31.7% |
| 2 Supplier delay (PO outstanding past promise) | 2,912 | ₹15.31 Cr | 38.6% |
| 3 Supplier short-shipment (< 90% of order received) | 221 | ₹0.84 Cr | 2.1% |
| 4 Unforecast demand spike (> 1.5× prior 8-wk avg) | 769 | ₹4.96 Cr | 12.5% |
| 5 Demand variability / thin safety stock | 2,105 | ₹5.93 Cr | 15.0% |

Causes overlap (a late PO often arrives while the reorder point is also too low): 34.6% of events show a policy gap,
40.2% a late PO, 16.2% a demand spike. The *primary* cause uses a documented precedence (structural → supplier → demand).
In Chennai, policy gaps account for ₹9.4 Cr of its ₹14.4 Cr loss; in Kolkata, supplier delay is ₹2.3 Cr of ₹4.1 Cr.

Seasonality (Q3, Q7): electronics lose **4.0×** and snacks **3.1×** more revenue per SKU-week in Diwali build-up weeks
than in normal weeks; East stock-out rates peak in monsoon (14.7%).

## 3. Pipeline and supplier reliability (`vw_supplier_scorecard`, `sp_pipeline_delay_alerts`)

* Tier-3 suppliers: 46% on time, actual lead time 19.8 days vs 15.2 promised; Tier-1: 83.5% on time.
* The four worst: ConnectPro Gadgets 38%, Kisan Mill Traders 44%, PureSkin Personal Care 48%, SafeShip Packaging 50%.
  They account for 52 of the 71 overdue open POs.
* Of the 71 overdue POs, 53 sit on lines that are already stocked out or critical.
* Of 398 deficit lines, 150 will run dry **before** their inbound PO is due, 92 have an inbound PO that is already overdue, and 36 have no PO open at all.

## 4. Operational waste

**Inventory (`sp_excess_inventory_waste`):** excess (> 8 weeks of cover) is only ₹1.32 Cr, but stock above the 4-week target is
₹7.07 Cr, concentrated in Bhiwandi (41% of its stock) and Gurugram (40%). Expiry-risk stock (cover > 50% of shelf life) is ₹0.64 Cr.

**Assets (`sp_asset_waste_rca`, Oct-24 → Sep-26):**

| Warehouse | Utilisation | Idle | Downtime | Diagnosis |
|---|---|---|---|---|
| Pune | 35.5% | 60.5% | 4.0% | Over-provisioned: +20 assets, ₹1.62 Cr idle cost |
| Jaipur | 40.9% | 54.2% | 4.8% | Over-provisioned: +10 assets, ₹0.83 Cr idle cost |
| Kolkata | 68.4% | 22.9% | **8.8%** | Ageing fleet: 1,032 breakdowns, ₹4.1 Cr maintenance |
| Lucknow | 68.8% | 23.1% | **8.1%** | Ageing fleet |
| Chennai | **93.1%** | 0.5% | 6.4% | Overstretched: ~4 assets short |
Network idle cost ₹5.8 Cr; maintenance ₹27.5 Cr; 6,348 breakdowns.

## 5. Recommendations (what an analyst would put in front of the supply-chain head)

1. **Rebalance now (`sp_regional_rebalance`):** 236 transfer lines, 137k units, ₹2.07 Cr of stock moved from Bhiwandi (₹0.95 Cr) and
   Gurugram (₹0.88 Cr) mainly to Chennai (₹0.64 Cr), Ahmedabad (₹0.41 Cr), Bengaluru (₹0.28 Cr) - ≈₹44.7 lakh indicative net
   benefit (margin protected ₹51.9 lakh less ₹7.2 lakh freight; 19% of lines are same-region). Caveat: receivers' existing inbound POs are not netted off.
2. **Fix the planning parameters:** reset reorder-point multipliers at Chennai and Guwahati upward and at Bhiwandi and
   Gurugram downward; review quarterly with the Q9 audit.
3. **Supplier management:** put the four Tier-3 suppliers on a performance plan; dual-source their SKUs; plan monsoon buffers for East/West lanes.
4. **Festive plan:** pre-build electronics and snacks 3-4 weeks ahead of Diwali; the 6-week trailing forecast is too slow for a ~2× electronics ramp.
5. **Fleet:** redeploy surplus equipment from Pune and Jaipur to Chennai and Guwahati; replace/overhaul the Kolkata and Lucknow fleets.

## Method and limits
* Metrics: fill rate = units sold ÷ units demanded; stock-out rate = share of SKU-weeks with any lost units; weeks of cover = closing stock ÷ 4-week average demand.
* Lost revenue uses selling price; margin figures use price − cost. Carrying cost assumes 22% per year (a stated assumption, configurable in `cfg_thresholds`).
* Root-cause precedence and thresholds are rules of thumb (documented in the procedure header) - change them in SQL if your business differs.
* Transfer benefits are indicative single-cycle estimates; freight rates are assumptions.
* Simulated data: planted effects are strong by design, so magnitudes are larger than a typical real network would show.
