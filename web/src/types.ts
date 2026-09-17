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
