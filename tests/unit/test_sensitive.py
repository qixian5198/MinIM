import pytest

from app.security.sensitive import REPLACEMENT, DFAFilter


@pytest.fixture
def f() -> DFAFilter:
    return DFAFilter(["傻逼", "垃圾", "fuck"])


def test_hit_word_is_replaced(f: DFAFilter):
    assert f.filter("你这个傻逼") == f"你这个{REPLACEMENT}"


def test_miss_returns_original(f: DFAFilter):
    assert f.filter("今天天气不错") == "今天天气不错"


def test_case_insensitive_for_latin(f: DFAFilter):
    assert f.filter("FUCK you") == f"{REPLACEMENT} you"


def test_longest_match_wins(f: DFAFilter):
    f.load(["傻逼", "傻逼玩意"])
    assert f.filter("傻逼玩意") == REPLACEMENT


def test_multiple_hits(f: DFAFilter):
    assert f.filter("垃圾人滚开，别骂傻逼") == f"{REPLACEMENT}人滚开，别骂{REPLACEMENT}"


def test_empty_trie_returns_original():
    assert DFAFilter().filter("随便说点什么") == "随便说点什么"


def test_contains(f: DFAFilter):
    assert f.contains("这里有垃圾") is True
    assert f.contains("很干净") is False


def test_empty_words_are_skipped():
    f = DFAFilter(["傻逼", "  ", ""])
    assert f.filter("   ") == "   "
