/**
 * 차트 — 의존성 없이 SVG로 직접 그린다.
 *
 * 차트 라이브러리를 쓰지 않은 이유가 있다. **생성 UI에서 모델이 고르는 것은
 * 우리가 만든 컴포넌트다.** 그 컴포넌트가 무엇을 받고 무엇을 그리는지가
 * 한 파일에 다 보여야 6장의 이야기가 성립한다.
 *
 * 모델이 정하는 것은 `kind`와 `rows`뿐이고, 색과 축과 여백은 우리 것이다.
 * 그래서 디자인이 깨지지 않는다.
 */
import type { ChartKind } from '../types'

type Props = {
  kind: ChartKind
  rows: [string, number | null][]
  unit?: string
}

const W = 520
const H = 180
const PAD = { top: 12, right: 12, bottom: 28, left: 56 }

const COLORS = ['#2f81f7', '#16a34a', '#d97706', '#7c3aed', '#dc2626',
                '#0891b2', '#db2777', '#65a30d', '#9333ea', '#c2410c']

const fmt = (n: number) =>
  n >= 10000 ? `${Math.round(n / 10000).toLocaleString()}만` : n.toLocaleString()

export function Chart({ kind, rows }: Props) {
  const points = rows.filter(([, v]) => typeof v === 'number') as [string, number][]
  if (points.length === 0) return <p className="muted small">그릴 값이 없습니다.</p>

  const max = Math.max(...points.map(([, v]) => v))
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom

  if (kind === 'pie') {
    const total = points.reduce((sum, [, v]) => sum + v, 0) || 1
    let angle = -Math.PI / 2
    return (
      <div className="chart-row">
        <svg viewBox="0 0 180 180" className="chart" role="img">
          {points.slice(0, 8).map(([label, value], i) => {
            const sweep = (value / total) * Math.PI * 2
            const [x1, y1] = [90 + 72 * Math.cos(angle), 90 + 72 * Math.sin(angle)]
            angle += sweep
            const [x2, y2] = [90 + 72 * Math.cos(angle), 90 + 72 * Math.sin(angle)]
            return (
              <path key={label} fill={COLORS[i % COLORS.length]} opacity={0.85}
                d={`M90 90 L${x1} ${y1} A72 72 0 ${sweep > Math.PI ? 1 : 0} 1 ${x2} ${y2} Z`} />
            )
          })}
        </svg>
        <ul className="legend">
          {points.slice(0, 8).map(([label, value], i) => (
            <li key={label}>
              <i style={{ background: COLORS[i % COLORS.length] }} />
              <span>{label}</span>
              <b>{((value / total) * 100).toFixed(1)}%</b>
            </li>
          ))}
        </ul>
      </div>
    )
  }

  if (kind === 'bar') {
    const step = innerW / points.length
    return (
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img">
        <line x1={PAD.left} y1={PAD.top + innerH} x2={W - PAD.right} y2={PAD.top + innerH} className="axis" />
        {points.slice(0, 12).map(([label, value], i) => {
          const h = (value / max) * innerH
          return (
            <g key={label}>
              <rect x={PAD.left + i * step + step * 0.18} y={PAD.top + innerH - h}
                width={step * 0.64} height={h} fill={COLORS[i % COLORS.length]} opacity={0.85}>
                <title>{`${label} · ${value.toLocaleString()}`}</title>
              </rect>
              <text x={PAD.left + i * step + step / 2} y={H - 10} className="tick" textAnchor="middle">
                {label.length > 6 ? `${label.slice(0, 5)}…` : label}
              </text>
            </g>
          )
        })}
        <text x={PAD.left - 8} y={PAD.top + 10} className="tick" textAnchor="end">{fmt(max)}</text>
      </svg>
    )
  }

  const step = points.length > 1 ? innerW / (points.length - 1) : 0
  const path = points
    .map(([, v], i) => `${i === 0 ? 'M' : 'L'}${PAD.left + i * step} ${PAD.top + innerH - (v / max) * innerH}`)
    .join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img">
      <line x1={PAD.left} y1={PAD.top + innerH} x2={W - PAD.right} y2={PAD.top + innerH} className="axis" />
      <path d={path} fill="none" stroke={COLORS[0]} strokeWidth={2} />
      {points.map(([label, v], i) => (
        <circle key={label} cx={PAD.left + i * step} cy={PAD.top + innerH - (v / max) * innerH} r={2.5} fill={COLORS[0]}>
          <title>{`${label} · ${v.toLocaleString()}`}</title>
        </circle>
      ))}
      <text x={PAD.left} y={H - 10} className="tick">{points[0][0]}</text>
      <text x={W - PAD.right} y={H - 10} className="tick" textAnchor="end">{points[points.length - 1][0]}</text>
      <text x={PAD.left - 8} y={PAD.top + 10} className="tick" textAnchor="end">{fmt(max)}</text>
    </svg>
  )
}

export function Table({ rows }: { rows: [string, number | null][] }) {
  return (
    <table className="mini">
      <tbody>
        {rows.slice(0, 10).map(([label, value], i) => (
          <tr key={label}>
            <td className="rank">{i + 1}</td>
            <td>{label}</td>
            <td className="num">{typeof value === 'number' ? value.toLocaleString() : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
