import axios from 'axios'

export type Conclusion = 'PASS' | 'FAIL' | 'NEEDS_REVIEW' | 'NOT_APPLICABLE' | 'ERROR'

export interface Evidence {
  evidence_id: string
  file_id: string | null
  role: 'TARGET' | 'SOURCE'
  source_category: 'MANUAL' | 'PROJECT' | 'EVIDENCE_PDF' | 'EVIDENCE_IMAGE'
  excerpt: string
  locator: Record<string, unknown>
  score: number
}

export interface CheckRun {
  id: string
  run_type: 'PRIMARY' | 'INDEPENDENT_REVIEW' | 'RETRY'
  attempt_number: number
  executor_type: 'FIELD_RULE' | 'STRUCTURE_RULE' | 'SEMANTIC_AGENT' | 'VISION_AGENT'
  conclusion: Conclusion | null
  reason: string | null
  evidence_ids: string[]
  differences: string[]
  missing_information: string[]
  model_name: string | null
  prompt_version: string
  duration_ms: number
  retry_count: number
  input_tokens: number | null
  output_tokens: number | null
  error_type: string | null
  created_at: string
}

export interface CheckResult {
  id: string
  task_id: string
  check_item_id: string
  check_name: string
  check_type: string
  severity: 'CRITICAL' | 'NORMAL'
  system_conclusion: Conclusion
  final_conclusion: Conclusion
  reason_code: string
  reason: string
  evidence_ids: string[]
  has_manual_override: boolean
  evidences: Evidence[]
  runs: CheckRun[]
  created_at: string
  updated_at: string
}

export interface ResultList {
  schema_version: '1.0'
  task_id: string
  task_status: string
  items: CheckResult[]
}

export async function getResults(taskId: string): Promise<ResultList> {
  const response = await axios.get<ResultList>(`/api/v1/tasks/${taskId}/results`)
  return response.data
}

export async function retryErrors(taskId: string): Promise<void> {
  await axios.post(`/api/v1/tasks/${taskId}/retry-errors`)
}
