<template>
  <el-card shadow="hover" style="margin-top: 16px; border-radius: 12px;">
    <el-table :data="data.items" stripe border style="width: 100%;"
              v-loading="loading" empty-text="暂无数据"
              :default-sort="{ prop: 'avg_cpu', order: 'ascending' }">
      <el-table-column prop="resource_type" label="资源类型" width="100" sortable>
        <template #default="{ row }">
          <el-tag :type="resourceTagType(row.resource_type)" size="small" effect="plain">
            {{ row.resource_type || 'EC2' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="instance_id" label="实例ID" width="200" show-overflow-tooltip />
      <el-table-column prop="instance_name" label="名称" min-width="160" show-overflow-tooltip />
      <el-table-column prop="instance_type" label="规格" width="130" sortable />
      <el-table-column prop="region" label="区域" width="140" sortable />
      <el-table-column prop="status" label="状态" width="110" sortable>
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="private_ip" label="私有IP" width="135" />
      <el-table-column prop="avg_cpu" label="平均CPU" width="95" sortable>
        <template #default="{ row }">
          <span :class="pctClass(row.avg_cpu)">{{ fmtPct(row.avg_cpu) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="max_cpu" label="最高CPU" width="95" sortable>
        <template #default="{ row }">{{ fmtPct(row.max_cpu) }}</template>
      </el-table-column>
      <el-table-column prop="avg_mem" label="平均内存" width="95" sortable>
        <template #default="{ row }">
          <span :class="pctClass(row.avg_mem)">{{ fmtPct(row.avg_mem) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="max_mem" label="最高内存" width="95" sortable>
        <template #default="{ row }">{{ fmtPct(row.max_mem) }}</template>
      </el-table-column>
      <el-table-column label="标签" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <template v-if="row.tags && Object.keys(row.tags).length">
            <el-tag v-for="(v, k) in row.tags" :key="k" size="small" type="info"
                    style="margin: 1px 2px;" effect="plain">
              {{ k }}={{ v }}
            </el-tag>
          </template>
          <span v-else style="color: #ccc;">-</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="data.total"
        :page-sizes="[20, 50, 100, 200]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="emit('pageChange')"
        @size-change="emit('pageChange')"
      />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import type { AwsPageResult } from '../api'

defineProps<{ data: AwsPageResult; loading: boolean }>()
const page = defineModel<number>('page', { required: true })
const pageSize = defineModel<number>('pageSize', { required: true })
const emit = defineEmits<{ pageChange: [] }>()

function parsePct(v: unknown): number | null {
  if (v === null || v === undefined) return null
  if (typeof v === 'number') return v
  if (typeof v === 'string') {
    const n = parseFloat(v.replace('%', ''))
    return isNaN(n) ? null : n
  }
  return null
}

function fmtPct(v: unknown) {
  const n = parsePct(v)
  if (n === null) return '-'
  return `${n.toFixed(1)}%`
}

function pctClass(v: unknown) {
  const n = parsePct(v)
  if (n === null) return ''
  if (n < 5) return 'pct-danger'
  if (n < 10) return 'pct-warning'
  return ''
}

function resourceTagType(rt: string) {
  const map: Record<string, string> = {
    EC2: 'warning', ELB: '', RDS: 'danger', S3: 'success',
    EBS: 'info', VPC: '', Lambda: 'warning',
  }
  return map[rt] || 'info'
}

const STATUS_LABELS: Record<string, string> = {
  stopped: '已停止',
  low_utilization: '低利用率',
}

function statusLabel(s: string) {
  return STATUS_LABELS[s] || s
}

function statusTagType(s: string) {
  if (s === 'stopped') return 'danger'
  if (s === 'low_utilization') return 'warning'
  return 'info'
}
</script>

<style scoped>
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
.pct-danger { color: #f56c6c; font-weight: 600; }
.pct-warning { color: #e6a23c; font-weight: 600; }
</style>
