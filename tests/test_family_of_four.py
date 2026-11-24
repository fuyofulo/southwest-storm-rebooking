"""Demo: a family of four (two adults, two children) where the only valid flight has
three seats together. Offline (stub model). To see it printed:
    pytest -s tests/test_family_of_four.py
To run the same scenario through the real model:
    python -m scripts.demo_family
"""
from app.ai import AIPicker
from app.db import InMemoryRepo
from app.service import RebookingService
from scripts.demo_family import REQUEST_DATE, family_scenario, proof_lines, run
from tests.fakes import make_flight


def stub_model(system: str, user: str) -> str:
    # Stands in for the OpenRouter call. The service still validates this reply
    # and re-checks the pick against every rule.
    return '{"option_id": "OPT-1", "reason": "Only valid flight tonight; both children sit beside Adult 1, Adult 2 sits elsewhere on the same plane."}'


def test_family_of_four_with_three_seats_together():
    s = run(AIPicker(stub_model, "stub-model (test)"))

    assert s["status"] == "suggested"
    assert s["suggestion"]["kind"] == "split"
    assert s["family_must_agree"] is True
    assert "family's agreement" in s["message"]
    [flight] = s["suggestion"]["flights"]
    assert flight["flight_no"] == "WN2103"
    assert sorted(flight["seated_together"]) == ["Adult 1 (M. Rivera)", "Child 1", "Child 2"]
    assert flight["seated_apart"] == ["Adult 2"]
    assert s["documentation_lines"] == ["WN2103: STORM WAIVER DEN NOV26 BKG-DEMO4"]
    assert s["fare"]["result"] == "no fare difference"
    assert all(c["passed"] for c in s["checklist"])
    assert len(proof_lines(s)) == 3  # Child 1, Child 2 with Adult 1; Adult 2 apart (raises if a child is alone)


def test_family_of_four_if_the_flight_had_only_three_seats_in_total():
    # Same family, but the only valid flight has exactly 3 open seats: no safe way to fly all four.
    family, flights = family_scenario()
    flights[0] = make_flight("2026-11-18T18:40", flight_no="WN2103", open_seats_total=3, open_seats_adjacent_max=3)
    s = RebookingService(InMemoryRepo([family], flights)).suggest("BKG-DEMO4", REQUEST_DATE, use_ai=False)
    assert s["status"] == "no_suggestion" and s["flagged_for_agent"]
    assert s["suggestion"] is None
