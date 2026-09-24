"""敏感词过滤单测。

DFA 与 AC 跑同一组断言：两者实现不同，但对外的行为契约必须一致
（docs/11 M7 要求可切换）。切换实现时这套用例就是验收线。
"""

import pytest

from app.security.sensitive import REPLACEMENT, ACFilter, DFAFilter, SensitiveFilter


@pytest.fixture(params=[DFAFilter, ACFilter], ids=["dfa", "ac"])
def factory(request) -> type[SensitiveFilter]:
    return request.param


@pytest.fixture
def f(factory: type[SensitiveFilter]) -> SensitiveFilter:
    return factory(["傻逼", "垃圾", "fuck"])


def test_hit_word_is_replaced(f: SensitiveFilter):
    assert f.filter("你这个傻逼") == f"你这个{REPLACEMENT}"


def test_miss_returns_original(f: SensitiveFilter):
    assert f.filter("今天天气不错") == "今天天气不错"


def test_case_insensitive_for_latin(f: SensitiveFilter):
    assert f.filter("FUCK you") == f"{REPLACEMENT} you"


def test_longest_match_wins(f: SensitiveFilter):
    f.load(["傻逼", "傻逼玩意"])
    assert f.filter("傻逼玩意") == REPLACEMENT


def test_multiple_hits(f: SensitiveFilter):
    assert f.filter("垃圾人滚开，别骂傻逼") == f"{REPLACEMENT}人滚开，别骂{REPLACEMENT}"


def test_empty_trie_returns_original(factory: type[SensitiveFilter]):
    assert factory().filter("随便说点什么") == "随便说点什么"


def test_contains(f: SensitiveFilter):
    assert f.contains("这里有垃圾") is True
    assert f.contains("很干净") is False


def test_empty_words_are_skipped(factory: type[SensitiveFilter]):
    f = factory(["傻逼", "  ", ""])
    assert f.filter("   ") == "   "


def test_overlapping_hits_are_merged(factory: type[SensitiveFilter]):
    """abc 和 bcd 在 abcd 里重叠，合并成一段，不能出现 *** 套 ***"""
    f = factory(["abc", "bcd"])
    assert f.filter("abcd") == REPLACEMENT


def test_adjacent_hits_are_merged(factory: type[SensitiveFilter]):
    f = factory(["ab", "cd"])
    assert f.filter("abcd") == REPLACEMENT


def test_two_implementations_agree():
    """切换实现不该改变行为——docs/11 M7 要求可切换，这条就是验收线"""
    words = ["傻逼", "垃圾", "fuck", "ab", "bc", "abc"]
    texts = ["", "abc", "abcd", "你这个傻逼玩意", "垃圾人滚开", "FUCK", "今天天气不错"]
    dfa = DFAFilter(words)
    ac = ACFilter(words)
    for t in texts:
        assert dfa.filter(t) == ac.filter(t), t
