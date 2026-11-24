# Rebooking Spec: Denver Storm Rebooking Helper

The rebooking helper suggests one valid new itinerary for each booking cancelled by the Denver snowstorm (15–18 Nov 2026). The contact center agent reviews it and confirms it. The helper never books anything on its own.

**Sources**
- *Storm Travel Waiver Fare Rules Bulletin (Denver, November 2026)*: the fare and waiver rules. Clause numbers below (§x.x) refer to it.
- *Agent minutes readout*: where agent time goes. The three slowest steps are finding open flights (5.4 min), reseating the party (7.1 min for groups of 3+) and checking waiver rules (2.6 min, or 4.6 when the booking isn't covered). This spec targets those three.

**Data**
- `cancelled_bookings_denver_storm.csv`: `waiver_eligible`, `fare_class`, `fare_paid_usd`, `earliest_acceptable_departure`, plus origin, destination and passengers.
- `flight_seat_availability.csv`: `flight_status`, `departure_datetime`, `fare_class_open`, plus route and open seats.

---

## 1. Routing checks (run before any search)

Run these checks in order. The first one that fails decides where the booking goes.

| # | Check | If it fails |
|---|---|---|
| R1 | The request is made on or before 23 Nov 2026 (§2.5) | Send to Revenue Management. No suggestion. |
| R2 | The customer wants the same origin and destination pair (§2.2) | An alternate airport goes to Revenue Management. No suggestion. |
| R3 | The customer accepts travel departing between 18 and 23 Nov 2026 (§2.1) | Send to Revenue Management. No suggestion. |
| R4 | Read `waiver_eligible` as given. Never re-assess it (§1.3, §1.4). | `true` → waiver path (§3). `false` → non-covered path (§4). **Both paths get a suggestion.** |

A `waiver_eligible = false` booking is **not** skipped. It stays with the agent and is handled under its original fare class rules (§4.1).

## 2. Valid flight filter (every flight in a suggestion must pass)

A flight can be used only if all of these hold:

1. Same origin and destination as the original booking (§2.2).
2. `flight_status` is `scheduled` or `delayed`, never `cancelled` (§2.3).
3. `departure_datetime` falls between 18 and 23 Nov 2026 inclusive (§2.1).
4. `departure_datetime` is at or after the booking's `earliest_acceptable_departure`. Never offer an earlier flight, even if it has seats (§2.4).
5. It has enough real open seats for the people placed on it.
6. For a connecting itinerary, each leg arrives in time to make the next one.

`fare_class_open` does **not** need to match the original `fare_class` (§3.3).

If no flight passes, the helper makes no suggestion and says why. It never relaxes a rule to find one.

## 3. Choosing the suggestion (party seating)

The order is: together first, a safe split second, and the family has the final say.

1. **Together:** the earliest valid flight with enough seats for the whole party.
2. **Safe split:** only if no valid flight in the window fits the whole party. Spread the party across valid flights so that:
   - **every child travels with at least one adult**. A child is never placed on a flight alone.
   - the number of flights used is as small as possible.
   - every flight used passes Section 2 (§3.5).
3. If there's no way to split without leaving a child alone, make no suggestion and flag the booking for the agent.

A split is only a suggestion. **The agent must get the family's agreement before confirming it.** If the family says no, the agent can look at the next "together" option (for example, a later flight with enough seats) or escalate.

## 4. Fare treatment shown with the suggestion

**Waiver-eligible bookings (§3):**
- No fare difference in either direction. Nothing is collected and nothing is refunded (§3.1).
- `fare_paid_usd` carries over unchanged (§3.2). The customer keeps the benefits of their original fare class (§3.3).
- No change fees or same-day change charges (§3.4).
- A split party gets the same treatment for every member, with no penalty for the split (§3.5).

**Non-covered bookings (`waiver_eligible = false`, §4):**
- The original fare class's change rules apply (§4.1). Every fare class allows a change.
- If the open fare on the new flight is higher, the helper shows the difference so the agent can quote and collect it. Refunds of unused value follow standard fare rules and are not calculated by the helper.
- Loyalty tier does not change any of this (§4.2).
- Flights must still pass clauses 2.2–2.4. Anything outside those limits goes to Revenue Management (§4.3).

## 5. What the agent sees and does

For each booking in the queue, the agent sees:
- the suggested flight or flights and how the party is seated
- which path the booking is on (waiver or non-covered) and the fare result: "no fare difference" or "collect $X"
- a checklist showing that every rule above passed
- for a split: a reminder to get the family's agreement first

**On confirm:**
1. Check again that the seats are still open. If they aren't, don't confirm. Refresh the suggestion.
2. Waiver path: record `STORM WAIVER DEN NOV26` plus the original confirmation number. For a split, record it on **each** rebooked flight (§3.6).
3. Non-covered path: do **not** record that line (§4.4).
4. Split party: each new booking's note links to the other booking numbers, so the gate can find the rest of the family.

## 6. Open questions for the customer

- Which field says whether a passenger is a child? The adult-and-child rule depends on it.
- Which field holds the open fare price on a new flight? The non-covered fare difference needs it.
- What should "earliest" mean when two valid flights are close: earliest departure or earliest arrival at the final destination?
