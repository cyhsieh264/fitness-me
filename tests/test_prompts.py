"""Spec-004 §7.6: prompt module assembly via PromptContext.

Each section names that should appear under a given context is what we lock
in here; the exact wording of any one section is allowed to drift without
breaking these tests.
"""

from src.llm.prompts import (
    MODULES,
    PromptContext,
    active_section_names,
    build_system_prompt,
)


def _base_ctx(**overrides) -> PromptContext:
    base = {
        "today_iso": "2026-05-29",
        "timezone": "Asia/Taipei",
        "profile_summary": {"latest_weight_kg": 55.0},
        "active_goals": [],
        "latest_weight_recorded": True,
    }
    base.update(overrides)
    return PromptContext(**base)


def test_module_registry_has_unique_names():
    names = [name for name, _ in MODULES]
    assert len(names) == len(set(names)), names


def test_minimal_context_excludes_conditional_sections():
    """The baseline context (no image / no push / weight recorded) must
    NOT pull in DAILY_PUSH, IMAGE_EXTRACTION, INBODY_REPORTS, WEIGHT_GATING."""
    ctx = _base_ctx()
    active = set(active_section_names(ctx))
    assert "daily_push" not in active
    assert "image_extraction" not in active
    assert "inbody_reports" not in active
    assert "weight_gating" not in active


def test_today_anchor_always_present():
    ctx = _base_ctx()
    text = build_system_prompt(ctx)
    assert "TODAY: 2026-05-29 (Asia/Taipei)" in text


def test_line_formatting_always_present():
    """The plain-text output rules must render in every context — LINE never
    renders markdown regardless of what triggered the turn."""
    for ctx in (
        _base_ctx(),
        _base_ctx(has_pending_daily_push=True),
        _base_ctx(image_in_flight="inbody"),
    ):
        assert "line_formatting" in active_section_names(ctx)
        assert "LINE OUTPUT FORMAT" in build_system_prompt(ctx)


def test_identity_guard_always_present():
    """The bot must never disclose its underlying model/vendor — the guard
    section renders in every context, no exceptions."""
    for ctx in (
        _base_ctx(),
        _base_ctx(has_pending_daily_push=True),
        _base_ctx(image_in_flight="inbody"),
    ):
        assert "identity_guard" in active_section_names(ctx)
        assert "IDENTITY & INTERNAL DETAILS" in build_system_prompt(ctx)


def test_daily_push_only_when_pending():
    pending_ctx = _base_ctx(has_pending_daily_push=True)
    not_pending_ctx = _base_ctx(has_pending_daily_push=False)

    assert "daily_push" in active_section_names(pending_ctx)
    assert "daily_push" not in active_section_names(not_pending_ctx)

    pending_text = build_system_prompt(pending_ctx)
    not_pending_text = build_system_prompt(not_pending_ctx)
    assert "DAILY PUSH REPLY" in pending_text
    assert "DAILY PUSH REPLY" not in not_pending_text


def test_image_sections_only_when_image_in_flight():
    image_ctx = _base_ctx(image_in_flight="meal")
    text_ctx = _base_ctx(image_in_flight=None)

    assert "image_extraction" in active_section_names(image_ctx)
    assert "image_extraction" not in active_section_names(text_ctx)

    # IMAGE_CONTEXT + IMAGE_RECALL stay on always — text/image webhooks
    # can pair across turns.
    assert "image_context" in active_section_names(text_ctx)
    assert "image_recall" in active_section_names(text_ctx)


def test_inbody_section_only_when_image_is_inbody():
    inbody_ctx = _base_ctx(image_in_flight="inbody")
    meal_ctx = _base_ctx(image_in_flight="meal")
    text_ctx = _base_ctx(image_in_flight=None)

    assert "inbody_reports" in active_section_names(inbody_ctx)
    assert "inbody_reports" not in active_section_names(meal_ctx)
    assert "inbody_reports" not in active_section_names(text_ctx)


def test_weight_gating_only_when_no_weight():
    gated_ctx = _base_ctx(latest_weight_recorded=False)
    ungated_ctx = _base_ctx(latest_weight_recorded=True)

    assert "weight_gating" in active_section_names(gated_ctx)
    assert "weight_gating" not in active_section_names(ungated_ctx)

    gated_text = build_system_prompt(gated_ctx)
    assert "WEIGHT GATING" in gated_text


def test_user_profile_section_renders_latest_weight_when_missing():
    ctx = _base_ctx(
        profile_summary={"latest_weight_kg": None, "target_max_hr": 175},
        latest_weight_recorded=False,
    )
    text = build_system_prompt(ctx)
    assert "latest_weight_kg: not yet recorded" in text
    assert "target_max_hr: 175" in text


def test_active_goals_section_only_when_goals_present():
    no_goal_ctx = _base_ctx(active_goals=[])
    goal_ctx = _base_ctx(
        active_goals=[
            {
                "id": 7,
                "category": "strength",
                "description": "深蹲 60kg",
                "target_value": 60.0,
                "target_unit": "kg",
            }
        ]
    )
    assert "active_goals" not in active_section_names(no_goal_ctx)
    assert "active_goals" in active_section_names(goal_ctx)
    text = build_system_prompt(goal_ctx)
    assert "[id=7] (strength) 深蹲 60kg target=60.0kg" in text


def test_exercise_queries_section_teaches_autonomous_retry():
    """Spec-004: when first query returns empty, LLM should try alternative
    keywords / muscle_group / pattern itself, not give up and ask the user
    to enumerate exercise names."""
    text = build_system_prompt(_base_ctx())
    # The key phrases that drive the autonomous-retry behaviour.
    assert "不可以馬上回「找不到」" in text or "不要馬上回「找不到」" in text
    assert "不要反問使用者該用什麼名稱" in text
    assert "同義詞" in text
    assert "拆關鍵詞" in text


def test_conditional_savings_vs_full_context():
    """The "everything-on" prompt should be substantially larger than the
    "everything-off" baseline. Spec target was ~2k chars saved on a typical
    text-only turn."""
    minimal = build_system_prompt(_base_ctx())
    maximal = build_system_prompt(
        _base_ctx(
            has_pending_daily_push=True,
            image_in_flight="inbody",
            latest_weight_recorded=False,
        )
    )
    delta = len(maximal) - len(minimal)
    assert delta > 1500, f"expected conditional sections to add ≥1500c; got {delta}"
