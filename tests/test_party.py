"""Party make-up: only split when it's stated (decision Q1)."""
from app.models import ADULT, CHILD, LAP_INFANT, UNKNOWN
from app.party import derive_party, party_from_rows, party_to_rows
from tests.fakes import make_booking


def counts(party):
    return {t: party.count(t) for t in (ADULT, CHILD, LAP_INFANT, UNKNOWN)}


def test_child_count_in_note():
    p = derive_party(make_booking(party_size=4, agent_note="Two children in party of 4."))
    assert p.make_up_known
    assert counts(p) == {ADULT: 2, CHILD: 2, LAP_INFANT: 0, UNKNOWN: 0}


def test_flagged_infant_is_one_more_child():
    p = derive_party(make_booking(party_size=5, travels_with_infant=True, agent_note="Two children in party of 5."))
    assert counts(p) == {ADULT: 2, CHILD: 2, LAP_INFANT: 1, UNKNOWN: 0}


def test_lap_infant_note():
    p = derive_party(make_booking(party_size=2, travels_with_infant=True, agent_note="Lap infant on booking."))
    assert p.make_up_known
    assert counts(p) == {ADULT: 1, CHILD: 0, LAP_INFANT: 1, UNKNOWN: 0}


def test_no_hint_means_all_adults():
    p = derive_party(make_booking(party_size=4, agent_note="Party of 4 must sit together."))
    assert p.make_up_known
    assert counts(p)[ADULT] == 4


def test_family_without_count_is_unknown():
    p = derive_party(make_booking(party_size=4, agent_note="Family of 4 must sit together."))
    assert not p.make_up_known
    assert counts(p)[UNKNOWN] == 4


def test_infant_flag_without_count_is_unknown():
    p = derive_party(make_booking(party_size=4, travels_with_infant=True, agent_note="Party of 4 must sit together."))
    assert not p.make_up_known


def test_party_size_mismatch_is_unknown():
    p = derive_party(make_booking(party_size=3, agent_note="Two children in party of 4."))
    assert not p.make_up_known


def test_no_adult_left_is_unknown():
    p = derive_party(make_booking(party_size=2, agent_note="Two children in party."))
    assert not p.make_up_known


def test_every_person_gets_a_seat_including_lap_infants():
    p = derive_party(make_booking(party_size=3, travels_with_infant=True, agent_note="Lap infant on booking."))
    assert p.size == 3  # the infant is one of the 3 seats


def test_lead_passenger_is_adult_1():
    p = derive_party(make_booking(party_size=2, lead_passenger_name="A. Nkemelu"))
    assert p.passengers[0].label == "Adult 1 (A. Nkemelu)"


def test_round_trip_through_passenger_rows():
    p = derive_party(make_booking(party_size=4, agent_note="Two children in party of 4."))
    assert party_from_rows(party_to_rows("BKG-TEST", p)) == p
