"""敏感词过滤（发送侧，docs/03 §9）

DFA/Trie 实现：构建一次，之后每条消息 O(n) 单趟扫描。
命中不报错，替换为 REPLACEMENT 后照常入库（docs/06 §6 约定）。
"""

from __future__ import annotations

from collections.abc import Iterable

REPLACEMENT = "***"
_END = "__end__"

# 词库本该来自 sensitive_words 表（M7 接入），这里先给一份占位，
# 保证 M2 链路能跑通；load() 可重复调用覆盖。
DEFAULT_WORDS = ["傻逼", "垃圾", "fuck", "赌博"]


class DFAFilter:
    def __init__(self, words: Iterable[str] | None = None) -> None:
        self._root: dict[str, dict] = {}
        if words is not None:
            self.load(words)

    def load(self, words: Iterable[str]) -> None:
        for word in words:
            word = word.strip().lower()
            if not word:
                continue
            node = self._root
            for ch in word:
                node = node.setdefault(ch, {})
            node[_END] = True
        return None

    def contains(self, text: str) -> bool:
        lower = text.lower()
        for i in range(len(lower)):
            node = self._root
            for ch in lower[i:]:
                if ch not in node:
                    break
                node = node[ch]
                if _END in node:
                    return True
        return False

    def filter(self, text: str) -> str:
        """返回替换后的文本；未命中时返回同一个字符串对象"""
        if not text or not self._root:
            return text

        # 用原串的下标扫描、另建输出：命中长度与替换长度不等时下标才不会错位
        lower = text.lower()
        out: list[str] = []
        i = 0
        n = len(lower)
        while i < n:
            node = self._root
            end = -1
            for j in range(i, n):
                if lower[j] not in node:
                    break
                node = node[lower[j]]
                if _END in node:
                    end = j + 1  # 记最长匹配，不急着停
            if end > i:
                out.append(REPLACEMENT)
                i = end
            else:
                out.append(text[i])
                i += 1
        return "".join(out)


sensitive_filter = DFAFilter(DEFAULT_WORDS)
