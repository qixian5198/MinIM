"""敏感词过滤（发送侧，docs/03 §9）

两种实现同一个 Protocol，可切换、可压测对比（docs/11 M7 / docs/12 §2.5）：

- **DFA（Trie）**：从每个位置起单趟扫描，构建简单，默认实现
- **AC 自动机**：预建 fail 指针，扫描时文本指针不回退，多模式下常数更优

命中不报错，替换为 REPLACEMENT 后照常入库（docs/06 §6 约定）。
压测脚本见 `scripts/bench_sensitive.py`，结论记在 `docs/perf/sensitive-benchmark.md`。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Any, Protocol

REPLACEMENT = "***"
_END = "__end__"

# 节点要么指向子树，要么是结束标记，值类型不统一，只能 Any
Trie = dict[str, Any]

# 词库本该来自 sensitive_words 表（M7 接入），这里先给一份占位，
# 保证 M2 链路能跑通；load() 可重复调用覆盖。
DEFAULT_WORDS = ["傻逼", "垃圾", "fuck", "赌博"]


class SensitiveFilter(Protocol):
    """docs/11 M7：DFA 与 AC 都满足这个协议，可以互相替换"""

    def load(self, words: Iterable[str]) -> None: ...
    def filter(self, text: str) -> str: ...


def _replace_hits(text: str, hits: list[tuple[int, int]]) -> str:
    """命中区间合并后替换成 ***。

    重叠或相邻的合成一段——否则会出现 *** 套 ***，两段紧挨着的敏感词
    替换完看起来像四个星号串。DFA 和 AC 共用这段逻辑，保证切换实现
    不改行为（docs/11 M7 要求可切换）。
    """
    if not hits:
        return text

    merged: list[tuple[int, int]] = []
    for start, end in hits:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    out: list[str] = []
    prev = 0
    for start, end in merged:
        out.append(text[prev:start])
        out.append(REPLACEMENT)
        prev = end
    out.append(text[prev:])
    return "".join(out)


class DFAFilter:
    def __init__(self, words: Iterable[str] | None = None) -> None:
        self._root: Trie = {}
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

        # 原串下标扫描、另建输出：命中长度与替换长度不等时下标才不会错位
        lower = text.lower()
        hits: list[tuple[int, int]] = []
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
                hits.append((i, end))
            # 命中后只前进一格、不跳到 end：跳过去会漏掉"跨越已匹配区域"的词，
            # 比如词库有 ab/bc、文本是 abc 时，跳过就只认出 ab、漏掉 bc。
            # AC 靠 fail 指针天然能找到，DFA 只能靠不跳来对齐（代价是多扫几轮）。
            i += 1
        return _replace_hits(text, hits)


class ACFilter:
    """Aho-Corasick：BFS 建 fail 指针，扫描时不回退文本指针。

    - _goto[i][ch]：状态转移
    - _fail[i]：失配后跳到哪个状态
    - _out[i]：到该状态为止命中的词长（0 表示没命中），建树时沿 fail 链传播最长值
    """

    def __init__(self, words: Iterable[str] | None = None) -> None:
        self._goto: list[dict[str, int]] = [{}]
        self._fail: list[int] = [0]
        self._out: list[int] = [0]
        if words is not None:
            self.load(words)

    def load(self, words: Iterable[str]) -> None:
        for word in words:
            word = word.strip().lower()
            if not word:
                continue
            node = 0
            for ch in word:
                nxt = self._goto[node].get(ch)
                if nxt is None:
                    self._goto.append({})
                    self._fail.append(0)
                    self._out.append(0)
                    nxt = len(self._goto) - 1
                    self._goto[node][ch] = nxt
                node = nxt
            self._out[node] = max(self._out[node], len(word))

        # BFS：根的直连子节点 fail 指向根，其余沿父节点的 fail 链找
        queue: deque[int] = deque(self._goto[0].values())
        while queue:
            cur = queue.popleft()
            for ch, nxt in self._goto[cur].items():
                queue.append(nxt)
                f = self._fail[cur]
                while f and ch not in self._goto[f]:
                    f = self._fail[f]
                self._fail[nxt] = self._goto[f].get(ch, 0)
                if self._fail[nxt] == nxt:
                    self._fail[nxt] = 0
                # 沿 fail 链把更长的命中传播下来，保证最长匹配优先
                self._out[nxt] = max(self._out[nxt], self._out[self._fail[nxt]])
        return None

    def contains(self, text: str) -> bool:
        return self.filter(text) != text

    def filter(self, text: str) -> str:
        if not text or len(self._goto) <= 1:
            return text

        lower = text.lower()
        hits: list[tuple[int, int]] = []
        node = 0
        for i, ch in enumerate(lower):
            while node and ch not in self._goto[node]:
                node = self._fail[node]
            node = self._goto[node].get(ch, 0)
            if self._out[node]:
                end = i + 1
                hits.append((end - self._out[node], end))
        return _replace_hits(text, hits)


# 两个实现都要满足 Protocol：让 mypy 在这行校验一遍，改坏了立即可见
_IMPLEMENTATIONS: list[type[SensitiveFilter]] = [DFAFilter, ACFilter]

sensitive_filter = DFAFilter(DEFAULT_WORDS)
