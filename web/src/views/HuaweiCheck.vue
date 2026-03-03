<template>
  <div class="huawei-check">
    <div class="header">
      <h1>华为云风险巡检</h1>
      <el-button type="primary" :icon="Refresh" :loading="loading" @click="loadAll">
        刷新
      </el-button>
    </div>

    <!-- 概览卡片 -->
    <el-row :gutter="16" class="summary-cards">
      <el-col :span="6">
        <el-card shadow="hover" class="card total">
          <div class="card-body">
            <el-icon :size="36"><Warning /></el-icon>
            <div class="card-info">
              <div class="card-value">{{ summary.total }}</div>
              <div class="card-label">风险项总数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="card high">
          <div class="card-body">
            <el-icon :size="36"><CircleCloseFilled /></el-icon>
            <div class="card-info">
              <div class="card-value">{{ summary.by_risk_level['high'] || 0 }}</div>
              <div class="card-label">高风险</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="card medium">
          <div class="card-body">
            <el-icon :size="36"><WarningFilled /></el-icon>
            <div class="card-info">
              <div class="card-value">{{ summary.by_risk_level['medium'] || 0 }}</div>
              <div class="card-label">中风险</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="card scan-time">
          <div class="card-body">
            <el-icon :size="36"><Timer /></el-icon>
            <div class="card-info">
              <div class="card-value scan-time-value">{{ formatTime(summary.scan_time) }}</div>
              <div class="card-label">最近巡检</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 资源类型分布 -->
    <el-row :gutter="16" style="margin-top: 12px;">
      <el-col :span="24">
        <el-card shadow="hover">
          <div class="dist-row">
            <span class="dist-label">资源类型：</span>
            <el-tag v-for="(count, rtype) in summary.by_resource_type" :key="rtype"
                    :type="resourceTagType(rtype as string)" effect="plain" style="margin-right: 8px;">
              {{ rtype }} {{ count }}
            </el-tag>
            <span v-if="Object.keys(summary.by_resource_type).length === 0" style="color: #999;">暂无数据</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 筛选栏 -->
    <el-card shadow="hover" style="margin-top: 16px; border-radius: 12px;">
      <el-form :inline="true" class="filter-form">
        <el-form-item label="巡检类型">
          <el-select v-model="filters.check_type" placeholder="全部" clearable style="width: 200px;" @change="onSearch">
            <el-option v-for="ct in filterOptions.check_types" :key="ct"
                       :label="filterOptions.check_type_names?.[ct] || ct" :value="ct" />
          </el-select>
        </el-form-item>
        <el-form-item label="资源类型">
          <el-select v-model="filters.resource_type" placeholder="全部" clearable style="width: 120px;" @change="onSearch">
            <el-option v-for="rt in filterOptions.resource_types" :key="rt" :label="rt" :value="rt" />
          </el-select>
        </el-form-item>
        <el-form-item label="风险级别">
          <el-select v-model="filters.risk_level" placeholder="全部" clearable style="width: 120px;" @change="onSearch">
            <el-option label="高" value="high" />
            <el-option label="中" value="medium" />
            <el-option label="低" value="low" />
          </el-select>
        </el-form-item>
        <el-form-item label="区域">
          <el-select v-model="filters.region" placeholder="全部" clearable filterable style="width: 160px;" @change="onSearch">
            <el-option v-for="r in filterOptions.regions" :key="r" :label="r" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item label="搜索">
          <el-input v-model="filters.keyword" placeholder="资源ID / 名称 / 详情" clearable style="width: 200px;"
                    @keyup.enter="onSearch" @clear="onSearch">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="onSearch">
            <el-icon><Search /></el-icon> 查询
          </el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 巡检结果表格 -->
    <el-card shadow="hover" style="margin-top: 16px; border-radius: 12px;">
      <el-table :data="tableData.items" stripe border style="width: 100%;"
                v-loading="loading" empty-text="暂无巡检数据"
                :default-sort="{ prop: 'risk_level', order: 'ascending' }">
        <el-table-column prop="check_type" label="巡检类型" width="180" sortable>
          <template #default="{ row }">
            {{ checkTypeName(row.check_type) }}
          </template>
        </el-table-column>
        <el-table-column prop="resource_type" label="资源类型" width="90" sortable>
          <template #default="{ row }">
            <el-tag :type="resourceTagType(row.resource_type)" size="small" effect="plain">
              {{ row.resource_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="risk_level" label="风险" width="80" sortable>
          <template #default="{ row }">
            <el-tag :type="riskTagType(row.risk_level)" size="small">
              {{ riskLabel(row.risk_level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="resource_id" label="资源ID" width="220" show-overflow-tooltip />
        <el-table-column prop="resource_name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="region" label="区域" width="130" sortable />
        <el-table-column prop="detail" label="详情" min-width="300" show-overflow-tooltip />
        <el-table-column prop="scan_time" label="扫描时间" width="170" sortable>
          <template #default="{ row }">{{ formatTime(row.scan_time) }}</template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="tableData.total"
          :page-sizes="[20, 50, 100, 200]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadResults"
          @size-change="loadResults"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import {
  fetchCheckResults,
  fetchCheckSummary,
  fetchCheckFilterOptions,
  type CheckSummary,
  type CheckPageResult,
  type CheckFilterOptions,
} from '../api'

const loading = ref(false)
const page = ref(1)
const pageSize = ref(50)

const summary = ref<CheckSummary>({
  total: 0, by_check_type: {}, by_risk_level: {},
  by_resource_type: {}, check_type_names: {}, scan_time: null,
})

const filterOptions = ref<CheckFilterOptions>({
  check_types: [], risk_levels: [], resource_types: [],
  regions: [], check_type_names: {},
})

const filters = reactive({
  check_type: '', resource_type: '', risk_level: '', region: '', keyword: '',
})

const tableData = ref<CheckPageResult>({
  total: 0, items: [], page: 1, page_size: 50,
})

const CHECK_TYPE_NAMES: Record<string, string> = {
  ecs_security_group: 'ECS安全组规则',
  cce_workload_replica: 'CCE工作负载副本数',
  rds_ha: 'RDS高可用部署',
  dms_rabbitmq_cluster: 'DMS RabbitMQ集群',
  rds_network_type: 'RDS网络类型',
  dds_network_type: 'DDS网络类型',
  rds_params_double_one: 'RDS参数配置(双1)',
  cce_node_pods: 'CCE节点Pod数量',
  ecs_idle: 'ECS闲置检查',
}

function checkTypeName(ct: string) {
  return filterOptions.value.check_type_names?.[ct] || CHECK_TYPE_NAMES[ct] || ct
}

function riskTagType(level: string) {
  if (level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'info'
}

function riskLabel(level: string) {
  if (level === 'high') return '高'
  if (level === 'medium') return '中'
  if (level === 'low') return '低'
  return level
}

function resourceTagType(rt: string) {
  const map: Record<string, string> = { ECS: 'danger', CCE: '', RDS: 'warning', DDS: 'success', DMS: 'info' }
  return map[rt] || 'info'
}

function formatTime(t: string | null) {
  if (!t) return '-'
  const d = new Date(t)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function loadResults() {
  loading.value = true
  try {
    tableData.value = await fetchCheckResults({
      check_type: filters.check_type,
      resource_type: filters.resource_type,
      risk_level: filters.risk_level,
      region: filters.region,
      keyword: filters.keyword,
      page: page.value,
      page_size: pageSize.value,
    })
  } catch (e) {
    console.error('Failed to load check results', e)
  } finally {
    loading.value = false
  }
}

async function loadAll() {
  loading.value = true
  try {
    const [s, f] = await Promise.all([fetchCheckSummary(), fetchCheckFilterOptions()])
    summary.value = s
    filterOptions.value = f
    await loadResults()
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

function resetFilters() {
  filters.check_type = ''
  filters.resource_type = ''
  filters.risk_level = ''
  filters.region = ''
  filters.keyword = ''
  onSearch()
}

onMounted(loadAll)
</script>

<style scoped>
.huawei-check {
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
.summary-cards .card {
  border-radius: 12px;
}
.card-body {
  display: flex;
  align-items: center;
  gap: 16px;
}
.card-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}
.scan-time-value {
  font-size: 16px;
}
.card-label {
  font-size: 13px;
  color: #909399;
  margin-top: 2px;
}
.card.total .el-icon { color: #409eff; }
.card.high .el-icon { color: #f56c6c; }
.card.medium .el-icon { color: #e6a23c; }
.card.scan-time .el-icon { color: #67c23a; }

.dist-row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.dist-label {
  font-size: 14px;
  color: #606266;
  margin-right: 8px;
}
.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
}
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
