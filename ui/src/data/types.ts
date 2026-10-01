// Mirrors the three DuckDB tables in cli/agent_quiz_cli/storage.py, one row
// type per table. Keep field names identical to the column names there.

export interface ResultRow {
  result_id: string
  run_id: string
  run_timestamp: string
  quiz_id: string
  prompt: string
  category: string | null
  tags: string[] | null
  expected_answer: string
  agent_answer: string
  tools_used: string[] | null
  accuracy_score: number
  accuracy_method: string
  accuracy_rationale: string | null
  accuracy_min_score: number | null
  provenance_score: number
  expected_sources: string[] | null
  expected_database: string | null
  expected_schema: string | null
  provenance_min_score: number | null
  model_name: string
  agent_backend: string
  latency_ms: number | null
  agent_input_tokens: number | null
  agent_output_tokens: number | null
  grading_input_tokens: number | null
  grading_output_tokens: number | null
}

export interface AgentLogRow {
  result_id: string
  run_id: string
  quiz_id: string
  agent_trace: string // JSON-encoded turn-by-turn trace
}

export interface ToolCallRow {
  result_id: string
  run_id: string
  quiz_id: string
  call_index: number
  tool_name: string
  type: string // "sql" today
  payload: string // JSON, shape depends on `type`
}

export interface ReportData {
  generated_at: string
  results: ResultRow[]
  agent_logs: AgentLogRow[]
  tool_calls: ToolCallRow[]
}
