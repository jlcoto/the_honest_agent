import type { CSSProperties, ReactNode } from 'react'

/**
 * The markdown agents write in their answers, rendered: paragraphs, headings, bullet and
 * numbered lists, tables, code (inline and fenced), quotes, bold, italic and links.
 *
 * The answer is untrusted model output, so this builds React elements and never inserts
 * HTML: an HTML tag in the text shows as text. Links open only for http(s) URLs. Display
 * only: grading and the stored results keep the raw text.
 */
export function Markdown({ text, style }: { text: string; style?: CSSProperties }) {
  return <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0, ...style }}>{blocks(text)}</div>
}

const body: CSSProperties = { margin: 0, font: 'var(--type-body)', color: 'var(--fg-1)', textWrap: 'pretty', overflowWrap: 'anywhere' }
const code: CSSProperties = {
  font: '400 0.9em var(--font-mono)',
  padding: '1px 4px',
  borderRadius: 'var(--radius-xs)',
  background: 'var(--bg-sunken)',
  border: '1px solid var(--border-1)',
}
const fence: CSSProperties = {
  margin: 0,
  padding: '10px 12px',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--bg-sunken)',
  border: '1px solid var(--border-1)',
  font: '400 12.5px/1.55 var(--font-mono)',
  color: 'var(--fg-1)',
  whiteSpace: 'pre',
  overflowX: 'auto',
}
const cell: CSSProperties = { padding: '6px 10px', borderBottom: '1px solid var(--border-1)', textAlign: 'left', verticalAlign: 'top' }

const TABLE_ROW = /^\s*\|.*\|\s*$/
const TABLE_RULE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/
// A numbered item has at most three digits, so a line starting with a year ("1997. Revenue…") stays text.
const LIST_ITEM = /^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$/
const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/
// 1,307 · -4.2 · 12% · $3.50 · 1.2e6 · —
const NUMBER = /^\s*(?:[-+]?[$€£]?\s?[\d.,]+(?:e[-+]?\d+)?\s?%?|—|-)?\s*$/i

function blocks(text: string): ReactNode[] {
  const lines = text.replace(/\r\n?/g, '\n').split('\n')
  const out: ReactNode[] = []
  let para: string[] = []
  const flush = () => {
    if (para.length) out.push(<p key={out.length} style={body}>{lineBreaks(para)}</p>)
    para = []
  }

  for (let i = 0; i < lines.length; ) {
    const line = lines[i]
    if (/^\s*```/.test(line)) {
      flush()
      const start = ++i
      while (i < lines.length && !/^\s*```/.test(lines[i])) i++
      out.push(<pre key={out.length} style={fence}>{lines.slice(start, i).join('\n')}</pre>)
      i++
    } else if (TABLE_ROW.test(line) && TABLE_RULE.test(lines[i + 1] ?? '')) {
      flush()
      const align = splitRow(lines[i + 1]).map((c) => (c.endsWith(':') ? 'right' : c.startsWith(':') ? 'left' : undefined))
      const head = splitRow(line)
      const rows: string[][] = []
      i += 2
      while (i < lines.length && TABLE_ROW.test(lines[i])) rows.push(splitRow(lines[i++]))
      out.push(<Table key={out.length} head={head} rows={rows} align={align} />)
    } else if (LIST_ITEM.test(line)) {
      flush()
      const ordered = /^\s*\d/.test(line)
      const items: string[] = []
      while (i < lines.length && (LIST_ITEM.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        const m = LIST_ITEM.exec(lines[i])
        if (m) items.push(m[3])
        else items[items.length - 1] += ' ' + lines[i].trim() // a wrapped item continues
        i++
      }
      const Tag = ordered ? 'ol' : 'ul'
      out.push(
        <Tag key={out.length} style={{ ...body, paddingLeft: 22, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {items.map((item, n) => (
            <li key={n}>{inline(item)}</li>
          ))}
        </Tag>,
      )
    } else if (HEADING.test(line)) {
      flush()
      const [, hashes, title] = HEADING.exec(line)!
      out.push(
        <p key={out.length} style={{ ...body, fontWeight: 600, fontSize: hashes.length <= 2 ? '1.05em' : undefined }}>
          {inline(title)}
        </p>,
      )
      i++
    } else if (/^\s*>/.test(line)) {
      flush()
      const quoted: string[] = []
      while (i < lines.length && /^\s*>/.test(lines[i])) quoted.push(lines[i++].replace(/^\s*>\s?/, ''))
      out.push(
        <div key={out.length} style={{ borderLeft: '3px solid var(--border-2)', paddingLeft: 12, color: 'var(--fg-2)' }}>
          {blocks(quoted.join('\n'))}
        </div>,
      )
    } else if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
      flush()
      out.push(<hr key={out.length} style={{ border: 0, borderTop: '1px solid var(--border-1)', margin: 0, width: '100%' }} />)
      i++
    } else if (!line.trim()) {
      flush()
      i++
    } else {
      para.push(line)
      i++
    }
  }
  flush()
  return out
}

function splitRow(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, '|'))
}

/** A markdown table; wide ones scroll inside their box instead of widening the page. */
function Table({ head, rows, align }: { head: string[]; rows: string[][]; align: (string | undefined)[] }) {
  // A column of numbers lines up on the right, as in a spreadsheet, unless the table says otherwise.
  const numeric = head.map((_, n) => rows.length > 0 && rows.every((row) => NUMBER.test((row[n] ?? '').replace(/[*_`]/g, ''))))
  const style = (n: number): CSSProperties => ({
    ...cell,
    textAlign: (align[n] as CSSProperties['textAlign']) ?? (numeric[n] ? 'right' : 'left'),
  })
  return (
    <div style={{ overflowX: 'auto', maxWidth: '100%', alignSelf: 'flex-start', border: '1px solid var(--border-1)', borderRadius: 'var(--radius-sm)' }}>
      <table style={{ borderCollapse: 'collapse', font: 'var(--type-small)', color: 'var(--fg-1)', fontVariantNumeric: 'tabular-nums' }}>
        <thead>
          <tr style={{ background: 'var(--bg-sunken)' }}>
            {head.map((h, n) => (
              <th key={n} style={{ ...style(n), fontWeight: 600, whiteSpace: 'nowrap' }}>
                {inline(h)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r}>
              {head.map((_, n) => (
                <td key={n} style={{ ...style(n), borderBottom: r === rows.length - 1 ? 0 : cell.borderBottom }}>
                  {inline(row[n] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Lines of one paragraph, with their line breaks kept: agents often mean them. */
function lineBreaks(lines: string[]): ReactNode[] {
  return lines.flatMap((l, n) => (n ? [<br key={`br${n}`} />, ...inline(l.trim(), `${n}-`)] : inline(l.trim(), `${n}-`)))
}

// Inline spans, first match wins: `code`, **bold**, __bold__, *italic*, _italic_, [text](url) (a URL may
// hold one level of brackets, as in Wikipedia's).
const INLINE = /(`+)(.+?)\1|\*\*(.+?)\*\*|__(.+?)__|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)|(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?!\w)|\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)/

function inline(text: string, prefix = ''): ReactNode[] {
  const out: ReactNode[] = []
  let rest = text
  while (rest) {
    const m = INLINE.exec(rest)
    if (!m) {
      out.push(rest)
      break
    }
    if (m.index) out.push(rest.slice(0, m.index))
    const key = `${prefix}${out.length}`
    if (m[2] != null) out.push(<code key={key} style={code}>{m[2]}</code>)
    else if (m[3] != null || m[4] != null) out.push(<strong key={key}>{inline(m[3] ?? m[4], `${key}-`)}</strong>)
    else if (m[5] != null || m[6] != null) out.push(<em key={key}>{inline(m[5] ?? m[6], `${key}-`)}</em>)
    else if (/^https?:\/\//i.test(m[8]))
      out.push(
        <a key={key} href={m[8]} target="_blank" rel="noopener noreferrer nofollow" style={{ color: 'var(--accent)' }}>
          {inline(m[7], `${key}-`)}
        </a>,
      )
    else out.push(m[7]) // not an http(s) link: its text only
    rest = rest.slice(m.index + m[0].length)
  }
  return out
}
