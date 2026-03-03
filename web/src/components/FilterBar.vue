<template>
  <el-card shadow="hover" style="margin-top: 16px; border-radius: 12px;">
    <el-form :inline="true" class="filter-form">
      <el-form-item label="资源类型">
        <el-select v-model="filters.resource_type" placeholder="全部" clearable style="width: 140px;" @change="emit('search')">
          <el-option v-for="rt in options.resource_types" :key="rt" :label="rt" :value="rt" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="filters.status" placeholder="全部" clearable style="width: 140px;" @change="emit('search')">
          <el-option v-for="s in options.statuses" :key="s" :label="statusLabel(s)" :value="s" />
        </el-select>
      </el-form-item>
      <el-form-item label="区域">
        <el-select v-model="filters.region" placeholder="全部" clearable filterable style="width: 180px;" @change="emit('search')">
          <el-option v-for="r in options.regions" :key="r" :label="r" :value="r" />
        </el-select>
      </el-form-item>
      <el-form-item label="账户">
        <el-select v-model="filters.account" placeholder="全部" clearable style="width: 140px;" @change="emit('search')">
          <el-option v-for="a in options.accounts" :key="a" :label="a" :value="a" />
        </el-select>
      </el-form-item>
      <el-form-item label="搜索">
        <el-input v-model="filters.keyword" placeholder="实例ID / 名称" clearable style="width: 200px;"
                  @keyup.enter="emit('search')" @clear="emit('search')">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="emit('search')">
          <el-icon><Search /></el-icon> 查询
        </el-button>
        <el-button @click="reset">重置</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup lang="ts">
import type { AwsFilterOptions } from '../api'

const props = defineProps<{ options: AwsFilterOptions }>()
const filters = defineModel<{
  resource_type: string
  status: string
  region: string
  account: string
  keyword: string
}>('filters', { required: true })

const emit = defineEmits<{ search: [] }>()

const STATUS_LABELS: Record<string, string> = {
  stopped: '已停止',
  low_utilization: '低利用率',
}

function statusLabel(s: string) {
  return STATUS_LABELS[s] || s
}

function reset() {
  filters.value = { resource_type: '', status: '', region: '', account: '', keyword: '' }
  emit('search')
}
</script>

<style scoped>
.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
}
</style>
