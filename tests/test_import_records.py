"""Spec-004 §7.7: per-block session_type marker in import_history.

The historical-import parser must understand `YYYY/MM/DD (self|coach|other)`
markers and pass the correct session_type into log_strength_training so the
old "everything-is-coach" hardcode is gone.
"""

from datetime import date

from src.services.import_records import (
    DEFAULT_SESSION_TYPE,
    parse_date_blocks,
)


def test_default_when_no_tag():
    text = "2025/05/12\n深蹲 40kg*10*4\nRDL 35kg*10*3\n"
    blocks = parse_date_blocks(text, cutoff_years=99)
    assert len(blocks) == 1
    d, body, session_type = blocks[0]
    assert d == date(2025, 5, 12)
    assert session_type == DEFAULT_SESSION_TYPE == "self_training"
    assert "深蹲 40kg*10*4" in body


def test_self_tag():
    text = "2025/05/12 (self)\n深蹲 40kg*10*4\n"
    blocks = parse_date_blocks(text, cutoff_years=99)
    assert blocks[0][2] == "self_training"


def test_coach_tag():
    text = "2025/05/14 (coach)\n臥推 30kg*8*3\n"
    blocks = parse_date_blocks(text, cutoff_years=99)
    assert blocks[0][2] == "coach"


def test_other_tag():
    text = "2025/05/16 (other)\n打網球 60min\n"
    blocks = parse_date_blocks(text, cutoff_years=99)
    assert blocks[0][2] == "other"


def test_mixed_blocks_keep_per_block_session_type():
    text = (
        "2025/05/12 (self)\n深蹲 40kg*10*4\n\n"
        "2025/05/14 (coach)\n臥推 30kg*8*3\n\n"
        "2025/05/16\n打網球 60min\n"
    )
    blocks = parse_date_blocks(text, cutoff_years=99)
    assert [(d.isoformat(), st) for d, _, st in blocks] == [
        ("2025-05-12", "self_training"),
        ("2025-05-14", "coach"),
        ("2025-05-16", DEFAULT_SESSION_TYPE),
    ]


def test_unknown_tag_is_ignored_as_no_match():
    """`(foo)` is not a recognised tag; the date line must not match at all
    so the LLM never silently accepts garbage tags as a session type."""
    text = "2025/05/12 (foo)\n深蹲 40kg*10*4\n"
    blocks = parse_date_blocks(text, cutoff_years=99)
    # The 'foo' date line fails the regex entirely, so the body lines have
    # no preceding date and the whole block is dropped.
    assert blocks == []


def test_trailing_whitespace_allowed_after_tag():
    text = "2025/05/14 (coach)   \n深蹲 40kg*10*4\n"
    blocks = parse_date_blocks(text, cutoff_years=99)
    assert blocks[0][2] == "coach"
