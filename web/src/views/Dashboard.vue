<template>
  <div class="dashboard">
    <div class="header">
      <h1>AWS 巡检</h1>
      <el-button type="primary" :icon="Refresh" :loading="loading" @click="loadAll">
        刷新
      </el-button>
    </div>

    <SummaryCards :summary="summary" />
    <FilterBar v-model:filters="filters" :options="filterOptions" @search="onSearch" />
    <ResourceTable
      :data="tableData"
      :loading="loading"
      v-model:page="page"
      v-model:page-size="pageSize"
      @page-change="loadResources"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import {
  fetchAwsResources,
  fetchAwsSummary,
  fetchAwsFilterOptions,
  type AwsSummary,
  type AwsPageResult,
  type AwsFilterOptions,
} from '../api'
import SummaryCards from '../components/SummaryCards.vue'
import FilterBar from '../components/FilterBar.vue'
import ResourceTable from '../components/ResourceTable.vue'

const loading = ref(false)
const page = ref(1)
const pageSize = ref(50)

const summary = ref<AwsSummary>({
  total: 0, by_resource_type: {}, by_status: {}, by_region: {}, scan_time: null,
})

const filterOptions = ref<AwsFilterOptions>({
  resource_types: [], statuses: [], regions: [], accounts: [],
})

const filters = reactive({
  resource_type: '', status: '', region: '', account: '', keyword: '',
})

const tableData = ref<AwsPageResult>({
  total: 0, items: [], page: 1, page_size: 50,
})

async function loadResources() {
  loading.value = true
  try {
    tableData.value = await fetchAwsResources({
      resource_type: filters.resource_type,
      status: filters.status,
      region: filters.region,
      account: filters.account,
      keyword: filters.keyword,
      page: page.value,
      page_size: pageSize.value,
    })
  } catch (e) {
    console.error('Failed to load resources', e)
  } finally {
    loading.value = false
  }
}

async function loadAll() {
  loading.value = true
  try {
    const [s, f] = await Promise.all([fetchAwsSummary(), fetchAwsFilterOptions()])
    summary.value = s
    filterOptions.value = f
    await loadResources()
  } catch (e) {
    console.error('Failed to load data', e)
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  loadAll()
}

onMounted(loadAll)
</script>

<style scoped>
.dashboard {
  max-width: 1600px;
  margin: 0 auto;
  padding: 24px;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.header h1 {
  font-size: 22px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}
</style>
