"""문의 계약.

3주차에서 배운 자리다. 입구의 타입 보증이 여기 있고, 이 모델을 통과하지
못한 요청은 핸들러에 닿지 못한다(422).

AG-UI 문(`/agent`)에는 이 파일의 모델이 필요 없다. 규격이 `RunAgentInput`
으로 계약을 이미 갖고 있기 때문이다. **표준을 쓰면 계약도 따라온다**는 것이
9주차에 새로 얻는 것 중 하나다.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    """v0 폼형의 입력. 화면의 폼과 1:1로 대응한다."""

    date_from: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="시작 일자")
    date_to: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="종료 일자")
    group_by: Literal["nation", "genre", "movieType", "distributor"] | None = Field(
        default=None, description="나눌 축. 폼의 드롭다운이다"
    )


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    """v1 챗 위젯의 입력.

    **여기에 화면 상태가 없다는 것이 이 모델의 전부다.** 필드를 더 넣으면
    v1이 v2가 되는데, 그러면 무너지는 장면을 보여줄 수 없다.
    """

    messages: list[ChatMessage] = Field(min_length=1, max_length=20)


class ChatResponse(BaseModel):
    reply: str
