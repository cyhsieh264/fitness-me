"""Whitelist gate: who may talk to the bot.

The critical invariant is fail-closed: an empty ALLOWED_USER_IDS blocks
everyone. The bot is a public LINE Official Account, so "no whitelist
configured" must mean "locked down", never "open to the world".
"""

from src.auth.whitelist import is_user_allowed
from src.config import settings


def _set_allowed(monkeypatch, value: str) -> None:
    monkeypatch.setattr(settings, "allowed_user_ids", value)


class TestIsUserAllowed:
    def test_listed_user_allowed(self, monkeypatch):
        _set_allowed(monkeypatch, "Uaaa,Ubbb")
        assert is_user_allowed("Uaaa")
        assert is_user_allowed("Ubbb")

    def test_unlisted_user_blocked(self, monkeypatch):
        _set_allowed(monkeypatch, "Uaaa,Ubbb")
        assert not is_user_allowed("Uccc")

    def test_empty_whitelist_blocks_everyone(self, monkeypatch):
        """Fail closed: a missing/empty secret must not open the bot up."""
        _set_allowed(monkeypatch, "")
        assert not is_user_allowed("Uaaa")

    def test_whitespace_around_ids_tolerated(self, monkeypatch):
        _set_allowed(monkeypatch, " Uaaa , Ubbb ")
        assert is_user_allowed("Uaaa")
        assert is_user_allowed("Ubbb")
