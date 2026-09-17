"""JSON Patch — 서버와 화면이 같은 규격을 본다.

`web/src/patch.ts`가 같은 연산 넷을 구현한다. 둘이 어긋나면 화면과 서버의
문서가 갈라지므로, 여기 테스트가 양쪽의 계약이다.
"""

from core import patch
from core.schema import empty_report


def test_four_operations():
    doc = empty_report().dump()
    patch.apply(doc, [
        patch.replace("/filters/nation", "국적별"),
        patch.add("/sections/-", {"id": "s3", "kind": "text", "title": "메모",
                                  "metric": "audi_cnt", "chart": None, "groupBy": None,
                                  "limit": 10, "rows": [], "note": "", "status": "ok"}),
    ])
    assert doc["filters"]["nation"] == "국적별"
    assert [s["id"] for s in doc["sections"]] == ["s1", "s2", "s3"]

    patch.apply(doc, [patch.move("/sections/2", "/sections/0")])
    assert [s["id"] for s in doc["sections"]] == ["s3", "s1", "s2"]

    patch.apply(doc, [patch.remove("/sections/0")])
    assert [s["id"] for s in doc["sections"]] == ["s1", "s2"]


def test_add_to_array_end():
    """`/sections/-`는 끝에 붙이라는 RFC 6902의 표기다."""
    doc = {"sections": [1, 2]}
    patch.apply(doc, [patch.add("/sections/-", 3)])
    assert doc["sections"] == [1, 2, 3]


def test_patch_is_smaller_than_snapshot():
    """패치를 쓰는 이유가 크기다. 숫자로 확인해 둔다."""
    import json

    doc = empty_report().dump()
    snapshot = len(json.dumps(doc, ensure_ascii=False))
    delta = len(json.dumps([patch.replace("/sections/0/chart", "bar")], ensure_ascii=False))
    assert delta * 5 < snapshot
