/**
 * AG-UI 클라이언트 — 붙는 쪽의 전부.
 *
 * CopilotKit 같은 프레임워크를 쓰면 이 파일이 없어도 된다. 그래도 손으로
 * 짜 두는 이유는 이 과정이 늘 하는 순서 때문이다. 5주차에 API 바닥을 본 뒤
 * LiteLLM을 얹었고, 6주차에 루프를 손으로 짠 뒤 LangGraph를 봤다.
 * **바닥을 먼저 본 사람만 프레임워크가 무엇을 대신해 주는지 안다.**
 *
 * 하는 일은 셋뿐이다.
 *
 *   ① POST로 RunAgentInput을 보낸다 (지금 문서와 선택을 함께)
 *   ② 돌아오는 SSE를 `data: {…}` 단위로 자른다
 *   ③ 이벤트 종류에 따라 상태를 고치거나 화면에 알린다
 *
 * ③에서 상태를 고치는 방법이 JSON Patch다. 서버가 문서 전체를 다시 보내지
 * 않고 바뀐 자리만 보내므로, 우리는 그 자리만 다시 그린다.
 */
import { applyPatch, type Op } from './patch'
import type { Report } from './types'

export type AguiEvent = {
  type: string
  [key: string]: unknown
}

export type Handlers = {
  onSnapshot(doc: Report): void
  onDelta(ops: Op[], next: Report): void
  onText(id: string, full: string, done: boolean): void
  onEvent(event: AguiEvent): void
  onDone(result: unknown): void
  onError(message: string): void
}

/** 화면이 요청에 함께 싣는 것들. **v1과 v2를 가르는 자리다.** */
export type ForwardedProps = {
  selectedSectionId?: string | null
  uiAction?: Record<string, unknown>
  simulate?: string
  maxCostUsd?: number
}

let runSeq = 0

export async function runAgent(
  threadId: string,
  text: string,
  state: Report | null,
  props: ForwardedProps,
  handlers: Handlers,
  signal?: AbortSignal,
): Promise<void> {
  runSeq += 1
  const body = {
    thread_id: threadId,
    run_id: `r-${runSeq}`,
    // 지금 화면이 들고 있는 문서를 그대로 보낸다. 서버는 이것을 기준으로
    // 패치를 만든다. 기준점이 맞아야 패치가 맞는 자리를 고친다
    state: state ?? {},
    messages: text ? [{ id: `m-${runSeq}`, role: 'user', content: text }] : [],
    tools: [],
    context: [],
    forwarded_props: props,
  }

  const response = await fetch('/api/agent', {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok || !response.body) {
    handlers.onError(`요청이 실패했습니다 (${response.status})`)
    return
  }

  let doc: Report | null = state
  const texts = new Map<string, string>()

  // SSE는 프레임 사이가 빈 줄이다. 청크 경계가 프레임 경계와 다르므로
  // 남는 조각(buffer)을 들고 다음 청크와 이어 붙여야 한다
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let cut = buffer.indexOf('\n\n')
    while (cut !== -1) {
      const frame = buffer.slice(0, cut)
      buffer = buffer.slice(cut + 2)
      cut = buffer.indexOf('\n\n')

      const line = frame.split('\n').find(l => l.startsWith('data:'))
      if (!line) continue
      let event: AguiEvent
      try {
        event = JSON.parse(line.slice(5).trim())
      } catch {
        continue
      }
      handlers.onEvent(event)

      switch (event.type) {
        case 'STATE_SNAPSHOT':
          doc = event.snapshot as Report
          handlers.onSnapshot(doc)
          break

        case 'STATE_DELTA': {
          // **여기가 이 회차의 핵심 세 줄이다.**
          // 서버가 보낸 연산 배열을 우리 문서에 적용하고 다시 그린다
          const ops = event.delta as Op[]
          if (doc) {
            doc = applyPatch(doc, ops)
            handlers.onDelta(ops, doc)
          }
          break
        }

        case 'TEXT_MESSAGE_START':
          texts.set(event.messageId as string, '')
          break

        case 'TEXT_MESSAGE_CONTENT': {
          const id = event.messageId as string
          const next = (texts.get(id) ?? '') + (event.delta as string)
          texts.set(id, next)
          handlers.onText(id, next, false)
          break
        }

        case 'TEXT_MESSAGE_END':
          handlers.onText(event.messageId as string, texts.get(event.messageId as string) ?? '', true)
          break

        case 'RUN_ERROR':
          // 스트림이 시작된 뒤의 실패는 상태 코드로 오지 않는다.
          // 헤더가 이미 200으로 나갔기 때문이다
          handlers.onError(event.message as string)
          break

        case 'RUN_FINISHED':
          handlers.onDone(event.result)
          break
      }
    }
  }
}

/** v1 챗 위젯. **화면 상태를 보내지 않는다.** 그 한 가지가 v2와의 차이다. */
export async function runChat(text: string): Promise<string> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ messages: [{ role: 'user', content: text }] }),
  })
  const data = await response.json()
  return data.reply ?? ''
}
