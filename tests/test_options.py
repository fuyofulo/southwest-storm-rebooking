"""Section 3: together first, then a split party on different flights, never a child without an adult."""
from dataclasses import replace

from app.options import build_options
from app.party import derive_party
from app.rules import all_passed, check_option
from tests.fakes import make_booking, make_flight, make_party


def sound_split(option, party):
    """Every group side by side on its own flight, within its seats; every child with an adult; lead first."""
    nos = [seg.flight.flight_no for seg in option.segments]
    assert len(nos) >= 2 and len(set(nos)) == len(nos), "split must use different flights"
    for seg in option.segments:
        assert len(seg.together) <= seg.flight.open_seats_adjacent_max <= seg.flight.open_seats_total
        if any(p.is_minor for p in seg.together):
            assert any(p.is_adult for p in seg.together), "a child has no adult beside them"
    assert party.passengers[0] in option.segments[0].together, "lead passenger's group comes first"
    assert sum(len(s.together) for s in option.segments) == party.size


def test_together_is_the_earliest_flight_with_an_adjacent_block_for_everyone():
    b = make_booking(party_size=3)
    small = make_flight("2026-11-18T08:00", open_seats_total=9, open_seats_adjacent_max=2)
    later = make_flight("2026-11-18T14:00", open_seats_adjacent_max=3)
    earliest_fit = make_flight("2026-11-18T10:00", open_seats_adjacent_max=3)
    result = build_options(b, make_party(adults=3), [later, small, earliest_fit])
    assert [o.kind for o in result.options] == ["together", "together"]
    assert result.options[0].segments[0].flight == earliest_fit
    assert result.together_available


def test_no_split_offered_when_a_together_option_exists():
    b = make_booking(party_size=4)
    flights = [make_flight("2026-11-18T08:00", open_seats_adjacent_max=3), make_flight("2026-11-20T08:00", open_seats_adjacent_max=4)]
    result = build_options(b, make_party(adults=2, children=2), flights)
    assert all(o.kind == "together" for o in result.options)


def test_party_of_four_best_block_three_puts_lead_plus_two_together_and_the_fourth_on_another_flight():
    b = make_booking(party_size=4)
    party = make_party(adults=4)
    three = make_flight("2026-11-19T10:00", open_seats_total=8, open_seats_adjacent_max=3)
    other = make_flight("2026-11-19T15:00", open_seats_total=2, open_seats_adjacent_max=2)
    result = build_options(b, party, [three, other])
    opt = result.options[0]
    assert opt.kind == "split" and opt.family_must_agree
    sound_split(opt, party)
    assert [s.flight for s in opt.segments] == [three, other]
    assert [len(s.together) for s in opt.segments] == [3, 1]


def test_never_all_four_on_the_three_seat_flight():
    # Plenty of open seats on the 3-block flight, but no second valid flight: no option at all.
    b = make_booking(party_size=4)
    result = build_options(b, make_party(adults=4), [make_flight(open_seats_total=9, open_seats_adjacent_max=3)])
    assert result.options == () and result.reason.startswith("No flight met the rules")


def test_children_stay_with_the_lead_adult_and_only_an_adult_travels_alone():
    b = make_booking(party_size=4)
    party = make_party(adults=2, children=2)
    flights = [make_flight("2026-11-18T10:00", open_seats_adjacent_max=3), make_flight("2026-11-18T12:00", open_seats_adjacent_max=1)]
    opt = build_options(b, party, flights).options[0]
    sound_split(opt, party)
    assert [p.label for p in opt.segments[1].together] == ["Adult 2"]


def test_split_uses_fewest_flights():
    # 2 adults + 2 children + 1 infant, blocks of 3 and 2: two flights, each child group with an adult.
    b = make_booking(party_size=5)
    party = make_party(adults=2, children=2, infants=1)
    flights = [
        make_flight("2026-11-18T08:00", open_seats_total=3, open_seats_adjacent_max=3),
        make_flight("2026-11-18T09:00", open_seats_total=2, open_seats_adjacent_max=2),
        make_flight("2026-11-18T10:00", open_seats_total=2, open_seats_adjacent_max=2),
    ]
    result = build_options(b, party, flights)
    assert result.min_flights == 2
    for opt in result.options:
        assert len(opt.segments) == 2
        sound_split(opt, party)


def test_no_option_when_a_split_would_leave_a_child_alone():
    # 1 adult + 1 child, flights with single seats only: they can never sit together.
    b = make_booking(party_size=2)
    flights = [make_flight(open_seats_total=1, open_seats_adjacent_max=1), make_flight("2026-11-18T12:00", open_seats_total=1, open_seats_adjacent_max=1)]
    result = build_options(b, make_party(adults=1, children=1), flights)
    assert result.options == ()
    assert "child next to an adult" in result.reason


def test_unknown_make_up_is_split_with_an_agent_check_that_the_separate_group_is_adults():
    b = make_booking(party_size=4, agent_note="Family of 4 must sit together.")
    party = derive_party(b)
    flights = [make_flight("2026-11-18T10:00", open_seats_total=10, open_seats_adjacent_max=3), make_flight("2026-11-18T12:00")]
    flights[1] = replace(flights[1], open_seats_adjacent_max=1, open_seats_total=1)
    opt = build_options(b, party, flights).options[0]
    sound_split(opt, party)
    assert opt.agent_checks == (f"Make-up not stated: confirm Passenger 4 on {flights[1].flight_no} is an adult (no child may fly without an adult).",)


def test_unknown_make_up_still_gets_together_options_first():
    b = make_booking(party_size=4, agent_note="Family of 4 must sit together.")
    result = build_options(b, derive_party(b), [make_flight(open_seats_adjacent_max=4)])
    assert result.options[0].kind == "together" and result.options[0].agent_checks == ()


def test_not_enough_seats_anywhere():
    b = make_booking(party_size=6)
    flights = [make_flight(open_seats_total=2, open_seats_adjacent_max=2)]
    result = build_options(b, make_party(adults=6), flights)
    assert result.options == () and "only 2 open seats" in result.reason


def test_no_valid_flight_says_why():
    b = make_booking()
    result = build_options(b, make_party(), [make_flight(flight_status="cancelled")])
    assert result.options == () and "1 cancelled" in result.reason


def test_recheck_rejects_a_tampered_split():
    b = make_booking(party_size=4)
    party = make_party(adults=2, children=2)
    flights = [make_flight("2026-11-18T10:00", open_seats_adjacent_max=3), make_flight("2026-11-18T12:00", open_seats_adjacent_max=1)]
    result = build_options(b, party, flights)
    opt = result.options[0]
    first, second = opt.segments
    child = next(p for p in first.together if p.is_minor)
    adult = second.together[0]
    swapped = replace(opt, segments=(  # a child alone on the second flight
        replace(first, together=tuple(adult if p == child else p for p in first.together)),
        replace(second, together=(child,)),
    ))
    all_on_one = replace(opt, segments=(replace(first, together=party.passengers),))  # 4 in a block of 3
    flights_by_no = {f.flight_no: f for f in flights}
    assert all_passed(check_option(b, party, opt, flights_by_no, False, 2))
    assert not all_passed(check_option(b, party, swapped, flights_by_no, False, 2))
    assert not all_passed(check_option(b, party, all_on_one, flights_by_no, False, 2))


def test_recheck_rejects_a_flight_not_in_the_table():
    b = make_booking()
    party = make_party()
    result = build_options(b, party, [make_flight()])
    assert not all_passed(check_option(b, party, result.options[0], {}, True, 1))
