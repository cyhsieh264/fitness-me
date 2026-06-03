"""Outbound LINE message formatting: markdown stripping + [IMAGE:url] parsing.

LINE renders plain text only, so strip_markdown is the safety net behind the
prompt's LINE OUTPUT FORMAT rule. These tests lock in two invariants: common
markdown syntax is flattened, and legitimate plain-text uses of the same
characters (workout notation, the [IMAGE:url] tag) survive untouched.
"""

from linebot.v3.messaging import ImageMessage, TextMessage

from src.line.handler import _build_messages, strip_markdown


class TestStripMarkdown:
    def test_bold_asterisks_removed(self):
        assert strip_markdown("**深蹲** 40kg 完成") == "深蹲 40kg 完成"

    def test_bold_underscores_removed(self):
        assert strip_markdown("__重點__ 提醒") == "重點 提醒"

    def test_headings_removed(self):
        text = "# 本週摘要\n## 重訓\n內容"
        assert strip_markdown(text) == "本週摘要\n重訓\n內容"

    def test_inline_code_unwrapped(self):
        assert strip_markdown("輸入 `深蹲 40kg*10*4` 即可") == "輸入 深蹲 40kg*10*4 即可"

    def test_code_fence_lines_removed(self):
        text = "```\n深蹲 40kg*10*4\n```"
        assert strip_markdown(text) == "深蹲 40kg*10*4\n"

    def test_markdown_link_flattened_to_text_and_url(self):
        assert (
            strip_markdown("[報告](https://example.com/r/1)")
            == "報告 https://example.com/r/1"
        )

    def test_workout_notation_single_asterisks_untouched(self):
        text = "深蹲 40kg*10*4\n臥推 9kg each*12*3"
        assert strip_markdown(text) == text

    def test_image_tag_untouched(self):
        text = "上次的 InBody:\n[IMAGE:https://example.com/i/1/abc123]"
        assert strip_markdown(text) == text

    def test_plain_text_with_emoji_untouched(self):
        text = "已記錄 ✓\n\n📌 本週重點\n- 深蹲加 2.5kg"
        assert strip_markdown(text) == text

    def test_hashtag_without_space_untouched(self):
        # "#1" is not a heading — heading syntax requires a space after #.
        assert strip_markdown("#1 深蹲") == "#1 深蹲"


class TestBuildMessages:
    def test_markdown_stripped_before_send(self):
        messages = _build_messages("**已記錄**\n深蹲 40kg*10*4")
        assert len(messages) == 1
        assert isinstance(messages[0], TextMessage)
        assert messages[0].text == "已記錄\n深蹲 40kg*10*4"

    def test_image_tag_becomes_image_message(self):
        messages = _build_messages(
            "上次的 InBody:\n[IMAGE:https://example.com/i/1/abc123]"
        )
        assert len(messages) == 2
        assert isinstance(messages[0], TextMessage)
        assert messages[0].text == "上次的 InBody:"
        assert isinstance(messages[1], ImageMessage)

    def test_empty_after_strip_falls_back_to_placeholder(self):
        messages = _build_messages("")
        assert len(messages) == 1
        assert messages[0].text == "..."
