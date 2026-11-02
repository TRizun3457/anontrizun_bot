from commands import mention_matches


def test_plain_command_matches():
    assert mention_matches("/potata", ["trizun_game"])
    assert mention_matches("/potata 30", ["trizun_game"])


def test_mention_is_case_insensitive_and_checked():
    assert mention_matches("/potata@trizun_game", ["trizun_game"])
    assert mention_matches("/potata@Trizun_Game 30", ["trizun_game"])
    assert not mention_matches("/potata@other_bot", ["trizun_game"])
    assert not mention_matches("/potata@trizun_game", [None])


def test_empty_text():
    assert mention_matches(None, ["x"])
    assert mention_matches("", ["x"])


def test_second_premium_username_and_parser():
    from commands import parse_usernames

    names = ["trizun_gay", "trizun_game"]
    assert mention_matches("/potata@trizun_game", names)
    assert parse_usernames("@a, b;c ,,") == frozenset({"a", "b", "c"})
    assert parse_usernames(None) == frozenset()
