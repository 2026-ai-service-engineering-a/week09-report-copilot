"""말에서 뜻을 읽는 자리 — **한 곳에만 둔다.**

라우터도 노드도 같은 것을 읽는다. 라우터는 "어디로 보낼까"를 정하려고 읽고,
노드는 "무엇을 바꿀까"를 정하려고 읽는다. 읽는 목적이 다를 뿐 읽는 대상은
같으므로 규칙은 한 벌이어야 한다.

**실제로 두 벌이었다가 한쪽만 고쳐 한 번 샜다.** `_chart_word`를 느슨하게
고쳤는데 라우터의 정규식은 그대로여서, "막대 그래프로 해줘"가 라우터에서
분류 호출로 새고 섹션이 하나 더 생겼다. 12장 2절에 적은 것과 같은 종류의
사고이고, 해법도 같다. **손으로 두 번 적은 것은 언젠가 어긋난다.**
"""

from __future__ import annotations

import re

# 차트 종류를 뜻하는 낱말. 뒤에 로·차트·그래프가 따라오면 그것으로 본다
CHART_WORDS = {"막대": "bar", "바 ": "bar", "bar": "bar",
               "선": "line", "라인": "line", "line": "line",
               "파이": "pie", "원형": "pie", "pie": "pie"}

# 섹션을 나눌 축. 앞의 셋이 시간 축이다
AXIS_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("month", ("월별", "달별", "월간")),
    ("week", ("주별", "주간", "주차별")),
    ("weekday", ("요일", "요일별")),
    ("nation", ("국적", "나라", "국가")),
    ("genre", ("장르",)),
    ("distributor", ("배급",)),
    ("watchGrade", ("등급",)),
    ("movieType", ("영화구분", "예술영화", "독립영화")),
    ("movieNm", ("영화별", "작품별", "상위", "순위", "톱")),
]

# 있던 것을 고치라는 뜻의 말들
CHANGE_WORDS = ("바꿔", "변경", "로 해", "로해", "말고", "대신")

REMOVE = re.compile(r"(빼|지워|삭제)")
TO_TOP = re.compile(r"(맨\s*)?위로")
PUBLISH = re.compile(r"(발행|공유\s*링크|내보내)")


def chart_word(said: str) -> str | None:
    """말에서 차트 종류를 읽는다.

    낱말이 나오고 그 뒤에 로·차트·그래프가 따라오면 그것으로 본다.
    정규식으로 말끝을 전부 적으려 들면 사용자가 말하는 방식을 매번
    따라다니게 된다.
    """
    for word, kind in CHART_WORDS.items():
        found = said.find(word)
        if found < 0:
            continue
        tail = said[found + len(word):found + len(word) + 12]
        if tail.startswith("로") or "차트" in tail or "그래프" in tail or "graph" in tail.lower():
            return kind
    return None


def axis_word(said: str) -> str | None:
    """말에 **명시된** 축만 돌려준다. 없으면 None."""
    for axis, words in AXIS_WORDS:
        if any(word in said for word in words):
            return axis
    return None


def says_change(said: str) -> bool:
    return any(word in said for word in CHANGE_WORDS)


def edits_selection(said: str) -> bool:
    """고른 섹션을 손보라는 말인가. 라우터가 `apply`로 보낼지 가린다."""
    return bool(chart_word(said) or REMOVE.search(said) or TO_TOP.search(said))
