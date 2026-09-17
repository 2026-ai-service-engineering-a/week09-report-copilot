/**
 * 박스오피스 리포트 코파일럿 — 화면 하나.
 *
 * 모드를 고르는 스위치가 없다. **완성된 제품 하나**이고, 사람과 에이전트가
 * 같은 문서를 본다. 10주차부터 각자 만들 것도 이 모양이다.
 *
 * 화면이 부르는 것은 `POST /api/agent` 하나다. 요청에 세 가지가 실린다.
 *
 *   state              지금 화면이 들고 있는 리포트 문서
 *   selectedSectionId  무엇을 고른 채로 말했는지
 *   uiAction           버튼·드롭다운으로 조작한 것
 *
 * v0 폼형과 v1 챗 위젯은 API에 그대로 남아 있다(`/api/report`·`/api/chat`).
 * 화면에서 모드를 고르는 대신 `examples/01_chat_widget_breaks.py`가 둘을
 * 나란히 돌려 무엇이 갈리는지 보여 준다. **화면은 제품이고, 비교는 예제의
 * 일이다.**
 */
import { useEffect, useRef, useState } from 'react'
import { runAgent, type AguiEvent, type ToolCall } from './agui'
import { touched, type Op, type Touched } from './patch'
import { ReportView } from './components/ReportView'
import { ToolCard } from './components/ToolCard'
import type { Report } from './types'

const THREAD = 'lab'

type Line = { who: 'user' | 'agent'; text: string; id?: string }
type Config = { mode: string; model: string; provider: string | null; dataReady: boolean }

const EXAMPLES = [
  '2026년 1월부터 월별 관객수 보여줘',
  '국적별로도 보여줘',
  '3분기만',
  '요일별 패턴은?',
  '이 리포트 발행해줘',
]

export default function App() {
  const [report, setReport] = useState<Report | null>(null)
  const [config, setConfig] = useState<Config | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [lines, setLines] = useState<Line[]>([])
  const [events, setEvents] = useState<AguiEvent[]>([])
  const [cards, setCards] = useState<ToolCall[]>([])
  const [hot, setHot] = useState<Touched>({ sections: new Set(), head: false, conclusion: false })
  const [busy, setBusy] = useState(false)
  const [usage, setUsage] = useState<Record<string, unknown> | null>(null)
  const [said, setSaid] = useState('')
  const [showTrace, setShowTrace] = useState(false)
  const traceRef = useRef<HTMLDivElement>(null)
  const chatRef = useRef<HTMLDivElement>(null)

  // 첫 화면. **저장된 문서를 서버에서 꺼낸다.**
  // 공유 상태가 브라우저에만 있었다면 새로고침에 날아갔을 자리다
  useEffect(() => {
    fetch(`/api/report/${THREAD}`).then(r => r.json()).then(setReport).catch(() => {})
    fetch('/api/config').then(r => r.json()).then(setConfig).catch(() => {})
  }, [])

  useEffect(() => { traceRef.current?.scrollTo({ top: traceRef.current.scrollHeight }) }, [events])
  useEffect(() => { chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight }) }, [lines, cards, busy])

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

    await runAgent(
      THREAD, text, report,
      { selectedSectionId: selected, uiAction, toolResult, maxCostUsd: 0.2 },
      {
        onSnapshot: setReport,
        onDelta: (ops, next) => { setReport(next); flash(ops) },
        onText: (id, full) => setLines(prev => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last?.who === 'agent' && last.id === id) {
            copy[copy.length - 1] = { ...last, text: full }
            return copy
          }
          return [...copy, { who: 'agent', text: full, id }]
        }),
        // 도구 호출을 화면 조각으로 옮긴다. 결과가 따라온 것은 그려 주고,
        // 없는 것은 화면이 실행 주체다 (승인 카드)
        onToolCall: call => setCards(prev => [...prev.filter(c => c.id !== call.id), call]),
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

  if (!report) return <main className="app"><p className="muted">불러오는 중…</p></main>

  const scripted = config?.mode === 'offline'

  return (
    <main className="app">
      <header className="top">
        <h1>박스오피스 리포트 코파일럿</h1>
        {config && (
          <span
            className={`pill ${scripted ? 'is-scripted' : 'is-live'}`}
            title={scripted
              ? '키가 없어 각본 대역이 모델을 대신합니다. 질의도 상태 패치도 진짜로 일어납니다'
              : `${config.model}을 실제로 부릅니다`}
          >
            {scripted ? '각본 대역' : config.model}
          </span>
        )}
        {config && !config.dataReady && (
          <span className="pill is-warn">데이터 없음 · scripts.load_data</span>
        )}
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
          editable
        />

        <aside className="side">
          <div className="panel chat">
            <h3>
              코파일럿
              {selected && <em>{selected} 선택됨</em>}
            </h3>

            <div className="lines" ref={chatRef}>
              {lines.length === 0 && !busy && (
                <div className="small muted hints">
                  <p>이렇게 말해 보세요.</p>
                  <ul>
                    {EXAMPLES.map(text => (
                      <li key={text}>
                        <button type="button" onClick={() => send(text)} disabled={busy}>{text}</button>
                      </li>
                    ))}
                  </ul>
                  <p className="tip">섹션을 클릭해 고른 다음 "이거 빼줘"라고 해 보세요.</p>
                </div>
              )}
              {lines.map((line, i) => (
                <p key={i} className={`line is-${line.who}`}>{line.text}</p>
              ))}
              {cards.map(call => (
                <ToolCard
                  key={call.id}
                  call={call}
                  onRespond={value => {
                    setCards(prev => prev.filter(c => c.id !== call.id))
                    send('', undefined, { name: call.name, value })
                  }}
                />
              ))}
              {busy && <p className="line is-agent is-busy">도는 중…</p>}
            </div>

            <form onSubmit={e => { e.preventDefault(); const t = said.trim(); setSaid(''); if (t) send(t) }}>
              <input
                value={said}
                onChange={e => setSaid(e.target.value)}
                placeholder={busy ? '도는 중…' : '무엇을 할까요?'}
                disabled={busy}
              />
              <button disabled={busy || !said.trim()}>보내기</button>
            </form>
          </div>

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
