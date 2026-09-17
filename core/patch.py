"""JSON Patch — 공유 상태를 고치는 유일한 문법.

RFC 6902다. 문서 전체를 다시 보내는 대신 **바뀐 자리만** 보낸다. 이유가 셋이다
(교안 5장 3절).

  · 크기: 섹션이 열 개면 스냅샷은 수 KB고, 패치는 연산 한 줄이다
  · 화면: 무엇이 바뀌었는지 알면 그 자리만 다시 그린다. 스크롤과 포커스가 산다
  · 기록: 패치 배열이 곧 변경 이력이고, 되돌리기도 여기서 나온다

대가는 **기준점이 맞아야 한다**는 것이다. 화면이 가진 문서와 서버가 생각하는
문서가 어긋나면 엉뚱한 자리를 고친다. 그래서 실행을 시작할 때 스냅샷으로
한 번 맞추고 간다.

여섯 연산 중 넷만 쓴다. `copy`와 `test`는 이 랩에 쓸 일이 없다.
"""

from __future__ import annotations

from typing import Any


def replace(path: str, value: Any) -> dict:
    return {"op": "replace", "path": path, "value": value}


def add(path: str, value: Any) -> dict:
    """`/sections/-`는 배열 끝에 붙이라는 RFC 6902의 표기다."""
    return {"op": "add", "path": path, "value": value}


def remove(path: str) -> dict:
    return {"op": "remove", "path": path}


def move(from_: str, path: str) -> dict:
    """배열 안에서 자리를 옮긴다. 화면에서 드래그한 것과 같은 결과다."""
    return {"op": "move", "from": from_, "path": path}


def _segments(path: str) -> list[str]:
    return [s.replace("~1", "/").replace("~0", "~") for s in path.split("/")[1:]]


def _parent(doc: Any, parts: list[str]) -> tuple[Any, str]:
    cursor = doc
    for key in parts[:-1]:
        cursor = cursor[int(key)] if isinstance(cursor, list) else cursor[key]
    return cursor, parts[-1]


def get_at(doc: Any, path: str) -> Any:
    cursor = doc
    for key in _segments(path):
        cursor = cursor[int(key)] if isinstance(cursor, list) else cursor[key]
    return cursor


def apply_one(doc: Any, op: dict) -> None:
    """연산 하나를 제자리에서 적용한다."""
    parts = _segments(op["path"])
    parent, key = _parent(doc, parts)
    kind = op["op"]

    if kind == "add":
        if not isinstance(parent, list):
            parent[key] = op["value"]
        elif key == "-":
            parent.append(op["value"])
        else:
            parent.insert(int(key), op["value"])
    elif kind == "replace":
        if isinstance(parent, list):
            parent[int(key)] = op["value"]
        else:
            parent[key] = op["value"]
    elif kind == "remove":
        if isinstance(parent, list):
            parent.pop(int(key))
        else:
            parent.pop(key, None)
    elif kind == "move":
        value = get_at(doc, op["from"])
        apply_one(doc, {"op": "remove", "path": op["from"]})
        apply_one(doc, {"op": "add", "path": op["path"], "value": value})
    else:
        raise ValueError(f"지원하지 않는 연산: {kind}")


def apply(doc: dict, ops: list[dict]) -> dict:
    """서버도 같은 패치를 자기 사본에 적용한다.

    화면만 고치고 서버가 옛 문서를 들고 있으면, 다음 요청에서 둘이 어긋난
    채로 패치가 나간다. **패치를 만든 쪽도 그것을 적용해야 한다.**
    """
    for op in ops:
        apply_one(doc, op)
    return doc
