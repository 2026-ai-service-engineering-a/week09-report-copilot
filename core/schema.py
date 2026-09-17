"""공유 상태 — 이 저장소에서 가장 중요한 파일.

화면이 그리는 문서와 에이전트가 읽고 쓰는 상태가 **같은 하나**다. 그 하나의
모양이 여기 적혀 있다.

한 문장으로: **이 스키마가 곧 에이전트의 권한 범위다.**

여기 없는 필드는 어떤 경로로도 바뀌지 않는다. "UI 언어를 영어로 바꿔줘"가
거절되는 것은 프롬프트로 부탁해서가 아니라 고칠 대상이 아예 없기 때문이다.
6주차에 "프롬프트는 부탁이고 게이트는 물리 법칙"이라고 했던 그 자리이고,
여기서는 **스키마가 물리 법칙**이다. 권한을 넓히고 싶으면 필드를 넣으면 된다.
요점은 "못 한다"가 아니라 할 수 있는 것의 목록이 코드 한 곳에 있다는 것이다.

필드 이름이 camelCase인 것에도 이유가 있다. 이 문서는 그대로 브라우저로
건너가 React state가 된다. 파이썬에서는 `movie_type`으로 쓰고 나갈 때
`movieType`이 되도록 별칭을 둔다 (AG-UI 이벤트도 선 위에서는 camelCase다).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

SectionKind = Literal["chart", "table", "text"]
ChartKind = Literal["line", "bar", "pie"]
# 섹션을 나눌 수 있는 축. 여기 없는 값으로는 group by를 할 수 없다.
# 앞의 셋이 시간 축이고, 이것이 없으면 "월별로 보여줘"에 대답할 수 없다
GroupBy = Literal[
    "month", "week", "weekday",
    "nation", "genre", "movieType", "watchGrade", "distributor", "movieNm",
]
SectionStatus = Literal["ok", "stopped_by_budget", "unverified", "pending"]


class Base(BaseModel):
    """모든 상태 모델의 공통 설정. 안으로는 snake_case, 밖으로는 camelCase."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",          # 스키마에 없는 필드는 들어오지도 못한다
    )


class Period(Base):
    """리포트가 다루는 기간."""

    from_: date = Field(alias="from", description="시작 일자")
    to: date = Field(description="종료 일자")


class Filters(Base):
    """리포트 전체에 걸리는 조건. 화면의 드롭다운이 이것이다."""

    nation: str = Field(default="전체", description="제작 국가. '전체'면 걸지 않는다")
    movie_type: str = Field(default="전체", description="영화 구분: 일반영화·예술영화·독립영화")


class Section(Base):
    """리포트의 한 조각. 차트 하나, 표 하나, 문단 하나."""

    id: str
    kind: SectionKind
    title: str
    metric: str = Field(description="data/metrics.yaml의 지표 id")
    chart: ChartKind | None = Field(default=None, description="kind가 chart일 때만")
    group_by: GroupBy | None = Field(default=None, description="나눌 축. 없으면 일자별")
    limit: int = Field(default=10, ge=1, le=50, description="표·순위의 행 수")
    rows: list[list] = Field(default_factory=list, description="도구가 채운 집계 결과")
    total: float | None = Field(
        default=None,
        description="잘라 내기 전의 전체 합. 비율을 상위 몇 줄로 계산하지 않게 한다",
    )
    note: str = Field(default="", description="이 섹션에 대한 한 문장")
    status: SectionStatus = Field(default="ok")


class Report(Base):
    """공유 상태 그 자체. 화면이 그리는 것이 이것이고, 에이전트가 고치는 것도 이것이다.

    **여기 `ui_language`도 `theme`도 없다.** 화면의 겉모습은 상태가 아니라
    화면의 것이고, 그래서 에이전트가 손댈 수 없다 (교안 5장 4절).
    """

    title: str = Field(min_length=1, max_length=120)
    period: Period
    filters: Filters = Field(default_factory=Filters)
    sections: list[Section] = Field(default_factory=list, max_length=12)
    conclusion: str = Field(default="", max_length=2000)
    published_at: str | None = Field(
        default=None,
        description="공유 링크를 만든 시각. **되돌리기 어려운 행동**이라 승인 카드를 거친다",
    )

    def dump(self) -> dict:
        """선 위로 나가는 모양. 날짜는 문자열로, 필드는 camelCase로."""
        return self.model_dump(mode="json", by_alias=True)


def empty_report(from_: str = "2026-08-01", to: str = "2026-08-31") -> Report:
    """새 대화가 시작될 때 놓이는 빈 문서.

    섹션 둘을 미리 얹어 둔다. 빈 화면에서 시작하면 사용자가 무엇을 할 수
    있는지 모르고, 무엇보다 **"이거 빼줘"를 시험해 볼 대상이 없다**.
    """
    return Report(
        title=f"{from_[:7].replace('-', '년 ')}월 박스오피스 리포트",
        period=Period(**{"from": from_, "to": to}),
        sections=[
            Section(id="s1", kind="chart", chart="line", metric="audi_cnt",
                    title="일별 관객수"),
            Section(id="s2", kind="table", metric="audi_acc",
                    title="누적 관객 상위 10편", group_by="movieNm"),
        ],
    )


def next_section_id(report: Report) -> str:
    """s1, s2, … 다음 번호. 화면이 섹션을 구분하는 열쇠다."""
    used = {int(s.id[1:]) for s in report.sections if s.id[1:].isdigit()}
    return f"s{max(used, default=0) + 1}"
