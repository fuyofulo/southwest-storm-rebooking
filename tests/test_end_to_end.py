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
    assert summary["suggested"] + summary["no_suggestion_flagged_for_agent"] + summary["revenue_management"] == 140
    assert summary["all_suggestions_pass_every_check"]
    assert summary["child_without_adult_problems"] == []
    # every non-covered booking is handled, not skipped
    assert summary["suggested_non_covered_path"] == 6
    # every split is a suggestion the family must agree to
    assert summary["family_must_agree"] == summary["split"]


def test_real_data_after_the_request_deadline_all_go_to_revenue_management(service):
    results = service.suggest_all(date(2026, 11, 24), use_ai=False)
    assert summarize(results)["revenue_management"] == 140
    assert all(s["suggestion"] is None for s in results)
