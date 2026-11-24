"""End-to-end over the real CSVs (code choice, no network). Run with -s to see the summary."""
from datetime import date

import pytest

from app.config import get_settings
from app.db import CsvRepo
from app.service import RebookingService
from app.summary import format_summary, summarize


@pytest.fixture(scope="module")
def service():
    return RebookingService(CsvRepo(get_settings().data_dir), picker=None)


def test_real_data_on_18_nov(service):
    results = service.suggest_all(date(2026, 11, 18), use_ai=False)
    summary = summarize(results)
    print("\nEnd-to-end over the real data, request date 2026-11-18\n" + format_summary(summary))

    assert summary["bookings"] == 140
    assert summary["ready_to_confirm"] + summary["split_party_confirm"] + summary["no_option_found"] == 140
    assert summary["all_suggestions_pass_every_check"]
    assert summary["safety_problems"] == []
    # every non-covered booking is handled, not skipped
    assert summary["suggested_non_covered_path"] == 6
    # every split is on different flights and needs the family's agreement
    for s in results:
        if s["suggestion_status"] == "split_party_confirm":
            assert s["family_must_agree"] and len({f["flight_no"] for f in s["suggestion"]["flights"]}) >= 2


def test_every_party_of_four_whose_best_flight_seats_three_is_split_party_confirm(service):
    # The acceptance case: 3 including the lead on that flight, the 4th on a different valid flight.
    results = service.suggest_all(date(2026, 11, 18), use_ai=False)
    cases = [s for s in results if s["party_size"] == 4 and s["suggestion_status"] == "split_party_confirm"
             and s["suggestion"]["flights"][0]["open_seats_adjacent_max"] == 3]
    assert {s["booking_id"] for s in cases} >= {"BKG-10011", "BKG-10023", "BKG-10066", "BKG-10079", "BKG-10091", "BKG-10103", "BKG-10121"}
    for s in cases:
        first, second = s["suggestion"]["flights"]
        assert first["passengers"] == 3 and first["includes_lead_passenger"] and second["passengers"] == 1
        assert first["flight_no"] != second["flight_no"]


def test_real_data_after_the_request_deadline_all_go_to_revenue_management(service):
    results = service.suggest_all(date(2026, 11, 24), use_ai=False)
    assert summarize(results)["revenue_management"] == 140
    assert all(s["suggestion"] is None and s["suggestion_status"] == "no_option_found" for s in results)
