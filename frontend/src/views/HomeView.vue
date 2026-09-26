<script setup lang="ts">
import axios from 'axios'
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createTask,
  deleteTask,
  getTasks,
  type CreateTaskFiles,
  type TaskSummary,
} from '../api/tasks'

const router = useRouter()
const tasks = ref<TaskSummary[]>([])
const loading = ref(true)
const creating = ref(false)
const error = ref('')
const name = ref('')
const files = reactive<Partial<CreateTaskFiles>>({ evidence: [] })

function message(value: unknown): string {
  if (axios.isAxiosError(value) && typeof value.response?.data?.message === 'string') {
    return value.response.data.message
  }
  return '操作失败，请稍后重试。'
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    tasks.value = await getTasks()
  } catch (reason) {
    error.value = message(reason)
  } finally {
    loading.value = false
  }
}

function selectFile(key: 'manual' | 'template' | 'project', event: Event): void {
  const selected = (event.target as HTMLInputElement).files?.[0]
  if (selected) files[key] = selected
}

function selectEvidence(event: Event): void {
  files.evidence = Array.from((event.target as HTMLInputElement).files ?? [])
}

function validateFiles(): string | null {
  if (!name.value.trim()) return '请输入任务名称。'
  if (!files.manual || !files.template || !files.project) return '请上传三项必需材料。'
  const all = [files.manual, files.template, files.project, ...(files.evidence ?? [])]
  if (!files.manual.name.toLowerCase().endsWith('.docx')) return '说明书必须是 DOCX。'
  if (!files.template.name.toLowerCase().endsWith('.docx')) return '模板必须是 DOCX。'
  if (!files.project.name.toLowerCase().endsWith('.json')) return '项目资料必须是 JSON。'
  if ((files.evidence ?? []).some((file) => !/\.(pdf|png|jpe?g)$/i.test(file.name))) {
    return '依据材料只支持 PDF、PNG、JPG 或 JPEG。'
  }
  if (new Set(all.map((file) => `${file.name}:${file.size}`)).size !== all.length) {
    return '不能上传重复文件。'
  }
  if (all.some((file) => file.size > 50 * 1024 * 1024)) return '单个文件不能超过 50 MB。'
  return null
}

async function submit(): Promise<void> {
  const validation = validateFiles()
  if (validation) {
    ElMessage.warning(validation)
    return
  }
  creating.value = true
  try {
    const task = await createTask(name.value.trim(), files as CreateTaskFiles)
    ElMessage.success('任务材料已解析，请确认核对清单')
    await router.push({ name: 'checklist', params: { taskId: task.id } })
  } catch (reason) {
    ElMessage.error(message(reason))
  } finally {
    creating.value = false
  }
}

function openTask(task: TaskSummary): void {
  const routeName = task.status === 'AWAITING_CHECKLIST_CONFIRMATION' ? 'checklist' : 'results'
  void router.push({ name: routeName, params: { taskId: task.id } })
}

async function remove(task: TaskSummary): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `将永久删除任务“${task.name}”及全部本地材料和报告，是否继续？`,
      '删除任务',
      { type: 'warning', confirmButtonText: '永久删除', cancelButtonText: '取消' },
    )
    await deleteTask(task.id)
    ElMessage.success('任务已删除')
    await load()
  } catch (reason) {
    if (reason !== 'cancel') ElMessage.error(message(reason))
  }
}

onMounted(load)
</script>

<template>
  <section class="task-center">
    <header class="page-heading">
      <div><p class="eyebrow">阶段 4 · 完整闭环</p><h1>任务中心</h1></div>
      <el-button @click="load">刷新</el-button>
    </header>

    <el-card shadow="never" class="upload-card">
      <template #header><strong>新建核对任务</strong></template>
      <el-form label-position="top">
        <el-form-item label="任务名称"><el-input v-model="name" maxlength="255" /></el-form-item>
        <div class="upload-grid">
          <label>待核对说明书（DOCX）<input type="file" accept=".docx" @change="selectFile('manual', $event)" /></label>
          <label>说明书模板（DOCX）<input type="file" accept=".docx" @change="selectFile('template', $event)" /></label>
          <label>项目资料（JSON）<input type="file" accept=".json" @change="selectFile('project', $event)" /></label>
          <label>依据材料（PDF/PNG/JPG）<input type="file" multiple accept=".pdf,.png,.jpg,.jpeg" @change="selectEvidence" /></label>
        </div>
        <el-button type="primary" :loading="creating" @click="submit">上传并解析</el-button>
      </el-form>
    </el-card>

    <el-alert v-if="error" type="error" :closable="false" :title="error" show-icon />
    <el-skeleton v-else-if="loading" :rows="5" animated />
    <el-empty v-else-if="tasks.length === 0" description="暂无任务" />
    <el-table v-else :data="tasks" class="task-table">
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column prop="status" label="状态" min-width="180" />
      <el-table-column prop="stage" label="阶段" min-width="180" />
      <el-table-column label="进度" width="170">
        <template #default="scope"><el-progress :percentage="scope.row.progress" /></template>
      </el-table-column>
      <el-table-column label="结果" min-width="260">
        <template #default="scope">
          通过 {{ scope.row.pass_count }} · 失败 {{ scope.row.fail_count }} · 待复核
          {{ scope.row.needs_review_count }} · 错误 {{ scope.row.error_count }}
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="190" />
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="scope">
          <el-button link type="primary" @click="openTask(scope.row)">打开</el-button>
          <el-button link type="danger" @click="remove(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>
