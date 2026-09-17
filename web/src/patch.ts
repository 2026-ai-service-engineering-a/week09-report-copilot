/**
 * JSON Patch (RFC 6902) — 서버가 보낸 연산을 문서에 적용한다.
 *
 * 서버 쪽 `core/patch.py`와 **같은 연산 넷**을 구현한다. 둘이 같은 규격을
 * 보고 있어서 양쪽이 서로의 구현을 몰라도 된다. 그것이 규격을 쓰는 이유다.
 *
 * 불변으로 만든다(구조 공유 복사). React가 바뀐 가지만 다시 그리게 하려면
 * 제자리에서 고치면 안 된다.
 */
export type Op =
  | { op: 'add'; path: string; value: unknown }
  | { op: 'replace'; path: string; value: unknown }
  | { op: 'remove'; path: string }
  | { op: 'move'; from: string; path: string }

const segments = (path: string) =>
  path.split('/').slice(1).map(s => s.replace(/~1/g, '/').replace(/~0/g, '~'))

function clone<T>(value: T): T {
  if (Array.isArray(value)) return [...value] as unknown as T
  if (value && typeof value === 'object') return { ...value } as T
  return value
}

/** 경로를 따라 내려가며 지나는 노드만 복사한다. 나머지 가지는 그대로 공유한다. */
function copyPath(root: any, parts: string[]): [any, any, string] {
  const next = clone(root)
  let cursor = next
  for (let i = 0; i < parts.length - 1; i += 1) {
    const key = Array.isArray(cursor) ? Number(parts[i]) : parts[i]
    cursor[key] = clone(cursor[key])
    cursor = cursor[key]
  }
  return [next, cursor, parts[parts.length - 1]]
}

function getAt(root: any, path: string): unknown {
  return segments(path).reduce((cur, key) => (cur == null ? cur : cur[key as any]), root)
}

export function applyOne<T>(doc: T, op: Op): T {
  if (op.op === 'move') {
    const value = getAt(doc, op.from)
    const removed = applyOne(doc, { op: 'remove', path: op.from })
    return applyOne(removed, { op: 'add', path: op.path, value })
  }

  const [next, parent, key] = copyPath(doc, segments(op.path))

  if (op.op === 'add') {
    if (Array.isArray(parent)) {
      key === '-' ? parent.push(op.value) : parent.splice(Number(key), 0, op.value)
    } else {
      parent[key] = op.value
    }
  } else if (op.op === 'replace') {
    parent[Array.isArray(parent) ? Number(key) : (key as any)] = op.value
  } else if (op.op === 'remove') {
    Array.isArray(parent) ? parent.splice(Number(key), 1) : delete parent[key]
  }
  return next
}

export function applyPatch<T>(doc: T, ops: Op[]): T {
  return ops.reduce<T>((current, op) => applyOne(current, op), doc)
}

/** 바뀐 자리에 잠깐 불을 켜려고 쓴다.
 *
 *  `/sections/2/rows` → 섹션 2, `/period/from` → 머리말.
 *  **패치가 어디를 고쳤는지 아는 것이 화면을 덜 깜빡이게 하는 값이다.**
 *  스냅샷을 받으면 이것을 알 수 없어 전부 다시 그리게 된다. */
export type Touched = { sections: Set<number>; head: boolean; conclusion: boolean }

export function touched(ops: Op[]): Touched {
  const out: Touched = { sections: new Set(), head: false, conclusion: false }
  for (const op of ops) {
    if (op.path === '/sections') out.sections.add(-1)          // 통째로 갈렸다
    const found = /^\/sections\/(\d+|-)/.exec(op.path)
    if (found && found[1] !== '-') out.sections.add(Number(found[1]))
    if (op.path.startsWith('/period') || op.path.startsWith('/filters')) out.head = true
    if (op.path.startsWith('/conclusion') || op.path.startsWith('/publishedAt')) out.conclusion = true
  }
  return out
}
