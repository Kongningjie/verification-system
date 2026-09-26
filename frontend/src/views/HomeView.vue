<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CircleCheck, Warning } from '@element-plus/icons-vue'

import { getHealth, type HealthResponse } from '../api/health'

const health = ref<HealthResponse | null>(null)
const error = ref('')
const taskId = ref('')
const router = useRouter()

function openChecklist(): void {
  const value = taskId.value.trim()
  if (value) void router.push({ name: 'checklist', params: { taskId: value } })
}

onMounted(async () => {
  try {
    health.value = await getHealth()
  } catch {
    error.value = '后端尚未启动，请先按 README 启动 FastAPI。'
  }
})
</script>

<template>
  <section class="home">
    <el-card class="hero" shadow="never">
      <p class="eyebrow">阶段 3 · 证据核对</p>
      <h1>从动态清单到可追溯结论</h1>
      <p class="subtitle">
        确认清单后，系统会匹配材料内证据，依次执行确定性规则与受白名单约束的文本或视觉判断，并保留独立复核运行记录。
      </p>

      <el-alert v-if="health" type="success" :closable="false" show-icon>
        <template #title>
          后端连接正常 · {{ health.service }} v{{ health.version }}
        </template>
      </el-alert>
      <el-alert v-else-if="error" type="warning" :closable="false" show-icon :title="error" />

      <div class="milestones">
        <div class="milestone done">
          <el-icon><CircleCheck /></el-icon>
          <div><strong>基础工程</strong><span>FastAPI、Vue、SQLite、Alembic</span></div>
        </div>
        <div class="milestone pending">
          <el-icon><Warning /></el-icon>
          <div><strong>后续阶段</strong><span>人工复核、Excel/JSON 报告与验收评估</span></div>
        </div>
      </div>

      <div class="task-entry">
        <el-input
          v-model="taskId"
          placeholder="输入任务 ID，打开核对清单"
          clearable
          @keyup.enter="openChecklist"
        />
        <el-button type="primary" :disabled="!taskId.trim()" @click="openChecklist">
          打开清单
        </el-button>
      </div>
    </el-card>
  </section>
</template>
