/**
 * 도구 호출을 화면 조각으로 옮기는 자리 — 생성 UI와 승인 카드가 여기 있다.
 *
 * 둘은 같은 메커니즘의 두 용도다. 차이는 **기다리느냐**뿐이다.
 *
 *   결과가 따라온 호출  → 우리 컴포넌트로 그린다 (생성 UI)
 *   결과가 없는 호출    → 화면이 실행 주체다. 사용자에게 묻고 답을 돌려준다
 *
 * 그리고 가장 흔한 오해를 걷어 낸다. **모델이 마크업을 쓰는 것이 아니다.**
 * 모델이 정하는 것은 도구 이름과 인자뿐이고, 무엇을 그릴지는 아래 표가
 * 정한다. 여기 없는 도구는 화면에 뜨지 않는다.
 */
import { Chart, Table } from './Chart'
import type { ToolCall } from '../agui'

type Props = {
  call: ToolCall
  onRespond(value: string): void
}

export function ToolCard({ call, onRespond }: Props) {
  // ── 승인 카드: 결과가 없는 호출 ────────────────────────────────
  if (call.name === 'confirm_publish' && !call.result) {
    const args = call.args ?? {}
    return (
      <div className="tool-card is-ask">
        <strong>이 리포트를 발행할까요?</strong>
        <p className="small muted">
          {args.summary} · 섹션 {args.sectionCount}개 · {args.period}
        </p>
        <p className="small muted">
          공유 링크가 나가면 회수할 수 없습니다.
        </p>
        <div className="tool-actions">
          <button className="primary" onClick={() => onRespond('approved')}>발행</button>
          <button onClick={() => onRespond('rejected')}>그만두기</button>
        </div>
      </div>
    )
  }

  // ── 생성 UI: 결과가 따라온 호출 ────────────────────────────────
  if (call.name === 'run_query' && call.result?.rows?.length) {
    const rows = call.result.rows as [string, number | null][]
    const grouped = call.result.groupBy && call.result.groupBy !== 'stat_date'
    return (
      <div className="tool-card">
        <strong>{call.result.metric} · {call.result.groupBy}</strong>
        {grouped && rows.length > 6
          ? <Table rows={rows} />
          : <Chart kind={grouped ? 'bar' : 'line'} rows={rows} />}
        <p className="small muted">
          모델이 정한 것은 지표와 축뿐입니다. 컴포넌트는 우리 것 중에서 골랐습니다.
        </p>
      </div>
    )
  }

  if (call.name === 'lookup_metric' && call.result) {
    return (
      <div className="tool-card">
        <strong>{call.result.name ?? call.args?.term}</strong>
        <p className="small">{call.result.desc ?? call.result.error}</p>
        {call.result.expr && <code className="small">{call.result.expr}</code>}
      </div>
    )
  }

  return null
}
