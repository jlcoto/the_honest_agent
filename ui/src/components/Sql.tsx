import type { CSSProperties, ReactNode } from 'react'
import { formatDialect, postgresql } from 'sql-formatter'
import { getSegments } from 'sql-highlight'

/**
 * SQL as the agent sent it, made readable: a long query sent on one line is laid out with
 * sql-formatter, and keywords take the accent colour (sql-highlight). Only whitespace
 * changes: the words and their case stay as written, and a query the agent already wrote
 * over several lines keeps its own lines. Display only; provenance parses the original.
 */

// Short enough to read at a glance on one line.
const SHORT = 60

/** A long one-line query, laid out a clause per line; anything else, as written. */
export function formatSql(sql: string): string {
  const text = sql.replace(/^\s*\n/, '').replace(/\s+$/, '')
  if (text.includes('\n')) return dedent(text)
  if (text.length <= SHORT) return text
  try {
    // The report doesn't know the warehouse's dialect; PostgreSQL's parses the most of what
    // agents send (DuckDB and Snowflake SQL too). SQL it can't parse is shown as sent.
    return formatDialect(text, { dialect: postgresql, keywordCase: 'preserve' })
  } catch {
    return text
  }
}

function dedent(text: string): string {
  const lines = text.split('\n')
  const pad = Math.min(...lines.filter((l) => l.trim()).map((l) => l.match(/^ */)![0].length))
  return lines.map((l) => l.slice(pad).replace(/\s+$/, '')).join('\n')
}

const keyword: CSSProperties = { color: 'var(--accent)', fontWeight: 500 }

/** The query with its keywords in the accent colour, in the case the agent wrote them. */
export function highlight(sql: string): ReactNode {
  return getSegments(sql).map((s, i) =>
    s.name === 'keyword' ? (
      <span key={i} style={keyword}>
        {s.content}
      </span>
    ) : (
      s.content
    ),
  )
}
