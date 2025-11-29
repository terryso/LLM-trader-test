"""Tests for utils/text.py module."""
import pytest

from utils.text import strip_ansi_codes, escape_markdown


class TestStripAnsiCodes:
    """Tests for strip_ansi_codes function."""

    def test_removes_color_codes(self):
        """Should remove ANSI color codes from text."""
        colored = "\x1b[31mRed text\x1b[0m"
        assert strip_ansi_codes(colored) == "Red text"

    def test_removes_multiple_codes(self):
        """Should remove multiple ANSI codes."""
        text = "\x1b[1m\x1b[32mBold Green\x1b[0m Normal"
        assert strip_ansi_codes(text) == "Bold Green Normal"

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert strip_ansi_codes("") == ""

    def test_handles_no_codes(self):
        """Should return unchanged text when no ANSI codes present."""
        plain = "Plain text without codes"
        assert strip_ansi_codes(plain) == plain

    def test_handles_cursor_movement(self):
        """Should remove cursor movement codes."""
        text = "\x1b[2J\x1b[HHello"
        assert strip_ansi_codes(text) == "Hello"

    def test_handles_256_color(self):
        """Should remove 256-color codes."""
        text = "\x1b[38;5;196mRed 256\x1b[0m"
        assert strip_ansi_codes(text) == "Red 256"

    def test_handles_rgb_color(self):
        """Should remove RGB color codes."""
        text = "\x1b[38;2;255;0;0mRGB Red\x1b[0m"
        assert strip_ansi_codes(text) == "RGB Red"


class TestEscapeMarkdown:
    """Tests for escape_markdown function."""

    def test_escapes_underscore(self):
        """Should escape underscores."""
        assert escape_markdown("hello_world") == r"hello\_world"

    def test_escapes_asterisk(self):
        """Should escape asterisks."""
        assert escape_markdown("*bold*") == r"\*bold\*"

    def test_escapes_brackets(self):
        """Should escape square brackets."""
        assert escape_markdown("[link]") == r"\[link\]"

    def test_escapes_parentheses(self):
        """Should escape parentheses."""
        assert escape_markdown("(text)") == r"\(text\)"

    def test_escapes_backtick(self):
        """Should escape backticks."""
        assert escape_markdown("`code`") == r"\`code\`"

    def test_escapes_hash(self):
        """Should escape hash symbols."""
        assert escape_markdown("#heading") == r"\#heading"

    def test_escapes_plus_minus(self):
        """Should escape plus and minus."""
        assert escape_markdown("+1 -2") == r"\+1 \-2"

    def test_escapes_pipe(self):
        """Should escape pipe character."""
        assert escape_markdown("a|b") == r"a\|b"

    def test_escapes_dot(self):
        """Should escape dots."""
        assert escape_markdown("1.2.3") == r"1\.2\.3"

    def test_escapes_exclamation(self):
        """Should escape exclamation marks."""
        assert escape_markdown("Hello!") == r"Hello\!"

    def test_escapes_backslash(self):
        """Should escape backslashes."""
        assert escape_markdown("path\\to") == r"path\\to"

    def test_handles_empty_string(self):
        """Should return empty string unchanged."""
        assert escape_markdown("") == ""

    def test_handles_none(self):
        """Should return None unchanged (falsy)."""
        assert escape_markdown(None) is None

    def test_handles_plain_text(self):
        """Should return plain text unchanged."""
        assert escape_markdown("Hello World") == "Hello World"

    def test_escapes_multiple_special_chars(self):
        """Should escape multiple special characters in one string."""
        text = "*bold* _italic_ `code`"
        expected = r"\*bold\* \_italic\_ \`code\`"
        assert escape_markdown(text) == expected

    def test_escapes_tilde(self):
        """Should escape tilde character."""
        assert escape_markdown("~strikethrough~") == r"\~strikethrough\~"

    def test_escapes_curly_braces(self):
        """Should escape curly braces."""
        assert escape_markdown("{json}") == r"\{json\}"

    def test_escapes_equals(self):
        """Should escape equals sign."""
        assert escape_markdown("a=b") == r"a\=b"

    def test_escapes_greater_than(self):
        """Should escape greater than sign."""
        assert escape_markdown("a>b") == r"a\>b"
