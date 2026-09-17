"""리포트 문서가 사는 곳.

공유 상태는 **브라우저가 아니라 DB에 산다.** 어디에 두느냐에 따라 이렇게
갈린다 (교안 5장 5절).

| 어디 | 새로고침하면 | 탭을 두 개 열면 | 서버를 재시작하면 |
| 브라우저 메모리 | 날아간다 | 서로 다른 문서 | 무관 |
| 서버 프로세스 | 남는다 | 같은 문서 | **날아간다** |
| DB | 남는다 | 같은 문서 | 남는다 |

8주차 4장 4절에서 "상태는 프로세스가 아니라 DB에 산다"고 했던 그 자리다.
`thread_id`가 어느 리포트인지를 가리키고, 그것은 **요청이 가져온다.**
모델이 정하게 두지 않는다 (7주차 원칙).

쓰기가 필요하므로 여기만 `ADMIN_DATABASE_URL`을 쓴다. 도구가 쓰는 연결은
여전히 읽기 전용이다 (`core/db.py`).
"""

from __future__ import annotations

import json
import os

import psycopg

from core.schema import Report, empty_report


def _url() -> str:
    return os.environ.get("ADMIN_DATABASE_URL") or os.environ.get(
        "DATABASE_URL", "postgresql://report:report@db:5432/boxoffice"
    )


def load(thread_id: str) -> dict:
    """없으면 빈 문서를 만들어 준다. 첫 화면이 비어 있지 않게."""
    try:
        with psycopg.connect(_url(), autocommit=True) as conn:
            row = conn.execute(
                "SELECT doc FROM report WHERE thread_id = %s", (thread_id,)
            ).fetchone()
    except psycopg.Error:
        row = None          # DB가 아직 없어도 화면은 떠야 한다
    if row:
        return row[0]
    return empty_report().dump()


def save(thread_id: str, doc: dict) -> None:
    """마지막 상태를 적어 둔다. 실패해도 이번 응답을 깨뜨리지 않는다."""
    try:
        Report.model_validate(doc)      # 스키마를 통과한 것만 저장한다
    except Exception:
        return
    try:
        with psycopg.connect(_url(), autocommit=True) as conn:
            conn.execute(
                "INSERT INTO report (thread_id, doc, updated_at) "
                "VALUES (%s, %s, now()) "
                "ON CONFLICT (thread_id) DO UPDATE SET doc = EXCLUDED.doc, updated_at = now()",
                (thread_id, json.dumps(doc, ensure_ascii=False)),
            )
    except psycopg.Error:
        pass
