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
      <p class="eyebrow">阶段 2 · 核对清单</p>
      <h1>动态核对清单已可生成与确认</h1>
      <p class="subtitle">
        上传材料经解析后，系统会合并通用规则与模板批注要求。你可以逐项编辑、停用、调整等级，再冻结为不可变版本。
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
          <div><strong>后续阶段</strong><span>证据匹配、正式核对、复核与报告</span></div>
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
