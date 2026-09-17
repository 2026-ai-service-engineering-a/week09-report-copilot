/**
 * 화면이 아는 문서의 모양.
 *
 * 서버의 `core/schema.py`와 **같은 스키마**다. 한쪽을 고치면 다른 쪽도
 * 고쳐야 하고, 그것이 공유 상태의 값이자 비용이다. 실제 제품에서는 서버의
 * pydantic 모델에서 타입을 생성해 이 파일을 지운다.
 */
export type ChartKind = 'line' | 'bar' | 'pie'

export type Section = {
  id: string
  kind: 'chart' | 'table' | 'text'
  title: string
  metric: string
  chart: ChartKind | null
  groupBy: string | null
  limit: number
  rows: [string, number | null][]
  note: string
  status: 'ok' | 'pending' | 'unverified' | 'stopped_by_budget'
}

export type Report = {
  title: string
  period: { from: string; to: string }
  filters: { nation: string; movieType: string }
  sections: Section[]
  conclusion: string
  publishedAt: string | null
}

/** 화면 모드 넷. 코어는 하나이고 갈리는 것은 요청이 무엇을 싣느냐뿐이다. */
export type Mode = 'v0' | 'v1' | 'v2' | 'v3'

export const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: 'v0', label: 'v0 · 폼형', hint: 'AI가 화면 뒤에. 조건만 보낸다' },
  { id: 'v1', label: 'v1 · 챗 위젯', hint: 'AI가 화면 옆에. 대화만 보낸다' },
  { id: 'v2', label: 'v2 · 공유 상태', hint: 'AI가 화면 안에. 문서와 선택을 함께 보낸다' },
  { id: 'v3', label: 'v3 · 생성 UI', hint: '에이전트가 화면에 컴포넌트를 낸다' },
]
