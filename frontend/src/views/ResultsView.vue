<script setup lang="ts">
import axios from 'axios'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'

import { getResults, retryErrors, type CheckResult, type Conclusion } from '../api/results'

const route = useRoute()
const taskId = computed(() => String(route.params.taskId))
const results = ref<CheckResult[]>([])
const taskStatus = ref('')
const loading = ref(true)
const retrying = ref(false)
const error = ref('')
let events: EventSource | null = null

const errorCount = computed(
  () => results.value.filter((item) => item.system_conclusion === 'ERROR').length,
)
const tagType: Record<Conclusion, 'success' | 'danger' | 'warning' | 'info'> = {
  PASS: 'success',
  FAIL: 'danger',
  NEEDS_REVIEW: 'warning',
  NOT_APPLICABLE: 'info',
  ERROR: 'danger',
}

function errorMessage(value: unknown): string {
  if (axios.isAxiosError(value) && typeof value.response?.data?.message === 'string') {
    return value.response.data.message
  }
  return '结果读取失败，请稍后重试。'
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const response = await getResults(taskId.value)
    results.value = response.items
    taskStatus.value = response.task_status
  } catch (reason) {
    error.value = errorMessage(reason)
  } finally {
    loading.value = false
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

onMounted(() => {
  void load()
  events = new EventSource(`/api/v1/tasks/${taskId.value}/events`)
  events.addEventListener('progress', () => void load())
  events.onerror = () => {
    events?.close()
    events = null
    void load()
  }
})
onBeforeUnmount(() => events?.close())
</script>

<template>
  <section class="checklist-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">阶段 3 · 系统核对</p>
        <h1>核对结果</h1>
        <p class="subtitle">任务 {{ taskId }} · 当前状态 {{ taskStatus || '读取中' }}</p>
      </div>
      <div class="result-actions">
        <el-button @click="load">刷新</el-button>
        <el-button v-if="errorCount" type="warning" :loading="retrying" @click="retry">
          重试 {{ errorCount }} 个错误项
        </el-button>
      </div>
    </header>
    <el-skeleton v-if="loading" :rows="6" animated />
    <el-alert v-else-if="error" type="error" :closable="false" show-icon :title="error" />
    <el-empty v-else-if="results.length === 0" description="暂无核对结果；可稍后刷新恢复状态" />
    <div v-else class="checklist-items">
      <el-card v-for="item in results" :key="item.id" shadow="never" class="check-item">
        <template #header>
          <div class="item-header">
            <div class="item-identity">
              <strong>{{ item.check_name }}</strong>
              <el-tag :type="tagType[item.system_conclusion]">{{ item.system_conclusion }}</el-tag>
              <el-tag v-if="item.severity === 'CRITICAL'" type="danger" effect="plain">关键</el-tag>
            </div>
            <span>{{ item.reason_code }}</span>
          </div>
        </template>
        <p class="result-reason">{{ item.reason }}</p>
        <el-collapse v-if="item.evidences.length">
          <el-collapse-item :title="`证据（${item.evidences.length}）`">
            <div v-for="evidence in item.evidences" :key="evidence.evidence_id" class="evidence-row">
              <el-tag size="small" effect="plain">{{ evidence.role }}</el-tag>
              <span>{{ evidence.excerpt }}</span>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-card>
    </div>
  </section>
</template>
