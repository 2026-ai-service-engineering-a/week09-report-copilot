"""데이터베이스로 나가는 단 한 자리.

앱이 쓰는 연결은 **읽기 전용 계정**이다. `docker-compose.yml`의 `DATABASE_URL`이
`reader`로 되어 있고, 그 역할에는 `SELECT` 권한밖에 없다 (`scripts/initdb.sql`).

모델이 질의에 관여하는 제품에서는 게이트가 둘이어야 한다.

  ① `core/harness.py`의 `gate_query` — 우리가 짠 검사. 구멍이 있을 수 있다
  ② 이 연결의 권한 — 우리 코드와 무관하게 막는다

둘째 층이 있어야 첫째 층의 실수가 사고가 되지 않는다. 6주차에 "게이트는
물리 법칙"이라고 했던 말의 가장 단단한 형태가 DB 권한이다.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import tuple_row

# 어떤 질의도 이보다 오래 붙들지 못한다. 모델이 짠 질의가 테이블을 통째로
# 훑는 사고를 시간으로도 한 번 막는다
STATEMENT_TIMEOUT_MS = 5_000


def url() -> str:
    return os.environ.get(
        "DATABASE_URL", "postgresql://reader:reader@db:5432/boxoffice"
    )


@contextmanager
def connect():
    with psycopg.connect(url(), autocommit=True, row_factory=tuple_row) as conn:
        conn.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
        yield conn


def fetch(sql: str, params: tuple | dict = ()) -> list[tuple]:
    """읽기 질의 하나. 쓰기는 권한이 없어 여기까지 오지도 못한다."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def fetch_one(sql: str, params: tuple | dict = ()) -> tuple | None:
    rows = fetch(sql, params)
    return rows[0] if rows else None


def ready() -> bool:
    """테이블이 적재돼 있는가. `/config`가 화면에 알려 주는 값이다."""
    try:
        return bool(fetch_one("SELECT 1 FROM daily_boxoffice LIMIT 1"))
    except Exception:
        return False
