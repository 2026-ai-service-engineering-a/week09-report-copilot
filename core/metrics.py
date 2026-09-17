"""지표 사전 — "스크린당 관객수"가 무슨 뜻인지 찾아 오는 자리.

4주차에 배운 검색이 여기서 다시 쓰인다. 대상이 다르다. 그때는 문서였고
여기서는 **업무 용어**다. 컬럼 이름은 데이터에 적혀 있지만 "드롭률"이나
"와이드 릴리즈"는 어디에도 적혀 있지 않다. 실제 BI 제품이 metric layer라고
부르는 자리다.

이 사전이 없으면 모델이 지표를 지어낸다. 지어낸 지표로 만든 리포트는 형태가
멀쩡해서 **틀렸다는 것조차 알기 어렵다.** 그래서 못 찾으면 조용히 넘어가지
않고 `UnknownMetric`을 올린다 (교안 10장 2절).

검색은 임베딩이 아니라 별칭 표다. 지표가 열몇 개뿐이라 벡터를 꺼낼 이유가
없다. **4주차에서 배운 것은 벡터가 아니라 "모르면 찾아본다"는 구조다.**
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from core.errors import UnknownMetric

METRICS_PATH = Path(__file__).resolve().parent.parent / "data" / "metrics.yaml"


class Metric:
    """지표 하나. 계산할 수 없는 지표도 사전에는 있다."""

    def __init__(self, raw: dict):
        self.id: str = raw["id"]
        self.name: str = raw["name"]
        self.aliases: list[str] = raw.get("aliases") or []
        self.unit: str = raw.get("unit") or ""
        self.expr: str | None = raw.get("expr")
        self.computable: bool = bool(raw.get("computable"))
        self.desc: str = (raw.get("desc") or "").strip()

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "unit": self.unit,
            "expr": self.expr, "computable": self.computable, "desc": self.desc,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"Metric({self.id})"


@lru_cache(maxsize=1)
def all_metrics() -> list[Metric]:
    raw = yaml.safe_load(METRICS_PATH.read_text(encoding="utf-8")) or []
    return [Metric(item) for item in raw]


def by_id(metric_id: str) -> Metric:
    for metric in all_metrics():
        if metric.id == metric_id:
            return metric
    raise UnknownMetric(metric_id)


def computable_ids() -> list[str]:
    """도구가 실제로 계산할 수 있는 지표만. 스키마의 enum이 여기서 나온다."""
    return [m.id for m in all_metrics() if m.computable]


def _normalize(text: str) -> str:
    return re.sub(r"[\s·,()]+", "", (text or "").lower())


def lookup(term: str) -> Metric:
    """용어 하나를 지표로 옮긴다. 못 찾으면 **조용히 넘어가지 않는다.**

    맞히는 순서가 있다. 정확히 같은 것 → 별칭 → 들어 있는 것.
    마지막 단계까지 못 찾으면 `UnknownMetric`이다.
    """
    wanted = _normalize(term)
    if not wanted:
        raise UnknownMetric(term)

    metrics = all_metrics()
    for metric in metrics:
        names = [metric.id, metric.name, *metric.aliases]
        if any(_normalize(name) == wanted for name in names):
            return metric
    for metric in metrics:
        names = [metric.name, *metric.aliases]
        if any(wanted in _normalize(name) or _normalize(name) in wanted for name in names):
            return metric
    raise UnknownMetric(term)


def catalog() -> str:
    """모델의 시스템 프롬프트에 붙일 한 덩어리.

    계산할 수 없는 지표도 **일부러 함께 넣는다.** 목록에 없으면 모델은 그냥
    지어내고, 목록에 "계산할 수 없다"고 적혀 있으면 그렇게 답한다.
    """
    lines = []
    for metric in all_metrics():
        mark = "" if metric.computable else "  [계산 불가]"
        lines.append(f"- {metric.id} ({metric.name}, {metric.unit}){mark}: {metric.desc}")
    return "\n".join(lines)
