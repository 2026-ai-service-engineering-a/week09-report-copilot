/**
 * 화면 넷을 한 앱에 담았다. 코어는 하나이고 갈리는 것은 **요청이 무엇을
 * 실어 보내느냐**뿐이다.
 *
 *   v0  조건만 보낸다            POST /api/report
 *   v1  대화만 보낸다            POST /api/chat        ← 여기서 무너진다
 *   v2  대화 + 문서 + 선택        POST /api/agent
 *   v3  v2 + 프런트엔드 도구      POST /api/agent
 *
 * 왼쪽 위에서 모드를 바꿔 가며 같은 한마디("이거 빼줘")를 쳐 보는 것이
 * 이 랩의 첫 번째 실습이다.
 */
import { useEffect, useRef, useState } from 'react'
import { runAgent, runChat, type AguiEvent, type ToolCall } from './agui'
import { touched, type Op, type Touched } from './patch'
import { ReportView } from './components/ReportView'
import { ToolCard } from './components/ToolCard'
import { MODES, type Mode, type Report } from './types'

const THREAD = 'lab'

type Line = { who: 'user' | 'agent'; text: string }

export default function App() {
  const [mode, setMode] = useState<Mode>('v2')
  const [report, setReport] = useState<Report | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [lines, setLines] = useState<Line[]>([])
  const [events, setEvents] = useState<AguiEvent[]>([])
  const [hot, setHot] = useState<Touched>({ sections: new Set(), head: false, conclusion: false })
  const [busy, setBusy] = useState(false)
  const [usage, setUsage] = useState<Record<string, unknown> | null>(null)
  const [said, setSaid] = useState('')
  const [cards, setCards] = useState<ToolCall[]>([])
  const [showTrace, setShowTrace] = useState(false)
  const traceRef = useRef<HTMLDivElement>(null)

  // 첫 화면. **저장된 문서를 서버에서 꺼낸다.**
  // 공유 상태가 브라우저에만 있었다면 새로고침에 날아갔을 자리다
  useEffect(() => {
    fetch(`/api/report/${THREAD}`).then(r => r.json()).then(setReport).catch(() => {})
  }, [])

  useEffect(() => {
    traceRef.current?.scrollTo({ top: traceRef.current.scrollHeight })
  }, [events])

  const flash = (ops: Op[]) => {
    setHot(touched(ops))
    window.setTimeout(
      () => setHot({ sections: new Set(), head: false, conclusion: false }), 1400)
  }

  async function send(
    text: string,
    uiAction?: Record<string, unknown>,
    toolResult?: { name: string; value: string },
  ) {
    if (busy) return
    setBusy(true)
    setEvents([])
    setUsage(null)
    setCards([])
    if (text) setLines(prev => [...prev, { who: 'user', text }])

    // v1은 **일부러** 문서도 선택도 보내지 않는다. 그것이 v1이다
    if (mode === 'v1') {
      const reply = await runChat(text)
      setLines(prev => [...prev, { who: 'agent', text: reply }])
      setBusy(false)
      return
    }

    await runAgent(
      THREAD, text, report,
      {
        selectedSectionId: selected,
        uiAction,
        toolResult,
        maxCostUsd: 0.2,
      },
      {
        onSnapshot: setReport,
        onDelta: (ops, next) => { setReport(next); flash(ops) },
        onText: (id, full) => setLines(prev => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last?.who === 'agent' && (last as Line & { id?: string }).id === id) {
            copy[copy.length - 1] = { ...last, text: full }
            return copy
          }
          return [...copy, Object.assign({ who: 'agent' as const, text: full }, { id })]
        }),
        // v3에서만 도구 호출을 화면 조각으로 옮긴다. v2에서는 같은 이벤트가
        // 흐르지만 화면이 그것을 그리지 않는다. **생성 UI는 프런트의 선택이다**
        onToolCall: call => { if (mode === 'v3') setCards(prev => [...prev.filter(c => c.id !== call.id), call]) },
        onEvent: event => {
          setEvents(prev => [...prev, event])
          // 하네스가 무언가를 막거나 잘랐으면 **사용자에게 말해 준다.**
          // 조용히 자르면 없는 구간이 0이라고 오해한다
          if (event.type === 'CUSTOM' && event.name === 'guard') {
            const v = event.value as { check: string; detail: string }
            setLines(prev => [...prev, { who: 'agent', text: `ⓘ ${v.detail}` }])
          }
        },
        onDone: result => setUsage((result as { usage?: Record<string, unknown> })?.usage ?? null),
        onError: message => setLines(prev => [...prev, { who: 'agent', text: `⚠ ${message}` }]),
      },
    ).catch(e => setLines(prev => [...prev, { who: 'agent', text: `⚠ ${e}` }]))
    setBusy(false)
  }

  async function buildForm(groupBy: string) {
    setBusy(true)
    const response = await fetch('/api/report', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        date_from: report?.period.from ?? '2026-08-01',
        date_to: report?.period.to ?? '2026-08-31',
        group_by: groupBy || null,
      }),
    })
    const data = await response.json()
    setReport(data.report)
    setUsage(data.usage)
    setBusy(false)
  }

  if (!report) return <main className="app"><p className="muted">불러오는 중…</p></main>

  const current = MODES.find(m => m.id === mode)!

  return (
    <main className="app">
      <header className="top">
        <div className="modes">
          {MODES.map(m => (
            <button key={m.id} className={mode === m.id ? 'is-on' : ''} onClick={() => setMode(m.id)}>
              {m.label}
            </button>
          ))}
        </div>
        <p className="hint">{current.hint}</p>
        <label className="trace-toggle">
          <input type="checkbox" checked={showTrace} onChange={e => setShowTrace(e.target.checked)} />
          이벤트 보기
        </label>
      </header>

      <div className="board">
        <ReportView
          report={report}
          selected={selected}
          onSelect={setSelected}
          onAction={action => send('', action)}
          hot={hot}
          editable={mode === 'v2' || mode === 'v3'}
        />

        <aside className="side">
          {mode === 'v0' ? (
            <div className="panel">
              <h3>조건</h3>
              <p className="small muted">
                폼에 있는 것만 말할 수 있습니다. 대화가 낄 자리가 없습니다.
              </p>
              <div className="form">
                {['', 'nation', 'genre', 'distributor'].map(axis => (
                  <button key={axis || 'none'} disabled={busy} onClick={() => buildForm(axis)}>
                    {axis === '' ? '일자별' : axis}로 만들기
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="panel chat">
              <h3>
                {mode === 'v1' ? '챗 위젯' : '코파일럿'}
                {selected && (
                  <em className={mode === 'v1' ? 'is-dead' : ''}>
                    {selected} 선택됨{mode === 'v1' ? ' (보내지 않음)' : ''}
                  </em>
                )}
              </h3>
              {mode === 'v1' && (
                <p className="small warn">
                  이 위젯은 화면을 보지 못합니다. 왼쪽에서 섹션을 고른 다음
                  "이거 빼줘"라고 해 보세요. 고른 것은 화면만 알고 있습니다.
                </p>
              )}
              <div className="lines">
                {lines.length === 0 && (
                  <div className="small muted hints">
                    <p>이렇게 말해 보세요.</p>
                    <ul>
                      <li>2026년 1월부터 월별 관객수 보여줘</li>
                      <li>국적별로도 보여줘 · 장르별은 어때</li>
                      <li>3분기만 · 최근 3개월</li>
                      <li>섹션을 고르고 → 이거 빼줘 · 막대로 바꿔줘</li>
                      <li>이 리포트 발행해줘</li>
                    </ul>
                  </div>
                )}
                {lines.map((line, i) => (
                  <p key={i} className={`line is-${line.who}`}>{line.text}</p>
                ))}
                {cards.map(call => (
                  <ToolCard key={call.id} call={call}
                    onRespond={value => {
                      setCards(prev => prev.filter(c => c.id !== call.id))
                      send('', undefined, { name: call.name, value })
                    }} />
                ))}
              </div>
              <form onSubmit={e => { e.preventDefault(); const t = said.trim(); setSaid(''); if (t) send(t) }}>
                <input value={said} onChange={e => setSaid(e.target.value)}
                  placeholder={busy ? '도는 중…' : '무엇을 할까요?'} disabled={busy} />
                <button disabled={busy || !said.trim()}>보내기</button>
              </form>
            </div>
          )}

          {usage && (
            <p className="usage">
              모델 호출 <b>{String(usage.calls)}</b>회 · ${String(usage.spent_usd)}
              {usage.calls === 0 && <em> 코드가 처리했습니다</em>}
            </p>
          )}

          {showTrace && (
            <div className="panel trace" ref={traceRef}>
              <h3>AG-UI 이벤트</h3>
              {events.length === 0 && <p className="small muted">아직 없습니다.</p>}
              {events.map((event, i) => (
                <div key={i} className="ev">
                  <b>{String(event.type)}</b>
                  <span>{JSON.stringify(event).slice(0, 110)}</span>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
    </main>
  )
}
