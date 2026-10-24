from barthelona.llm.thinking import strip_think


def test_closed_and_unterminated_blocks_are_dropped() -> None:
    assert strip_think("<think>plan</think>answer") == "answer"
    assert strip_think("answer<think>cut off") == "answer"


def test_a_closing_tag_without_an_opener_drops_the_thought_before_it() -> None:
    text = "The user wants a program. Let me write it.</think>```asm\n_start:\n```"
    assert strip_think(text) == "```asm\n_start:\n```"


def test_an_orphan_closing_tag_and_a_later_cut_off_block_both_go() -> None:
    assert strip_think("thinking</think>answer<think>more thinking") == "answer"


def test_text_without_tags_is_only_trimmed() -> None:
    assert strip_think("  plain  ") == "plain"
