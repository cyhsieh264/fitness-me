"""Outbound LINE message formatting: markdown stripping, list spacing,
[IMAGE:url] parsing.

LINE renders plain text only, so strip_markdown is the safety net behind the
prompt's LINE OUTPUT FORMAT rule. These tests lock in two invariants: common
markdown syntax is flattened, and legitimate plain-text uses of the same
characters (workout notation, the [IMAGE:url] tag) survive untouched.

space_list_items is the same kind of safety net for list readability: long
list items that wrap in LINE's narrow window get a blank line between them,
while uniformly short lists stay tight.
"""

from linebot.v3.messaging import ImageMessage, TextMessage

from src.line.handler import _build_messages, space_list_items, strip_markdown


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


class TestSpaceListItems:
    def test_long_dash_items_get_blank_lines(self):
        text = (
            "你昨天的訓練：\n"
            "- 史密斯後弓箭步：主要訓練 股四頭肌 和 臀大肌。\n"
            "- 槓鈴RDL：主要訓練 臀大肌 和 膕繩肌。\n"
            "- 短槓肩推：主要訓練 前三角肌 和 中三角肌。"
        )
        expected = (
            "你昨天的訓練：\n"
            "- 史密斯後弓箭步：主要訓練 股四頭肌 和 臀大肌。\n"
            "\n"
            "- 槓鈴RDL：主要訓練 臀大肌 和 膕繩肌。\n"
            "\n"
            "- 短槓肩推：主要訓練 前三角肌 和 中三角肌。"
        )
        assert space_list_items(text) == expected

    def test_short_items_stay_tight(self):
        text = "練最多的肌群：\n- 臀大肌\n- 前三角肌\n- 二頭肌"
        assert space_list_items(text) == text

    def test_one_long_item_spaces_the_whole_run(self):
        text = "- 臀大肌\n- 後三角肌：可以試試 Cable 後三角飛鳥或俯身啞鈴飛鳥"
        expected = (
            "- 臀大肌\n\n- 後三角肌：可以試試 Cable 後三角飛鳥或俯身啞鈴飛鳥"
        )
        assert space_list_items(text) == expected

    def test_already_spaced_list_unchanged(self):
        text = (
            "- 史密斯後弓箭步：主要訓練 股四頭肌 和 臀大肌。\n"
            "\n"
            "- 槓鈴RDL：主要訓練 臀大肌 和 膕繩肌。"
        )
        assert space_list_items(text) == text

    def test_emoji_bullets_get_blank_lines(self):
        text = (
            "\U0001F3CB️ 史密斯後弓箭步：主要訓練 股四頭肌 和 臀大肌。\n"
            "\U0001F3CB️ 槓鈴RDL：主要訓練 臀大肌 和 膕繩肌。"
        )
        expected = text.replace("。\n", "。\n\n")
        assert space_list_items(text) == expected

    def test_single_item_unchanged(self):
        text = "- 後三角肌：可以試試 Cable 後三角飛鳥，改善圓肩很有幫助。"
        assert space_list_items(text) == text

    def test_plain_paragraphs_unchanged(self):
        text = "整體來說，昨天訓練的重點放在臀大肌和前三角肌。\n其他肌群各有一個動作。"
        assert space_list_items(text) == text

    def test_separate_runs_evaluated_independently(self):
        # A long-item run gets spaced; a later all-short run stays tight.
        text = (
            "- 史密斯後弓箭步：主要訓練 股四頭肌 和 臀大肌。\n"
            "- 槓鈴RDL：主要訓練 臀大肌 和 膕繩肌。\n"
            "\n"
            "肌群分佈：\n"
            "- 臀大肌：2 個動作\n"
            "- 股四頭肌：1 個動作"
        )
        expected = (
            "- 史密斯後弓箭步：主要訓練 股四頭肌 和 臀大肌。\n"
            "\n"
            "- 槓鈴RDL：主要訓練 臀大肌 和 膕繩肌。\n"
            "\n"
            "肌群分佈：\n"
            "- 臀大肌：2 個動作\n"
            "- 股四頭肌：1 個動作"
        )
        assert space_list_items(text) == expected


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
