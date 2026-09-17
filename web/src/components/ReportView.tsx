/**
 * 리포트 문서 — 공유 상태를 그린 것.
 *
 * 화면이 그리는 것과 에이전트가 고치는 것이 **같은 객체**다. 이 컴포넌트가
 * 받는 `report`는 서버가 보낸 `STATE_DELTA`가 적용된 결과이고, 사용자가
 * 여기서 누르는 것도 같은 문서를 고친다.
 *
 * 섹션을 클릭하면 선택된다. 그 선택이 다음 요청의 `forwardedProps`에 실려
 * 나가고, 그래서 "이거 빼줘"가 통한다. **이 한 가지가 v1과 v2의 차이다.**
 */
import { Chart, Table } from './Chart'
import type { ChartKind, Report, Section } from '../types'

type Props = {
  report: Report
  selected: string | null
  onSelect(id: string | null): void
  onAction(action: Record<string, unknown>): void
  hot: Set<number>
  /** 고르기는 늘 된다. **v1에서도 사용자는 섹션을 고를 수 있다.**
   *  못 고르는 것이 아니라, 고른 것이 요청에 실리지 않는 것이 v1이다 */
  editable: boolean
}

const STATUS_LABEL: Record<Section['status'], string> = {
  ok: '',
  pending: '만드는 중',
  unverified: '확인 못 함',
  stopped_by_budget: '예산으로 중단',
}

export function ReportView({ report, selected, onSelect, onAction, hot, editable }: Props) {
  return (
    <section className="doc">
      <header className="doc-head">
        <h2>{report.title}</h2>
        <p className="meta">
          <span>{report.period.from} ~ {report.period.to}</span>
          <span>국적 {report.filters.nation}</span>
          <span>구분 {report.filters.movieType}</span>
        </p>
      </header>

      {report.sections.length === 0 && (
        <p className="muted">섹션이 없습니다. 오른쪽에서 리포트를 만들어 보세요.</p>
      )}

      {report.sections.map((section, index) => (
        <article
          key={section.id}
          className={[
            'section',
            selected === section.id ? 'is-selected' : '',
            hot.has(index) || hot.has(-1) ? 'is-hot' : '',
            section.status === 'pending' ? 'is-pending' : '',
          ].join(' ')}
          onClick={() => onSelect(selected === section.id ? null : section.id)}
        >
          <div className="section-head">
            <h3>{section.title}</h3>
            <div className="section-tools">
              {STATUS_LABEL[section.status] && (
                <span className={`badge is-${section.status}`}>{STATUS_LABEL[section.status]}</span>
              )}
              <code>{section.metric}{section.groupBy ? ` · ${section.groupBy}` : ''}</code>
              {editable && section.kind === 'chart' && (
                <select
                  value={section.chart ?? 'line'}
                  onClick={e => e.stopPropagation()}
                  onChange={e => onAction({ type: 'set_chart', index, chart: e.target.value as ChartKind })}
                >
                  <option value="line">선</option>
                  <option value="bar">막대</option>
                  <option value="pie">파이</option>
                </select>
              )}
              {editable && index > 0 && (
                <button title="맨 위로" onClick={e => {
                  e.stopPropagation()
                  onAction({ type: 'move_section', from: index, to: 0 })
                }}>↑</button>
              )}
              {editable && (
                <button title="빼기" onClick={e => {
                  e.stopPropagation()
                  onAction({ type: 'remove_section', index })
                }}>×</button>
              )}
            </div>
          </div>

          {section.kind === 'chart'
            ? <Chart kind={section.chart ?? 'line'} rows={section.rows} />
            : <Table rows={section.rows} />}

          {section.note && <p className="note">{section.note}</p>}
        </article>
      ))}

      {report.conclusion && (
        <footer className={`conclusion ${hot.has(-2) ? 'is-hot' : ''}`}>
          <strong>결론</strong>
          <p>{report.conclusion}</p>
        </footer>
      )}
    </section>
  )
}
