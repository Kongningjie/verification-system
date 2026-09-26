<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { CircleCheck, Warning } from '@element-plus/icons-vue'

import { getHealth, type HealthResponse } from '../api/health'

const health = ref<HealthResponse | null>(null)
const error = ref('')

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
      <p class="eyebrow">阶段 A · 工程骨架</p>
      <h1>核对流程的本地运行底座已就绪</h1>
      <p class="subtitle">
        当前包含前后端启动链路、SQLite 迁移、环境配置和健康检查。文件解析、核对清单和模型运行将在后续阶段实现。
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
          <div><strong>业务能力待实现</strong><span>解析、清单、证据、核对、报告</span></div>
        </div>
      </div>
    </el-card>
  </section>
</template>
