<script setup lang="ts">
import { DocumentChecked } from '@element-plus/icons-vue'
</script>

<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <div class="brand">
        <el-icon :size="24"><DocumentChecked /></el-icon>
        <span>说明书核对系统</span>
      </div>
      <el-tag type="warning" effect="plain">本地 MVP</el-tag>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>
