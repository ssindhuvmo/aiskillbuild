import pytest

from core.agents.intake.validation import (
    missing_fields,
    validate_ai_experience,
    validate_domain,
    validate_hours,
    validate_role,
)


@pytest.mark.parametrize("v,expected", [(1, 1), (40, 40), ("8", 8), ("8 hours", 8), (12.0, 12)])
def test_hours_valid(v, expected):
    assert validate_hours(v) == (expected, None)


@pytest.mark.parametrize("v", [0, 41, -3, "lots", None, 7.5, True, ""])
def test_hours_invalid(v):
    val, err = validate_hours(v)
    assert val is None and err


def test_role():
    assert validate_role("  Backend   Engineer ") == ("Backend Engineer", None)
    for bad in ["", "engineer", "it", None, "ab"]:
        assert validate_role(bad)[0] is None


def test_ai_experience_options():
    assert validate_ai_experience(" beginner ") == ("Beginner", None)
    assert validate_ai_experience("EXPERIENCED") == ("Experienced", None)
    assert validate_ai_experience("none") == ("None", None)
    for bad in ["Advanced", "expert", "", None]:
        assert validate_ai_experience(bad)[0] is None


def test_domain():
    assert validate_domain("fintech") == ("FinTech", None)
    assert validate_domain("Other")[0] is None  # needs free text
    assert validate_domain("Logistics") == ("Logistics", None)
    assert validate_domain("")[0] is None


def test_missing_fields():
    assert "hours_per_week" in missing_fields({"current_role": "x"})
    full = dict(current_role="a", target_role="b", ai_experience="None", domain="d", hours_per_week=5)
    assert missing_fields(full) == []
