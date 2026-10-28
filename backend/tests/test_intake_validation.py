import pytest

from core.agents.intake.validation import (
    DEFAULT_PREFERENCES,
    ai_level,
    check_combination,
    missing_fields,
    next_step,
    steps,
    validate_capabilities,
    validate_constraints,
    validate_context,
    validate_domain,
    validate_hours,
    validate_preferences,
    validate_role,
    validate_years,
)

ALL_RATED = dict(python="Beginner", data_sql="Beginner", machine_learning="None", ai_llms="None", cloud="None")
FULL = dict(current_role="Data Analyst", target_role="Data Scientist", years_experience=4, domain="Retail",
            hours_per_week=5, capabilities=ALL_RATED)


@pytest.mark.parametrize("v,expected", [(1, 1), (40, 40), ("8", 8), ("8 hours", 8), (12.0, 12)])
def test_hours_valid(v, expected):
    assert validate_hours(v) == (expected, None)


@pytest.mark.parametrize("v", [0, 41, -3, "lots", None, 7.5, True, ""])
def test_hours_invalid(v):
    val, err = validate_hours(v)
    assert val is None and err


def test_years():
    assert validate_years("12 years") == (12, None)
    assert validate_years(0) == (0, None)
    for bad in [-1, 51, 2.5, "many", None, True]:
        assert validate_years(bad)[0] is None


def test_role():
    assert validate_role("  Backend   Engineer ") == ("Backend Engineer", None)
    for bad in ["", "engineer", "it", None, "ab"]:
        assert validate_role(bad)[0] is None


def test_domain():
    assert validate_domain("fintech") == ("FinTech", None)
    assert validate_domain("Other")[0] is None  # needs free text
    assert validate_domain("Logistics") == ("Logistics", None)
    assert validate_domain("")[0] is None


def test_capabilities_are_partial_and_normalized():
    assert validate_capabilities({"python": " intermediate ", "cloud": "NONE"}) == (
        {"python": "Intermediate", "cloud": "None"}, None,
    )
    for bad in [{}, {"rust": "Beginner"}, {"python": "Expert"}, {"python": "Advanced"}, "Beginner", None]:
        assert validate_capabilities(bad)[0] is None


def test_preferences():
    assert validate_preferences(["projects", "video", "video"]) == (["video", "projects"], None)
    for bad in [[], ["podcasts"], "video", None]:
        assert validate_preferences(bad)[0] is None


def test_constraints():
    assert validate_constraints({}) == ({}, None)
    assert validate_constraints({"budget": "monthly", "monthly_budget": "50", "remote_only": True, "weekends_only": False}) == (
        {"monthly_budget": 50, "budget": "monthly", "remote_only": True}, None,
    )
    assert validate_constraints({"budget": "free_only", "other": "  no  travel "}) == (
        {"budget": "free_only", "other": "no travel"}, None,
    )
    for bad in [{"budget": "monthly"}, {"budget": "cheap"}, {"pets": True}, {"other": "x" * 301}, []]:
        assert validate_constraints(bad)[0] is None


def test_context():
    assert validate_context("  Side project: a chatbot  ") == ("Side project: a chatbot", None)
    assert validate_context("x" * 2001)[0] is None


def test_free_only_budget_conflicts_with_paid_courses():
    assert check_combination(["paid_courses"], {"budget": "free_only"})
    assert check_combination(DEFAULT_PREFERENCES, {"budget": "free_only"}) is None
    assert check_combination(["paid_courses"], {"budget": "monthly", "monthly_budget": 20}) is None


@pytest.mark.parametrize("ml,llm,expected", [
    ("None", "None", "None"), ("Beginner", "Intermediate", "Beginner"), ("Experienced", "Intermediate", "Intermediate"),
    ("Experienced", "Experienced", "Experienced"), ("None", "Experienced", "Beginner"),
])
def test_ai_level_is_the_rounded_down_mean(ml, llm, expected):
    assert ai_level({"machine_learning": ml, "ai_llms": llm}) == expected


def test_ai_level_needs_both_ratings():
    assert ai_level({"machine_learning": "Beginner"}) is None and ai_level(None) is None


def test_missing_fields():
    assert "hours_per_week" in missing_fields({"current_role": "x"})
    assert missing_fields(FULL) == []
    assert missing_fields({**FULL, "capabilities": {"python": "Beginner"}}) == ["capabilities"]


def test_steps_in_order_and_optional_steps():
    assert [s["id"] for s in steps({})] == [
        "goal", "resume", "background", "hours", "capabilities", "preferences", "constraints", "context",
    ]
    assert next_step({}) == "goal"
    assert next_step(FULL) == "resume"
    assert next_step({**FULL, "resume_skipped": True}) == "preferences"
    assert next_step({**FULL, "resume_status": "review"}) == "resume"  # a resume waiting for review
    done = {**FULL, "resume_status": "reviewed", "learning_preferences": ["video"], "constraints": {},
            "additional_context": ""}
    assert next_step(done) is None


def test_help_choose_moves_the_goal_after_the_background():
    order = [s["id"] for s in steps({}, help_choose=True)]
    assert order[:4] == ["resume", "background", "goal", "hours"]
    assert next_step({"resume_skipped": True, "current_role": "QA Engineer", "years_experience": 3,
                      "domain": "Retail"}, help_choose=True) == "goal"
