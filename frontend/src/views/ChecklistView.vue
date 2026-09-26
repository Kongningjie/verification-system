<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  confirmChecklist,
  getChecklist,
  updateCheckItem,
  type CheckItem,
  type CheckType,
  type ChecklistResponse,
  type Severity,
  type SourceCategory,
} from '../api/checklists'

const route = useRoute()
const taskId = computed(() => String(route.params.taskId))
const checklist = ref<ChecklistResponse | null>(null)
const loading = ref(true)
const confirming = ref(false)
const savingIds = ref(new Set<string>())
const error = ref('')

const checkTypes: Array<{ label: string; value: CheckType }> = [
  { label: '字段一致性', value: 'FIELD' },
  { label: '语义核对', value: 'SEMANTIC' },
  { label: '图片核对', value: 'VISUAL' },
  { label: '结构核对', value: 'STRUCTURE' },
  { label: '模板语义核对', value: 'CUSTOM_SEMANTIC' },
  { label: '模板图片核对', value: 'CUSTOM_VISUAL' },
  { label: '模板结构核对', value: 'CUSTOM_STRUCTURE' },
]
const severities: Array<{ label: string; value: Severity }> = [
  { label: '关键', value: 'CRITICAL' },
  { label: '普通', value: 'NORMAL' },
]
const sourceOptions: Array<{ label: string; value: SourceCategory }> = [
  { label: '说明书', value: 'MANUAL' },
  { label: '项目 JSON', value: 'PROJECT' },
  { label: '依据 PDF', value: 'EVIDENCE_PDF' },
  { label: '依据图片', value: 'EVIDENCE_IMAGE' },
]

const editable = computed(
  () => checklist.value?.task_status === 'AWAITING_CHECKLIST_CONFIRMATION',
)
const enabledCount = computed(
  () => checklist.value?.items.filter((item) => item.enabled).length ?? 0,
)

function errorMessage(value: unknown): string {
  if (axios.isAxiosError(value)) {
    const message = value.response?.data?.message
    if (typeof message === 'string') return message
  }
  return '操作失败，请刷新后重试。'
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    checklist.value = await getChecklist(taskId.value)
  } catch (reason) {
    error.value = errorMessage(reason)
  } finally {
    loading.value = false
  }
}

async function save(item: CheckItem, notify = true): Promise<boolean> {
  if (!editable.value || savingIds.value.has(item.id)) return false
  const next = new Set(savingIds.value)
  next.add(item.id)
  savingIds.value = next
  try {
    const updated = await updateCheckItem(taskId.value, item, {
      name: item.name,
      requirement: item.requirement,
      check_type: item.check_type,
      severity: item.severity,
      required_source_categories: item.required_source_categories,
      target_hint: item.target_hint,
      enabled: item.enabled,
    })
    Object.assign(item, updated)
    if (checklist.value) checklist.value.checklist_revision += 1
    if (notify) ElMessage.success('核对项已保存')
    return true
  } catch (reason) {
    ElMessage.error(errorMessage(reason))
    await load()
    return false
  } finally {
    const remaining = new Set(savingIds.value)
    remaining.delete(item.id)
    savingIds.value = remaining
  }
}

async function confirmAll(): Promise<void> {
  if (!checklist.value || !editable.value) return
  try {
    await ElMessageBox.confirm(
      `将确认 ${enabledCount.value} 个已启用核对项。确认后清单不可修改，是否继续？`,
      '确认核对清单',
      { type: 'warning', confirmButtonText: '确认并进入队列', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  confirming.value = true
  try {
    for (const item of checklist.value.items) {
      if (!(await save(item, false))) return
    }
    const version = await confirmChecklist(taskId.value, checklist.value.checklist_revision)
    ElMessage.success(`清单版本 v${version.version_number} 已冻结`)
    await load()
  } catch (reason) {
    ElMessage.error(errorMessage(reason))
    await load()
  } finally {
    confirming.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="checklist-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">阶段 2 · 清单确认</p>
        <h1>核对清单</h1>
        <p class="subtitle">任务 {{ taskId }} · 已启用 {{ enabledCount }} 项</p>
      </div>
      <el-button @click="load">刷新</el-button>
    </header>

    <el-skeleton v-if="loading" :rows="8" animated />
    <el-alert
      v-else-if="error"
      type="error"
      show-icon
      :closable="false"
      :title="error"
    >
      <template #default><el-button size="small" @click="load">重试</el-button></template>
    </el-alert>
    <el-empty v-else-if="!checklist || checklist.items.length === 0" description="暂无核对项" />

    <template v-else>
      <el-alert
        v-if="!editable"
        type="success"
        :closable="false"
        show-icon
        :title="`清单已确认，当前任务状态：${checklist.task_status}`"
      />
      <div class="checklist-items">
        <el-card
          v-for="(item, index) in checklist.items"
          :key="item.id"
          class="check-item"
          shadow="never"
          :class="{ disabled: !item.enabled }"
        >
          <template #header>
            <div class="item-header">
              <div class="item-identity">
                <strong>#{{ index + 1 }} {{ item.name }}</strong>
                <el-tag size="small" effect="plain">
                  {{ item.source_type === 'COMMON_RULE' ? '通用规则' : '模板批注' }}
                </el-tag>
                <el-tag v-if="item.severity === 'CRITICAL'" size="small" type="danger">关键</el-tag>
              </div>
              <el-switch
                v-model="item.enabled"
                :disabled="!editable"
                active-text="启用"
                inactive-text="停用"
              />
            </div>
          </template>

          <el-row :gutter="20">
            <el-col :xs="24" :lg="9">
              <div class="source-panel">
                <h3>来源</h3>
                <template v-if="item.source_type === 'TEMPLATE_COMMENT'">
                  <p><span>批注：</span>{{ item.source_comment_text || '（空批注）' }}</p>
                  <p><span>圈选：</span>{{ item.source_selected_text || '（未圈选文本）' }}</p>
                  <p><span>位置：</span>{{ item.source_heading_path.join(' / ') || '未识别标题' }}</p>
                </template>
                <template v-else>
                  <p><span>规则：</span>{{ item.rule_id }} @ {{ item.rule_version }}</p>
                </template>
                <div v-if="item.generation_warnings.length" class="warnings">
                  <el-tag
                    v-for="warning in item.generation_warnings"
                    :key="warning"
                    type="warning"
                    size="small"
                  >
                    {{ warning }}
                  </el-tag>
                </div>
              </div>
            </el-col>
            <el-col :xs="24" :lg="15">
              <el-form label-position="top">
                <el-form-item label="名称">
                  <el-input v-model="item.name" :disabled="!editable" maxlength="255" />
                </el-form-item>
                <el-form-item label="核对要求">
                  <el-input
                    v-model="item.requirement"
                    type="textarea"
                    :rows="3"
                    :disabled="!editable"
                    maxlength="4000"
                    show-word-limit
                  />
                </el-form-item>
                <el-row :gutter="16">
                  <el-col :xs="24" :sm="12">
                    <el-form-item label="核对类型">
                      <el-select v-model="item.check_type" :disabled="!editable">
                        <el-option
                          v-for="option in checkTypes"
                          :key="option.value"
                          :label="option.label"
                          :value="option.value"
                        />
                      </el-select>
                    </el-form-item>
                  </el-col>
                  <el-col :xs="24" :sm="12">
                    <el-form-item label="严重等级">
                      <el-select v-model="item.severity" :disabled="!editable">
                        <el-option
                          v-for="option in severities"
                          :key="option.value"
                          :label="option.label"
                          :value="option.value"
                        />
                      </el-select>
                    </el-form-item>
                  </el-col>
                </el-row>
                <el-form-item label="所需依据">
                  <el-checkbox-group
                    v-model="item.required_source_categories"
                    :disabled="!editable"
                  >
                    <el-checkbox
                      v-for="option in sourceOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item label="目标提示">
                  <el-input v-model="item.target_hint" :disabled="!editable" maxlength="1000" />
                </el-form-item>
                <el-button
                  v-if="editable"
                  type="primary"
                  :loading="savingIds.has(item.id)"
                  @click="save(item)"
                >
                  保存此项
                </el-button>
              </el-form>
            </el-col>
          </el-row>
        </el-card>
      </div>

      <div v-if="editable" class="confirm-bar">
        <span>确认会创建不可变快照，后续阶段只使用该版本。</span>
        <el-button
          type="danger"
          size="large"
          :disabled="enabledCount === 0"
          :loading="confirming"
          @click="confirmAll"
        >
          确认全部清单
        </el-button>
      </div>
    </template>
  </section>
</template>
