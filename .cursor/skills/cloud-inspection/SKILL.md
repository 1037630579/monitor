---
name: cloud-inspection
description: AWS EC2 闲置实例检测与华为云风险巡检。用于执行巡检扫描、解读报告、调整参数、查看巡检结果时参考。
---

# 云巡检运维手册

## 1. AWS EC2 巡检

### 检测规则

| 类别 | 判定规则 | 风险 |
|------|---------|------|
| 已停止实例 | `state == "stopped"` | EBS 卷持续计费、弹性 IP 空置 |
| 低利用率实例 | CPU avg < 阈值 **或** 内存 avg < 阈值 | 资源浪费、可降配 |

### 检测指标

| 指标 | Namespace | MetricName | Period | Statistics |
|------|-----------|------------|--------|-----------|
| CPU | `AWS/EC2` | `CPUUtilization` | 300s (5分钟) | Average + Maximum |
| 内存 | `CWAgent` | `mem_used_percent` | 300s (5分钟) | Average + Maximum |

- `max_cpu` / `max_mem` 取 Maximum 统计量的最大值，是检测窗口内的真正峰值
- 未装 CloudWatch Agent 的实例仅检测 CPU

### 配置

```yaml
ec2_check:
  cpu_threshold: 10.0   # CPU 阈值 %
  mem_threshold: 10.0   # 内存阈值 %
  hours: 360            # 窗口（360 = 15天）
  max_workers: 20       # 并发线程
```

### 运行

```bash
python main.py --ec2                          # 默认参数
python main.py --ec2 --cpu 5 --mem 5 --hours 720   # 覆盖参数
```

## 2. 华为云巡检（9 项）

| 序号 | check_type | 资源 | 检查内容 |
|------|-----------|------|---------|
| 1 | ecs_security_group | ECS | 安全组规则（未设置/过于宽松） |
| 2 | cce_workload_replica | CCE | 工作负载可用副本数不足 |
| 3 | rds_ha | RDS | 实例是否单副本（非高可用） |
| 4 | dms_rabbitmq_cluster | DMS | RabbitMQ 是否集群部署 |
| 5 | rds_network_type | RDS | 网络是否通用型 |
| 6 | dds_network_type | DDS | 网络是否通用型 |
| 7 | rds_params_double_one | RDS | 参数配置双1检查 |
| 8 | cce_node_pods | CCE | 节点 pod 数量过多 |
| 9 | ecs_idle | ECS | CPU 利用率过低 |

### 运行

```bash
python main.py --huawei-check                             # 全部 9 项
python main.py --huawei-check --checks rds_ha,ecs_idle    # 指定项
```

## 3. 数据存储（MySQL 8.0）

```yaml
mysql:
  enabled: true
  host: "127.0.0.1"
  port: 3306
  user: "root"
  password: "lilihang@1219"
  db_name: "cloud_monitor"
```

| 表 | 存储内容 |
|----|---------|
| idle_resources | AWS EC2 巡检结果 |
| huawei_checks | 华为云 9 项巡检结果 |

数据库层用 pymysql 短连接，`save_*` 按 cloud+account 或 check_type 先删后插。

## 4. Web 服务

```bash
python main.py --server --port 8080
```

### API 端点

| 端点 | 说明 |
|------|------|
| `/api/aws-checks` | AWS 巡检列表（分页/筛选） |
| `/api/aws-checks/summary` | AWS 巡检汇总统计 |
| `/api/aws-checks/filter-options` | AWS 筛选项 |
| `/api/huawei-checks` | 华为云巡检列表 |
| `/api/huawei-checks/summary` | 华为云巡检汇总 |
| `/api/huawei-checks/filter-options` | 华为云筛选项 |

前端：Vue 3 + Element Plus，两个标签页（AWS 巡检 / 华为云巡检）。

## 5. 文件职责

| 文件 | 职责 |
|------|------|
| `config.yaml` | 配置（AWS/华为云/MySQL/Webhook/EC2阈值） |
| `cloud_monitor/config.py` | 配置数据类 |
| `cloud_monitor/tools/aws.py` | EC2 检测逻辑 |
| `cloud_monitor/tools/huawei_check.py` | 华为云 9 项巡检 |
| `cloud_monitor/db.py` | MySQL 存储层 |
| `cloud_monitor/server.py` | FastAPI 服务 + 前端托管 |
| `cloud_monitor/agent.py` | Claude Agent 工具注册 |
| `main.py` | CLI 入口 |

## 6. EC2 治理建议

### 已停止实例

| 停止时长 | 操作 |
|---------|------|
| > 30 天 | 评估释放，先创建 AMI |
| 有 EBS | 释放前检查数据 |
| 有弹性 IP | 同步释放（空置 $3.65/月） |

### 低利用率实例

| CPU | 建议 |
|:---:|------|
| < 5% | 强烈建议降配或合并 |
| 5%-10% | 评估降配一级 |
| 10%-20% | 持续观察 |
