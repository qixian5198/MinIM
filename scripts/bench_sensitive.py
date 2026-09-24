"""敏感词算法压测（docs/12 §2.5 · M7 的核心实验）

DFA（Trie）与 AC 自动机理论复杂度相同，实际差在常数因子和实现质量。
这个脚本用数据说话：同一份词库、同一份文本，比过滤耗时与构建内存。

用法：

    ~/.venvs/minim/bin/python scripts/bench_sensitive.py

结果人工整理进 `docs/perf/sensitive-benchmark.md`——
这个实验的价值不在选谁，而在学会用数据做技术决策。
"""

import random
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.security.sensitive import ACFilter, DFAFilter  # noqa: E402

WORD_COUNT = 10000
TEXT_LEN = 30000
ROUNDS = 10

# 用有限字符集造词：前缀重叠多，才逼得出 AC 的 fail 指针价值
CHARS = "的是不了在人有我他这个们中来上大为和国地到以说时要就出会可也你对能而"


def gen_words(n: int) -> list[str]:
    words: set[str] = set()
    while len(words) < n:
        length = random.randint(2, 4)
        words.add("".join(random.choice(CHARS) for _ in range(length)))
    return list(words)


def gen_text(length: int, words: list[str]) -> str:
    """正文为主，穿插若干敏感词，保证过滤时真的有命中"""
    filler = "正常文本内容"
    out: list[str] = []
    size = 0
    i = 0
    while size < length:
        out.append(filler)
        size += len(filler)
        if i % 20 == 0:  # 每 20 段插一个敏感词
            w = words[i % len(words)]
            out.append(w)
            size += len(w)
        i += 1
    return "".join(out)


def bench_filter(f, text: str, rounds: int) -> float:
    f.filter(text)  # 预热
    start = time.perf_counter()
    for _ in range(rounds):
        f.filter(text)
    return (time.perf_counter() - start) / rounds


def build_with_memory(cls, words: list[str]):
    tracemalloc.start()
    instance = cls(words)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return instance, peak


def main() -> None:
    random.seed(42)  # 结果可复现
    words = gen_words(WORD_COUNT)
    text = gen_text(TEXT_LEN, words)
    print(f"词库规模 : {len(words)} 词")
    print(f"文本长度 : {len(text)} 字")
    print(f"轮数     : {ROUNDS}")
    print()

    dfa, dfa_mem = build_with_memory(DFAFilter, words)
    ac, ac_mem = build_with_memory(ACFilter, words)

    dfa_t = bench_filter(dfa, text, ROUNDS)
    ac_t = bench_filter(ac, text, ROUNDS)

    # 两者结果必须一致，否则压测没有意义——先正确性后性能
    dfa_out = dfa.filter(text)
    ac_out = ac.filter(text)
    same = dfa_out == ac_out

    print(f"DFA  构建峰值内存 : {dfa_mem / 1024 / 1024:8.2f} MB")
    print(f"AC   构建峰值内存 : {ac_mem / 1024 / 1024:8.2f} MB")
    print(f"DFA  过滤耗时     : {dfa_t * 1000:8.2f} ms/次")
    print(f"AC   过滤耗时     : {ac_t * 1000:8.2f} ms/次")
    print(f"AC / DFA 耗时比   : {ac_t / dfa_t:8.2f}×")
    print(f"两者输出一致      : {same}")


if __name__ == "__main__":
    main()
