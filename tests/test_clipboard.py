"""Tests para clipboard read/write."""

from tmuxw.clipboard import get_clipboard_text, set_clipboard_text


class TestClipboard:
    def test_set_and_get_clipboard_text(self):
        """Test basic clipboard set/get round-trip."""
        test_text = "Hello, clipboard!"
        assert set_clipboard_text(test_text)
        retrieved = get_clipboard_text()
        assert retrieved == test_text

    def test_set_and_get_multiline_text(self):
        """Test multiline clipboard text."""
        test_text = "Line 1\nLine 2\nLine 3"
        assert set_clipboard_text(test_text)
        retrieved = get_clipboard_text()
        assert retrieved == test_text

    def test_set_and_get_unicode_text(self):
        """Test Unicode clipboard text."""
        test_text = "Hola ñ 你好 🎉"
        assert set_clipboard_text(test_text)
        retrieved = get_clipboard_text()
        assert retrieved == test_text

    def test_empty_clipboard_text(self):
        """Test setting empty string."""
        assert set_clipboard_text("")
        retrieved = get_clipboard_text()
        assert retrieved == ""

    def test_large_text(self):
        """Test large text block."""
        test_text = "A" * 10000
        assert set_clipboard_text(test_text)
        retrieved = get_clipboard_text()
        assert retrieved == test_text

    def test_get_clipboard_handles_errors(self):
        """Test get_clipboard_text returns None on error (robustness)."""
        # Just verify it doesn't crash
        result = get_clipboard_text()
        assert result is None or isinstance(result, str)
