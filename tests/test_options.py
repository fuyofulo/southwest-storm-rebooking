"""Section 3: together first, a safe split second, never a child without an adult."""
from dataclasses import replace

from app.options import build_options
from app.party import derive_party
from app.rules import all_passed, check_option
from tests.fakes import make_booking, make_flight, make_party


def no_child_without_adult(option):
    for seg in option.segments:
        assert not any(p.is_minor for p in seg.apart), "a child is seated apart"
        if any(p.is_minor for p in seg.together):
            assert any(p.is_adult for p in seg.together), "a child has no adult beside them"


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


def test_safe_split_keeps_children_in_the_block_with_an_adult():
    b = make_booking(party_size=4)
    f = make_flight(open_seats_total=6, open_seats_adjacent_max=3)
    result = build_options(b, make_party(adults=2, children=2), [f])
    opt = result.options[0]
    assert opt.kind == "split" and opt.family_must_agree
    no_child_without_adult(opt)
    assert len(opt.segments[0].apart) == 1


def test_split_uses_fewest_flights():
    # 3 minors + 2 adults; no flight can take 3 minors + an adult in one block, so 2 flights.
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
        no_child_without_adult(opt)
        assert sum(len(s.people) for s in opt.segments) == 5


def test_no_suggestion_when_a_split_would_leave_a_child_alone():
    # 1 adult + 1 child, flights with single seats only: they can never sit together.
    b = make_booking(party_size=2)
    flights = [make_flight(open_seats_total=1, open_seats_adjacent_max=1), make_flight("2026-11-18T12:00", open_seats_total=1, open_seats_adjacent_max=1)]
    result = build_options(b, make_party(adults=1, children=1), flights)
    assert result.options == ()
    assert "without an adult" in result.reason


def test_unknown_make_up_is_never_split_and_is_flagged():
    b = make_booking(party_size=4, agent_note="Family of 4 must sit together.")
    party = derive_party(b)
    result = build_options(b, party, [make_flight(open_seats_total=10, open_seats_adjacent_max=3)])
    assert result.options == ()
    assert "flagged for agent" in result.reason and "make-up" in result.reason


def test_unknown_make_up_still_gets_together_options():
    b = make_booking(party_size=4, agent_note="Family of 4 must sit together.")
    result = build_options(b, derive_party(b), [make_flight(open_seats_adjacent_max=4)])
    assert result.options[0].kind == "together"


def test_not_enough_seats_anywhere():
    b = make_booking(party_size=6)
    flights = [make_flight(open_seats_total=2, open_seats_adjacent_max=2)]
    result = build_options(b, make_party(adults=6), flights)
    assert result.options == () and "only 2 open seats" in result.reason


def test_no_valid_flight_says_why():
    b = make_booking()
    result = build_options(b, make_party(), [make_flight(flight_status="cancelled")])
    assert result.options == () and "1 cancelled" in result.reason


def test_recheck_rejects_a_tampered_option():
    b = make_booking(party_size=4)
    party = make_party(adults=2, children=2)
    f = make_flight(open_seats_total=6, open_seats_adjacent_max=3)
    result = build_options(b, party, [f])
    opt = result.options[0]
    seg = opt.segments[0]
    child = next(p for p in seg.together if p.is_minor)
    adult = seg.apart[0]
    # swap a child out of the block
    bad_seg = replace(seg, together=tuple(adult if p == child else p for p in seg.together), apart=(child,))
    bad = replace(opt, segments=(bad_seg,))
    flights_by_no = {f.flight_no: f}
    assert all_passed(check_option(b, party, opt, flights_by_no, False, 1))
    assert not all_passed(check_option(b, party, bad, flights_by_no, False, 1))


def test_recheck_rejects_a_flight_not_in_the_table():
    b = make_booking()
    party = make_party()
    result = build_options(b, party, [make_flight()])
    assert not all_passed(check_option(b, party, result.options[0], {}, True, 1))
