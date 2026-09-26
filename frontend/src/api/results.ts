import axios from 'axios'

export type Conclusion = 'PASS' | 'FAIL' | 'NEEDS_REVIEW' | 'NOT_APPLICABLE' | 'ERROR'

export interface Evidence {
  evidence_id: string
  file_id: string | null
  role: 'TARGET' | 'SOURCE'
  source_category: 'MANUAL' | 'PROJECT' | 'EVIDENCE_PDF' | 'EVIDENCE_IMAGE'
  excerpt: string
  content_type: string
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
  requirement: string
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
  review_records: ReviewRecord[]
  created_at: string
  updated_at: string
}

export interface ResultList {
  schema_version: '1.0'
  task_id: string
  task_status: string
  total: number
  page: number
  page_size: number
  items: CheckResult[]
}

export interface ReviewRecord {
  id: string
  reviewer_name: string
  previous_conclusion: Conclusion
  new_conclusion: Conclusion
  comment: string
  created_at: string
}

export interface ResultFilters {
  conclusion?: Conclusion
  executor_type?: CheckRun['executor_type']
  severity?: CheckResult['severity']
  has_manual_override?: boolean
  page: number
  page_size: number
}

export interface ReportInfo {
  id: string
  task_id: string
  format: 'EXCEL' | 'JSON'
  status: 'PENDING' | 'COMPLETED' | 'FAILED'
  sha256: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export async function getResults(taskId: string, filters?: ResultFilters): Promise<ResultList> {
  const response = await axios.get<ResultList>(`/api/v1/tasks/${taskId}/results`, {
    params: filters,
  })
  return response.data
}

export async function reviewResult(
  taskId: string,
  resultId: string,
  finalConclusion: Conclusion,
  comment: string,
): Promise<void> {
  await axios.post(`/api/v1/tasks/${taskId}/results/${resultId}/review`, {
    final_conclusion: finalConclusion,
    comment,
  })
}

export async function createReport(
  taskId: string,
  format: ReportInfo['format'],
): Promise<ReportInfo> {
  const response = await axios.post<ReportInfo>(`/api/v1/tasks/${taskId}/reports`, { format })
  return response.data
}

export async function downloadReport(taskId: string, report: ReportInfo): Promise<void> {
  const response = await axios.get<Blob>(`/api/v1/tasks/${taskId}/reports/${report.id}`, {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = `verification-report-${report.id}.${report.format === 'EXCEL' ? 'xlsx' : 'json'}`
  link.click()
  URL.revokeObjectURL(url)
}

export async function retryErrors(taskId: string): Promise<void> {
  await axios.post(`/api/v1/tasks/${taskId}/retry-errors`)
}
