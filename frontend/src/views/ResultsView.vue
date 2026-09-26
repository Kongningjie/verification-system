<script setup lang="ts">
import axios from 'axios'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'

import {
  createReport,
  downloadReport,
  getResults,
  retryErrors,
  reviewResult,
  type CheckResult,
  type Conclusion,
  type ReportInfo,
  type ResultFilters,
} from '../api/results'
import { getTask } from '../api/tasks'

const route = useRoute()
const taskId = computed(() => String(route.params.taskId))
const results = ref<CheckResult[]>([])
const selected = ref<CheckResult | null>(null)
const taskStatus = ref('')
const total = ref(0)
const loading = ref(true)
const retrying = ref(false)
const reporting = ref(false)
const reviewing = ref(false)
const detailVisible = ref(false)
const reviewVisible = ref(false)
const error = ref('')
const filters = reactive<ResultFilters>({ page: 1, page_size: 10 })
const reviewForm = reactive<{ conclusion: Conclusion; comment: string }>({
  conclusion: 'PASS',
  comment: '',
})
let events: EventSource | null = null
let reconnectTimer: number | null = null

const reviewCommentRequired = computed(() => {
  if (!selected.value) return false
  return selected.value.severity === 'CRITICAL' || (
    ['FAIL', 'ERROR', 'NEEDS_REVIEW'].includes(selected.value.final_conclusion)
    && reviewForm.conclusion === 'PASS'
  )
})
const tagType: Record<Conclusion, 'success' | 'danger' | 'warning' | 'info'> = {
  PASS: 'success', FAIL: 'danger', NEEDS_REVIEW: 'warning', NOT_APPLICABLE: 'info', ERROR: 'danger',
}

function errorMessage(value: unknown): string {
  if (axios.isAxiosError(value) && typeof value.response?.data?.message === 'string') {
    return value.response.data.message
  }
  return '操作失败，请稍后重试。'
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const response = await getResults(taskId.value, filters)
    results.value = response.items
    total.value = response.total
    taskStatus.value = response.task_status
  } catch (reason) {
    error.value = errorMessage(reason)
  } finally {
    loading.value = false
  }
}

async function recoverAndReconnect(): Promise<void> {
  try {
    const task = await getTask(taskId.value)
    taskStatus.value = task.status
    await load()
  } finally {
    if (!reconnectTimer) reconnectTimer = window.setTimeout(connectEvents, 1500)
  }
}

function connectEvents(): void {
  reconnectTimer = null
  events?.close()
  events = new EventSource(`/api/v1/tasks/${taskId.value}/events`)
  events.addEventListener('progress', () => void load())
  events.onerror = () => {
    events?.close()
    events = null
    void recoverAndReconnect()
  }
}

async function retry(): Promise<void> {
  retrying.value = true
  try {
    await retryErrors(taskId.value)
    ElMessage.success('错误项已进入重试队列')
    await load()
  } catch (reason) {
    ElMessage.error(errorMessage(reason))
  } finally {
    retrying.value = false
  }
}

function openDetail(item: CheckResult): void {
  selected.value = item
  detailVisible.value = true
}

function openReview(item: CheckResult): void {
  selected.value = item
  reviewForm.conclusion = item.final_conclusion === 'PASS' ? 'FAIL' : 'PASS'
  reviewForm.comment = ''
  reviewVisible.value = true
}

async function submitReview(): Promise<void> {
  if (!selected.value) return
  if (reviewCommentRequired.value && !reviewForm.comment.trim()) {
    ElMessage.warning('本次改判必须填写复核说明')
    return
  }
  reviewing.value = true
  try {
    await reviewResult(
      taskId.value,
      selected.value.id,
      reviewForm.conclusion,
      reviewForm.comment,
    )
    reviewVisible.value = false
    ElMessage.success('人工复核已记录')
    await load()
  } catch (reason) {
    ElMessage.error(errorMessage(reason))
  } finally {
    reviewing.value = false
  }
}

async function report(format: ReportInfo['format']): Promise<void> {
  reporting.value = true
  try {
    const generated = await createReport(taskId.value, format)
    await downloadReport(taskId.value, generated)
    ElMessage.success(`${format} 报告已生成`)
  } catch (reason) {
    ElMessage.error(errorMessage(reason))
  } finally {
    reporting.value = false
  }
}

function evidenceAsset(result: CheckResult, evidenceId: string): string {
  return `/api/v1/tasks/${taskId.value}/results/${result.id}/evidence/${evidenceId}/asset`
}

onMounted(() => { void load(); connectEvents() })
onBeforeUnmount(() => {
  events?.close()
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
})
</script>

<template>
  <section class="checklist-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">阶段 4 · 结果闭环</p>
        <h1>核对结果</h1>
        <p class="subtitle">任务 {{ taskId }} · 当前状态 {{ taskStatus || '读取中' }}</p>
      </div>
      <div class="result-actions">
        <el-button @click="load">刷新</el-button>
        <el-button v-if="taskStatus === 'COMPLETED_WITH_ERRORS'" type="warning" :loading="retrying" @click="retry">重试错误项</el-button>
        <el-dropdown :disabled="reporting" @command="report">
          <el-button type="primary" :loading="reporting">生成报告</el-button>
          <template #dropdown><el-dropdown-menu><el-dropdown-item command="EXCEL">Excel</el-dropdown-item><el-dropdown-item command="JSON">JSON</el-dropdown-item></el-dropdown-menu></template>
        </el-dropdown>
      </div>
    </header>

    <el-card shadow="never" class="filter-card">
      <el-select v-model="filters.conclusion" clearable placeholder="最终结论" @change="filters.page = 1; load()">
        <el-option v-for="value in ['PASS','FAIL','NEEDS_REVIEW','NOT_APPLICABLE','ERROR']" :key="value" :value="value" />
      </el-select>
      <el-select v-model="filters.executor_type" clearable placeholder="执行通道" @change="filters.page = 1; load()">
        <el-option v-for="value in ['FIELD_RULE','STRUCTURE_RULE','SEMANTIC_AGENT','VISION_AGENT']" :key="value" :value="value" />
      </el-select>
      <el-select v-model="filters.severity" clearable placeholder="严重等级" @change="filters.page = 1; load()">
        <el-option label="关键" value="CRITICAL" /><el-option label="普通" value="NORMAL" />
      </el-select>
      <el-select v-model="filters.has_manual_override" clearable placeholder="人工修改" @change="filters.page = 1; load()">
        <el-option label="已人工修改" :value="true" /><el-option label="未人工修改" :value="false" />
      </el-select>
    </el-card>

    <el-skeleton v-if="loading" :rows="6" animated />
    <el-alert v-else-if="error" type="error" :closable="false" show-icon :title="error" />
    <el-empty v-else-if="results.length === 0" description="暂无符合条件的核对结果" />
    <div v-else class="checklist-items">
      <el-card v-for="item in results" :key="item.id" shadow="never" class="check-item">
        <template #header><div class="item-header"><div class="item-identity"><strong>{{ item.check_name }}</strong><el-tag :type="tagType[item.final_conclusion]">{{ item.final_conclusion }}</el-tag><el-tag v-if="item.has_manual_override" type="warning" effect="plain">人工修改</el-tag><el-tag v-if="item.severity === 'CRITICAL'" type="danger" effect="plain">关键</el-tag></div><span>{{ item.reason_code }}</span></div></template>
        <p class="result-reason">{{ item.reason }}</p>
        <div class="result-actions"><el-button @click="openDetail(item)">查看证据详情</el-button><el-button type="warning" @click="openReview(item)">人工复核</el-button></div>
      </el-card>
      <el-pagination v-model:current-page="filters.page" v-model:page-size="filters.page_size" :total="total" layout="total, prev, pager, next" @current-change="load" />
    </div>

    <el-drawer v-model="detailVisible" title="结果与证据" size="60%">
      <template v-if="selected">
        <el-descriptions :column="1" border><el-descriptions-item label="核对要求">{{ selected.requirement }}</el-descriptions-item><el-descriptions-item label="系统结论">{{ selected.system_conclusion }}</el-descriptions-item><el-descriptions-item label="最终结论">{{ selected.final_conclusion }}</el-descriptions-item><el-descriptions-item label="理由">{{ selected.reason }}</el-descriptions-item></el-descriptions>
        <h3>目标与依据证据</h3>
        <div v-for="evidence in selected.evidences" :key="evidence.evidence_id" class="evidence-detail"><el-tag>{{ evidence.role }}</el-tag><p>{{ evidence.excerpt }}</p><pre>{{ JSON.stringify(evidence.locator, null, 2) }}</pre><img v-if="evidence.content_type === 'image'" :src="evidenceAsset(selected, evidence.evidence_id)" alt="证据图片缩略图" /></div>
        <h3>模型差异与缺失信息</h3>
        <div v-for="run in selected.runs" :key="run.id"><p>{{ run.run_type }}：{{ run.reason }}</p><ul><li v-for="difference in run.differences" :key="difference">差异：{{ difference }}</li><li v-for="missing in run.missing_information" :key="missing">缺失：{{ missing }}</li></ul></div>
        <h3>复核历史</h3><el-empty v-if="!selected.review_records.length" description="暂无人工复核" /><p v-for="record in selected.review_records" :key="record.id">{{ record.reviewer_name }}：{{ record.previous_conclusion }} → {{ record.new_conclusion }}；{{ record.comment }}</p>
      </template>
    </el-drawer>

    <el-dialog v-model="reviewVisible" title="人工复核" width="520px">
      <el-form v-if="selected" label-position="top"><el-form-item label="新结论"><el-select v-model="reviewForm.conclusion"><el-option v-for="value in ['PASS','FAIL','NEEDS_REVIEW','NOT_APPLICABLE','ERROR']" :key="value" :value="value" :disabled="value === selected.final_conclusion" /></el-select></el-form-item><el-form-item label="复核说明" :required="reviewCommentRequired"><el-input v-model="reviewForm.comment" type="textarea" :rows="4" maxlength="4000" show-word-limit /></el-form-item><el-alert type="warning" :closable="false" title="关键项任何改判，以及 FAIL/ERROR/NEEDS_REVIEW 改为 PASS 时必须填写说明。" /></el-form>
      <template #footer><el-button @click="reviewVisible = false">取消</el-button><el-button type="primary" :loading="reviewing" @click="submitReview">提交复核</el-button></template>
    </el-dialog>
  </section>
</template>
