import type { CSSProperties, ReactNode } from 'react'

/**
 * SQL as the agent sent it, made readable: a long query sent on one line gets a line break
 * before each clause, and keywords take the accent colour. Only whitespace changes: every word, quote and
 * the keywords' case stay as written. Display only; provenance parses the original.
 */

type Token = { kind: 'space' | 'comment' | 'string' | 'ident' | 'number' | 'word' | 'punct'; text: string }

const TOKEN =
  /(\s+)|(--[^\n]*|\/\*[\s\S]*?(?:\*\/|$))|('(?:[^']|'')*'?)|("(?:[^"]|"")*"?|`[^`]*`?)|(\d+(?:\.\d+)?(?:e[-+]?\d+)?)|([A-Za-z_][\w$]*)|([\s\S])/gy

export function tokens(sql: string): Token[] {
  const out: Token[] = []
  const kinds = ['space', 'comment', 'string', 'ident', 'number', 'word', 'punct'] as const
  TOKEN.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = TOKEN.exec(sql))) {
    const i = m.slice(1).findIndex((g) => g != null)
    out.push({ kind: kinds[i], text: m[0] })
  }
  return out
}

const KEYWORDS = new Set(
  `select from where group by order having limit offset join inner left right full outer cross on using as and or not
  in is null like ilike between case when then else end with union all intersect except distinct desc asc
  insert update delete into values set create table view describe show tables columns schemas databases explain
  interval date timestamp time cast over partition rows range qualify filter within lateral exists any true false
  nulls first last recursive fetch next only top pivot unpivot window`.split(/\s+/),
)

// Clause starts that get their own line; a two-word clause is matched on its first word.
const CLAUSE = new Set(['select', 'from', 'where', 'group', 'order', 'having', 'limit', 'offset', 'qualify', 'window', 'union', 'intersect', 'except', 'with'])
const JOIN_START = new Set(['join', 'inner', 'left', 'right', 'full', 'cross'])

const SHORT = 60

/** A long query on one line, split into a line per clause; a query that already has line breaks,
 * or is short enough to read at a glance, is kept as written. */
export function formatSql(sql: string): string {
  const text = sql.replace(/^\s*\n/, '').replace(/\s+$/, '')
  if (text.includes('\n')) return dedent(text)
  if (text.length <= SHORT) return text
  const toks = tokens(text)
  let out = ''
  let prevWord = ''
  const subquery: boolean[] = [] // per open bracket: does it hold a subquery?
  const depth = () => subquery.filter(Boolean).length
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i]
    const word = t.kind === 'word' ? t.text.toLowerCase() : ''
    if (t.text === '(') {
      const next = toks.slice(i + 1).find((x) => x.kind !== 'space')?.text.toLowerCase()
      subquery.push(next === 'select' || next === 'with')
    }
    if (t.text === ')') {
      if (subquery.pop()) {
        out = out.trimEnd() + '\n' + '  '.repeat(depth()) + ')'
        prevWord = '_'
        continue
      }
    }
    const inside = subquery.length === 0 || subquery[subquery.length - 1]
    const pad = '  '.repeat(depth())
    const startsClause =
      (CLAUSE.has(word) && !(word === 'with' && prevWord !== '') && !(word === 'order' && prevWord === 'within')) ||
      (JOIN_START.has(word) && !JOIN_START.has(prevWord) && prevWord !== 'natural')
    if (word && out && inside && startsClause) {
      out = out.trimEnd() + '\n' + pad + t.text
    } else if (word && (word === 'and' || word === 'or') && out && inside && !betweenOpen(toks, i)) {
      out = out.trimEnd() + '\n' + pad + '  ' + t.text
    } else out += t.text
    if (t.kind === 'word') prevWord = word
    else if (t.kind !== 'space') prevWord = '_'
  }
  return out
}

// `x between 1 and 5`: that `and` stays on the line.
function betweenOpen(toks: Token[], i: number): boolean {
  for (let j = i - 1; j >= 0; j--) {
    const w = toks[j].kind === 'word' ? toks[j].text.toLowerCase() : ''
    if (w === 'between') return true
    if (w === 'and' || w === 'or' || CLAUSE.has(w)) return false
  }
  return false
}

function dedent(text: string): string {
  const lines = text.split('\n')
  const pad = Math.min(...lines.filter((l) => l.trim()).map((l) => l.match(/^ */)![0].length))
  return lines.map((l) => l.slice(pad).replace(/\s+$/, '')).join('\n')
}

const keyword: CSSProperties = { color: 'var(--accent)', fontWeight: 500 }

/** The query with its keywords in the accent colour, in the case the agent wrote them. */
export function highlight(sql: string): ReactNode {
  return tokens(sql).map((t, i) =>
    t.kind === 'word' && KEYWORDS.has(t.text.toLowerCase()) ? (
      <span key={i} style={keyword}>
        {t.text}
      </span>
    ) : (
      t.text
    ),
  )
}
