# Rebooking Spec: Denver Storm Rebooking Helper

The rebooking helper suggests one valid new itinerary for each booking cancelled by the Denver snowstorm (15–18 Nov 2026). The contact center agent reviews it and confirms it. The helper never books anything on its own.

**Sources**
- *Storm Travel Waiver Fare Rules Bulletin (Denver, November 2026)*: the fare and waiver rules. Clause numbers below (§x.x) refer to it.
- *Agent minutes readout*: where agent time goes. The three slowest steps are finding open flights (5.4 min), reseating the party (7.1 min for groups of 3+) and checking waiver rules (2.6 min, or 4.6 when the booking isn't covered). This spec targets those three.
- *Prototype decisions (24 Nov 2026)*: where the bulletin and the data were silent, the customer decided. These are marked **Decision** below.

**Data**
- `cancelled_bookings_denver_storm.csv`: `waiver_eligible`, `fare_class`, `fare_paid_usd` (the whole party's total), `earliest_acceptable_departure`, `party_size`, `travels_with_infant`, `agent_note`, plus origin and destination. One row per booking; there is no per-passenger row.
- `flight_seat_availability.csv`: `flight_status`, `departure_datetime`, `fare_class_open`, `base_fare_usd` (per seat), `open_seats_total`, `open_seats_adjacent_max` (the largest block of side-by-side open seats), plus route. There is no seat map.
- The last row of the flight file (WN1154) is cut off. It is skipped with a warning, never guessed.

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

How each check reads the data:
- **R1, Decision:** the data has no request date. The request date is the `request_date` query parameter, else the `REQUEST_DATE` setting, else today.
- **R2:** the data has no field for a requested airport, so the booking's own pair is the request.
- **R3:** passes when `earliest_acceptable_departure` falls on or before 23 Nov 2026.

## 2. Valid flight filter (every flight in a suggestion must pass)

A flight can be used only if all of these hold:

1. Same origin and destination as the original booking (§2.2).
2. `flight_status` is `scheduled` or `delayed`, never `cancelled` (§2.3).
3. `departure_datetime` falls between 18 and 23 Nov 2026 inclusive (§2.1).
4. `departure_datetime` is at or after the booking's `earliest_acceptable_departure`. Never offer an earlier flight, even if it has seats (§2.4).
5. It has enough real open seats for the people placed on it. **Decision:** every person in `party_size` needs a seat, lap infants included, so a party is never put on a flight that is short a seat. People seated together also need an adjacent block that big (`open_seats_adjacent_max`).
6. For a connecting itinerary, each leg arrives in time to make the next one. **Decision:** this version suggests direct flights only, so there is no connection to check. Every booked route has direct flights in the data.

`fare_class_open` does **not** need to match the original `fare_class` (§3.3).

If no flight passes, the helper makes no suggestion and says why. It never relaxes a rule to find one.

## 3. Choosing the suggestion (party seating)

The order is: together first, a safe split second, and the family has the final say.

**Who is a child (Decision).** The data has no child field. A party's make-up counts as *stated* only when:
- the agent note gives a child count ("Two children in party of 4"). If `travels_with_infant` is also true, the infant is one more child; or
- the agent note says "Lap infant" (one lap infant, the rest adults); or
- there is no child, infant or family hint at all (everyone is an adult).

Any other hint ("Family of 4", or `travels_with_infant` with no count) means the make-up is **unknown**. Lap infants count as children for the adult rule.

1. **Together** (`suggestion_status` = `ready_to_confirm`): the earliest valid flight (by departure time) whose adjacent block fits the whole party: `open_seats_adjacent_max` ≥ party size.
2. **Split party** (`split_party_confirm`), only if no valid flight seats the whole party together. **Decision (acceptance criteria, Dec 2026 handoff):** the party is split into groups, and **each group sits side by side on its own, different flight**. Nobody is seated apart on the same plane, and no flight gets more people than its `open_seats_total`.
   - The lead passenger's group is as large as the best flight allows. Example: a party of 4 whose best flight has `open_seats_adjacent_max` = 3. Three passengers including the lead sit together on that flight; the fourth goes on a different valid flight. Putting all four on the three-seat flight is never allowed.
   - **Every child travels with at least one adult.** Every child and lap infant is in a group with an adult.
   - The number of flights used is as small as possible. Among those, the plan where the whole party has left soonest comes first, then the plan whose flights are closest together in time.
   - Every flight used passes Section 2: the same departure, status, seat and waiver-window rules (§3.5).
   - **Decision:** a party whose make-up is unknown can be split too, but the agent must confirm with the family that everyone in a group without the lead passenger is an adult. The page shows this as a check next to Confirm.
3. If there is no valid flight, or no way to split as above, there is no suggestion (`no_option_found`). The booking still opens and says plainly why no flight met the rules.

Example: a family of four (two adults, two children) whose best flight has 5 open seats, 3 of them side by side, and a later flight with 2 open seats. Both children and the lead adult take the block of 3; the other adult takes the later flight.

A split is only a suggestion. **The agent must get the family's agreement before confirming it.** If the family says no, the agent escalates. A split is never confirmed automatically.

**How the AI model fits in.** Code builds up to five valid options, best first (together options if any exist, otherwise splits). The model, called live through OpenRouter, picks one by its ID and writes a one-line reason for the agent. It keeps the first option unless the booking context (agent note, onward connection, weather risk, wheelchair, bags) gives a concrete reason. Code re-checks the pick against every rule in this spec. If the pick is malformed, not in the list, or fails a check, code uses its own first option, says so on the page, and logs why. The model never adds a flight or changes the seating.

## 4. Fare treatment shown with the suggestion

**Waiver-eligible bookings (§3):**
- No fare difference in either direction. Nothing is collected and nothing is refunded (§3.1).
- `fare_paid_usd` carries over unchanged (§3.2). The customer keeps the benefits of their original fare class (§3.3).
- No change fees or same-day change charges (§3.4).
- A split party gets the same treatment for every member, with no penalty for the split (§3.5).

**Non-covered bookings (`waiver_eligible = false`, §4):**
- The original fare class's change rules apply (§4.1). Every fare class allows a change.
- If the open fare on the new flight is higher, the helper shows the difference so the agent can quote and collect it. Refunds of unused value follow standard fare rules and are not calculated by the helper.
  - The open fare is `base_fare_usd`, per seat. The new fare is `base_fare_usd` × the people seated on each new flight, added up. The amount to collect is the new fare minus `fare_paid_usd` (the party total), if that is positive.
- Loyalty tier does not change any of this (§4.2).
- Flights must still pass clauses 2.2–2.4. Anything outside those limits goes to Revenue Management (§4.3).

## 5. What the agent sees and does

The agent works one list of every booking still waiting, newest `cancellation_time` first, on one screen. For each booking the agent sees:
- the `suggestion_status`: `ready_to_confirm`, `split_party_confirm` or `no_option_found`
- the suggested flight or flights: `flight_no`, `departure_datetime`, `open_seats_total`, `open_seats_adjacent_max`, and who sits on each (the lead passenger named)
- `waiver_eligible`, which path the booking is on (waiver or non-covered) and the fare result: "no fare difference" or "collect $X"
- a checklist showing that every rule above passed
- for a split: a reminder to get the family's agreement first
- the model's one-line reason, or the code's reason if it fell back
- for information only, not enforced by code: `onward_connection_flight_no`, each flight's `weather_risk_flag`, and the agent note

**Confirm records the agent's decision** (who, when, which suggestion) against the booking, and the booking leaves the waiting list. **It does not book a flight**; the booking is made in Southwest's own systems. A `no_option_found` booking can be confirmed too, once the agent has handled it by hand or escalated it.

**On confirm:**
1. Check again that the seats are still open. If they aren't, don't confirm. Refresh the suggestion.
2. Waiver path: record `STORM WAIVER DEN NOV26` plus the original confirmation number (`booking_id`). For a split, record it on **each** rebooked flight (§3.6).
3. Non-covered path: do **not** record that line (§4.4).
4. Split party: each new booking's note links to the other booking numbers, so the gate can find the rest of the family.

## 6. Open questions for the customer

Still open:
- Which field says whether a passenger is a child? Until there is one, the helper works the make-up out from the agent note and `travels_with_infant` (Section 3). When it is unknown, a split asks the agent to confirm that each group without the lead passenger is adults only.
- Does a lap infant need its own seat, and is the infant counted in `party_size`? Until answered, every person in `party_size` gets a seat (Section 2, rule 5).
- Is there a field for the date the request was made? Until there is, R1 uses the request date given to the helper (Section 1).
- If connecting itineraries are added: what is the minimum connection time?

Answered:
- Which field holds the open fare price on a new flight? `base_fare_usd`, per seat (Section 4).
- What should "earliest" mean? Earliest departure.
