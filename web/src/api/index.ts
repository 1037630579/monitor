import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// ── AWS 巡检 ──

export interface AwsResource {
  resource_type: string
  instance_id: string
  instance_name: string
  instance_type: string
  account: string
  status: string
  region: string
  availability_zone: string
  private_ip: string
  public_ip: string | null
  avg_cpu: number | null
  max_cpu: number | null
  avg_mem: number | null
  max_mem: number | null
  tags: Record<string, string>
  extra: Record<string, string>
  scan_time: string
}

export interface AwsPageResult {
  total: number
  items: AwsResource[]
  page: number
  page_size: number
}

export interface AwsSummary {
  total: number
  by_resource_type: Record<string, number>
  by_status: Record<string, number>
  by_region: Record<string, number>
  scan_time: string | null
}

export interface AwsFilterOptions {
  resource_types: string[]
  statuses: string[]
  regions: string[]
  accounts: string[]
}

export async function fetchAwsResources(params: Record<string, any>): Promise<AwsPageResult> {
  const { data } = await api.get('/aws-checks', { params })
  return data
}

export async function fetchAwsSummary(): Promise<AwsSummary> {
  const { data } = await api.get('/aws-checks/summary')
  return data
}

export async function fetchAwsFilterOptions(): Promise<AwsFilterOptions> {
  const { data } = await api.get('/aws-checks/filter-options')
  return data
}

// ── 华为云巡检 ──

export interface CheckItem {
  check_type: string
  risk_level: string
  resource_type: string
  resource_id: string
  resource_name: string
  region: string
  detail: string
  status: string
  extra?: Record<string, any>
  scan_time: string
}

export interface CheckPageResult {
  total: number
  items: CheckItem[]
  page: number
  page_size: number
}

export interface CheckSummary {
  total: number
  by_check_type: Record<string, number>
  by_risk_level: Record<string, number>
  by_resource_type: Record<string, number>
  check_type_names: Record<string, string>
  scan_time: string | null
}

export interface CheckFilterOptions {
  check_types: string[]
  risk_levels: string[]
  resource_types: string[]
  regions: string[]
  check_type_names: Record<string, string>
}

export async function fetchCheckResults(params: Record<string, any>): Promise<CheckPageResult> {
  const { data } = await api.get('/huawei-checks', { params })
  return data
}

export async function fetchCheckSummary(): Promise<CheckSummary> {
  const { data } = await api.get('/huawei-checks/summary')
  return data
}

export async function fetchCheckFilterOptions(): Promise<CheckFilterOptions> {
  const { data } = await api.get('/huawei-checks/filter-options')
  return data
}
