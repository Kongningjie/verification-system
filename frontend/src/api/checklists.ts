import axios from 'axios'

export type CheckType =
  | 'FIELD'
  | 'SEMANTIC'
  | 'VISUAL'
  | 'STRUCTURE'
  | 'CUSTOM_SEMANTIC'
  | 'CUSTOM_VISUAL'
  | 'CUSTOM_STRUCTURE'
export type Severity = 'CRITICAL' | 'NORMAL'
export type SourceCategory = 'MANUAL' | 'PROJECT' | 'EVIDENCE_PDF' | 'EVIDENCE_IMAGE'

export interface CheckItem {
  id: string
  source_type: 'COMMON_RULE' | 'TEMPLATE_COMMENT'
  source_comment_id: string | null
  rule_id: string | null
  rule_version: string | null
  name: string
  requirement: string
  check_type: CheckType
  severity: Severity
  required_source_categories: SourceCategory[]
  target_hint: string
  enabled: boolean
  generation_warnings: string[]
  source_comment_text: string | null
  source_selected_text: string | null
  source_heading_path: string[]
  version: number
  created_at: string
  updated_at: string
}

export interface ChecklistResponse {
  schema_version: '1.0'
  task_id: string
  task_status: string
  checklist_revision: number
  confirmed_version: number | null
  items: CheckItem[]
}

export interface ChecklistVersion {
  schema_version: '1.0'
  id: string
  task_id: string
  version_number: number
  item_count: number
  snapshot: Record<string, unknown>[]
  ruleset_version: string
  prompt_version: string
  model_name: string
  created_at: string
}

export type CheckItemUpdate = Pick<
  CheckItem,
  | 'name'
  | 'requirement'
  | 'check_type'
  | 'severity'
  | 'required_source_categories'
  | 'target_hint'
  | 'enabled'
>

export async function getChecklist(taskId: string): Promise<ChecklistResponse> {
  const response = await axios.get<ChecklistResponse>(`/api/v1/tasks/${taskId}/check-items`)
  return response.data
}

export async function updateCheckItem(
  taskId: string,
  item: CheckItem,
  update: CheckItemUpdate,
): Promise<CheckItem> {
  const response = await axios.patch<CheckItem>(
    `/api/v1/tasks/${taskId}/check-items/${item.id}`,
    { expected_version: item.version, ...update },
  )
  return response.data
}

export async function confirmChecklist(
  taskId: string,
  expectedRevision: number,
): Promise<ChecklistVersion> {
  const response = await axios.post<ChecklistVersion>(
    `/api/v1/tasks/${taskId}/check-items/confirm`,
    { expected_revision: expectedRevision },
  )
  return response.data
}
