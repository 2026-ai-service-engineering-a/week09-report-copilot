"""게이트웨이 첫 기동 준비 — 조직 하나를 만들어 둔다.

관리자 화면의 **Create New Key**는 Organization 칸을 건드리지 않으면 빈
문자열을 보내고, 게이트웨이는 "그런 조직이 없다"며 500으로 거절한다
(LiteLLM v1.100 기준). 고를 조직이 하나도 없으면 화면에서 키를 만들 방법이
없으므로, 기동할 때 기본 조직을 하나 만들어 둔다.

두 번 돌려도 안전하다. 이미 있으면 아무것도 하지 않는다.

    docker compose run --rm gateway-init
"""

import os
import sys
import time

import httpx

BASE = os.environ.get("GATEWAY_INTERNAL_URL", "http://litellm-proxy:4000")
MASTER = os.environ.get("LITELLM_MASTER_KEY", "")
ALIAS = os.environ.get("GATEWAY_ORG_ALIAS", "week09")


def wait_for_gateway(timeout: float = 120.0) -> None:
    started = time.time()
    while time.time() - started < timeout:
        try:
            if httpx.get(f"{BASE}/health/liveliness", timeout=3).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise SystemExit(f"게이트웨이가 {timeout:.0f}초 안에 뜨지 않았다: {BASE}")


def main() -> None:
    if not MASTER:
        raise SystemExit("LITELLM_MASTER_KEY가 없다. gateway/.env를 확인한다")

    wait_for_gateway()
    headers = {"Authorization": f"Bearer {MASTER}"}

    existing = httpx.get(f"{BASE}/organization/list", headers=headers, timeout=10).json()
    if existing:
        names = [o.get("organization_alias") for o in existing]
        print(f"조직이 이미 있다: {names}")
        return

    created = httpx.post(
        f"{BASE}/organization/new", headers=headers,
        json={"organization_alias": ALIAS}, timeout=10,
    ).json()
    print(f"기본 조직을 만들었다: {ALIAS} ({created.get('organization_id')})")
    print("관리자 화면에서 키를 만들 때 Organization 칸에서 이 조직을 고른다")


if __name__ == "__main__":
    sys.exit(main())
