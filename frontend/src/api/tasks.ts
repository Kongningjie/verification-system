import axios from 'axios'

export interface TaskSummary {
  id: string
  name: string
  status: string
  stage: string
  progress: number
  warning_count: number
  checklist_revision: number
  confirmed_checklist_version: number | null
  error_code: string | null
  error_message: string | null
  created_at: string
  updated_at: string
  result_total: number
  pass_count: number
  fail_count: number
  needs_review_count: number
  error_count: number
  manual_override_count: number
}

export interface CreateTaskFiles {
  manual: File
  template: File
  project: File
  evidence: File[]
}

export async function getTasks(): Promise<TaskSummary[]> {
  const response = await axios.get<TaskSummary[]>('/api/v1/tasks')
  return response.data
}

export async function getTask(taskId: string): Promise<TaskSummary> {
  const response = await axios.get<TaskSummary>(`/api/v1/tasks/${taskId}`)
  return response.data
}

export async function createTask(name: string, files: CreateTaskFiles): Promise<TaskSummary> {
  const body = new FormData()
  body.append('name', name)
  body.append('manual', files.manual)
  body.append('template', files.template)
  body.append('project', files.project)
  files.evidence.forEach((file) => body.append('evidence_files', file))
  const response = await axios.post<TaskSummary>('/api/v1/tasks', body)
  return response.data
}

export async function deleteTask(taskId: string): Promise<void> {
  await axios.delete(`/api/v1/tasks/${taskId}`)
}
