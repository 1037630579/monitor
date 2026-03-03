<template>
  <el-row :gutter="16" class="summary-cards">
    <el-col :span="6">
      <el-card shadow="hover" class="card total">
        <div class="card-body">
          <el-icon :size="36"><Warning /></el-icon>
          <div class="card-info">
            <div class="card-value">{{ summary.total }}</div>
            <div class="card-label">巡检资源总数</div>
          </div>
        </div>
      </el-card>
    </el-col>
    <el-col :span="6">
      <el-card shadow="hover" class="card stopped">
        <div class="card-body">
          <el-icon :size="36"><CircleCloseFilled /></el-icon>
          <div class="card-info">
            <div class="card-value">{{ summary.by_status['stopped'] || 0 }}</div>
            <div class="card-label">已停止</div>
          </div>
        </div>
      </el-card>
    </el-col>
    <el-col :span="6">
      <el-card shadow="hover" class="card low-util">
        <div class="card-body">
          <el-icon :size="36"><Odometer /></el-icon>
          <div class="card-info">
            <div class="card-value">{{ summary.by_status['low_utilization'] || 0 }}</div>
            <div class="card-label">低利用率</div>
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
            <div class="card-label">最近扫描</div>
          </div>
        </div>
      </el-card>
    </el-col>
  </el-row>

  <el-row :gutter="16" style="margin-top: 12px;">
    <el-col :span="24">
      <el-card shadow="hover">
        <div class="dist-row">
          <span class="dist-label">资源类型分布：</span>
          <el-tag v-for="(count, rtype) in summary.by_resource_type" :key="rtype"
                  :type="resourceTagType(rtype as string)" effect="plain" style="margin-right: 8px;">
            {{ rtype }} {{ count }}
          </el-tag>
          <span v-if="Object.keys(summary.by_resource_type).length === 0" style="color: #999;">暂无数据</span>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import type { AwsSummary } from '../api'

defineProps<{ summary: AwsSummary }>()

function formatTime(t: string | null) {
  if (!t) return '-'
  const d = new Date(t)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function resourceTagType(rtype: string) {
  const map: Record<string, string> = {
    EC2: 'warning', ELB: '', RDS: 'danger', S3: 'success',
    EBS: 'info', VPC: '', Lambda: 'warning',
  }
  return map[rtype] || 'info'
}
</script>

<style scoped>
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
.card.stopped .el-icon { color: #f56c6c; }
.card.low-util .el-icon { color: #e6a23c; }
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
</style>
