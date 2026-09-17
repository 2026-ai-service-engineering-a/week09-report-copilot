"""공유 상태 스키마 — 이 저장소가 지켜야 할 것의 목록.

여기 있는 테스트가 깨지면 **에이전트의 권한 범위가 바뀐 것**이다.
"""

import pytest
from pydantic import ValidationError

from core.schema import Report, empty_report, next_section_id


def test_schema_is_the_permission_boundary():
    """스키마에 없는 필드는 들어오지도 못한다.

    "화면을 영어로 바꿔줘"가 거절되는 것은 프롬프트로 부탁해서가 아니라
    고칠 대상이 없기 때문이다 (교안 5장 4절).
    """
    doc = empty_report().dump()
    doc["ui_language"] = "en"
    with pytest.raises(ValidationError):
        Report.model_validate(doc)


def test_wire_names_are_camel_case():
    """화면으로 건너가는 이름은 camelCase다. `period.from`은 파이썬 예약어라 별칭이다."""
    doc = empty_report().dump()
    assert set(doc["period"]) == {"from", "to"}
    assert "movieType" in doc["filters"]
    assert "groupBy" in doc["sections"][0]


def test_section_ids_do_not_collide():
    report = empty_report()
    assert next_section_id(report) == "s3"


def test_group_by_axis_is_closed():
    """축은 열린 문자열이 아니다. 여기 없는 축으로는 나눌 수 없다."""
    doc = empty_report().dump()
    doc["sections"][0]["groupBy"] = "director"      # 지원하지 않는 축
    with pytest.raises(ValidationError):
        Report.model_validate(doc)
