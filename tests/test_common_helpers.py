"""Tests for bot/handlers/_common.py helpers."""
from hypothesis import given, strategies as st

from bot.handlers._common import config_path, db_path, telegram_safe

BACKSLASH = chr(92)


class TestPaths:
    def test_db_path_resolvable(self):
        p = db_path()
        assert p.name == "bot.db"
        assert p.parent.name == "data"

    def test_config_path_resolvable(self):
        p = config_path()
        assert p.name == "config.yaml"


class TestTelegramSafe:
    def test_empty(self):
        assert telegram_safe("") == ""

    def test_no_special_chars(self):
        assert telegram_safe("hello world") == "hello world"

    def test_underscore_escaped(self):
        assert telegram_safe("_x_") == BACKSLASH + "_x" + BACKSLASH + "_"

    def test_asterisk_escaped(self):
        assert telegram_safe("*y*") == BACKSLASH + "*y" + BACKSLASH + "*"

    def test_brackets_escaped(self):
        result = telegram_safe("[a]")
        assert result == BACKSLASH + "[a" + BACKSLASH + "]"

    def test_backtick_escaped(self):
        result = telegram_safe("`c`")
        assert result == BACKSLASH + "`c" + BACKSLASH + "`"

    def test_real_world_impact_magnitude(self):
        result = telegram_safe("impact_magnitude >= 3.0")
        assert result == "impact" + BACKSLASH + "_magnitude >= 3.0"

    def test_no_special_passthrough(self):
        assert telegram_safe("abc 123 hello") == "abc 123 hello"

    @given(st.text(min_size=0, max_size=200))
    def test_never_crashes(self, raw):
        result = telegram_safe(raw)
        assert isinstance(result, str)
