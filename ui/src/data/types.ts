// Mirrors the three DuckDB tables in cli/honest_agent/storage.py, one row
// type per table. Keep field names identical to the column names there.

export interface ResultRow {
  result_id: string
  run_id: string
  run_timestamp: string
  eval_id: string
  eval_title: string | null // optional `title:` from the eval YAML
  prompt: string
  category: string | null
  tags: string[] | null
  expected_answer: string
  agent_answer: string
  tools_used: string[] | null
  accuracy_score: number
  accuracy_method: string
  grading_model: string | null // judge model for extract_match/llm_judge; null for contains
  accuracy_rationale: string | null // the judge's reason (llm_judge only)
  extracted_answer: string | null // the value extract_match compared (extract_match only)
  accuracy_tolerance: number | null // extract_match's allowed absolute difference
  accuracy_tolerance_percent: number | null // extract_match's allowed relative difference (0.01 = 1%)
  accuracy_min_score: number | null
  provenance_score: number | null // null when the eval expects no sources: not checked
  expected_sources: string[] | null
  expected_database: string | null
  expected_schema: string | null
  provenance_min_score: number | null
  // Every table/view the agent's counted queries read, with the database/schema each resolved to.
  queried_sources: SourceRef[] | null
  model_name: string
  agent_backend: string
  agent_name: string | null // null for results stored before agents were recorded
  latency_ms: number | null
  steps: number | null // model calls the agent made, each with the tool calls it asked for
  max_steps: number | null // the run's max_tool_steps
  hit_step_limit: boolean | null // used every step and was still asking for tools: no answer
  agent_input_tokens: number | null
  agent_output_tokens: number | null
  grading_input_tokens: number | null
  grading_output_tokens: number | null
}

export interface SourceRef {
  database: string | null // null: the SQL didn't say and no `use` statement set it
  schema: string | null
  name: string
}

export interface AgentLogRow {
  result_id: string
  run_id: string
  eval_id: string
  agent_trace: string // JSON-encoded turn-by-turn trace
  step_details: string | null // JSON StepDetails; null for runs from before the raw layer
}

export interface StepDetails {
  steps: { input_tokens: number; output_tokens: number; duration_ms: number | null; stop_reason: string | null }[]
  tool_ms: Record<string, number | null> // each tool call's duration, by tool_use id
}

export interface ToolCallRow {
  result_id: string
  run_id: string
  eval_id: string
  call_index: number
  tool_name: string
  type: string // "sql" today
  payload: string // JSON, shape depends on `type`
  is_error: boolean | null // the tool returned an error
  generated: boolean | null // SQL a tool wrote (e.g. Cortex Analyst), not necessarily run
  step: number | null // the step (model call) that made the call
  error: string | null // the readable error message, when the call failed
  result_column: string | null // set only when the result was exactly one row and one column
  result_value: string | null
}

export interface ReportData {
  generated_at: string
  results: ResultRow[]
  agent_logs: AgentLogRow[]
  tool_calls: ToolCallRow[]
}
