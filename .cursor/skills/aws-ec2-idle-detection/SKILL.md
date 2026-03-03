---
name: aws-ec2-idle-detection
description: AWS EC2 闲置实例检测与治理。用于执行 EC2 闲置扫描、解读检测报告、调整检测参数时参考。
---

# AWS EC2 闲置实例检测 — 运维手册

## 1. 功能概述

对多个 AWS 账户、多区域的 EC2 实例进行闲置检测，识别两类需关注的资源：

| 资源类别 | 判定规则 | 风险说明 |
|---------|---------|---------|
| 已停止实例 | `state == "stopped"` | EBS 卷持续计费、弹性 IP 空置计费 |
| 低利用率实例 | CPU 平均 < 阈值 **或** 内存平均 < 阈值（检测窗口内） | 资源浪费、存在降配空间 |

### 检测指标

| 指标 | CloudWatch Namespace | MetricName | 采集方式 |
|------|---------------------|------------|---------|
| CPU 利用率 | `AWS/EC2` | `CPUUtilization` | 默认启用 |
| 内存利用率 | `CWAgent` | `mem_used_percent` | 需安装 [CloudWatch Agent](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Install-CloudWatch-Agent.html) |

> 未安装 CloudWatch Agent 的实例不会产生内存告警，仅检测 CPU。

## 2. 配置参数

所有检测参数集中在 `config.yaml` 的 `ec2_check` 段：

```yaml
ec2_check:
  cpu_threshold: 10.0       # CPU 利用率阈值（%），低于此值标记为闲置
  mem_threshold: 10.0       # 内存利用率阈值（%），低于此值标记为闲置
  hours: 360                # 检测时间窗口（小时），360 = 15天
  max_workers: 20           # CloudWatch API 并发查询线程数
```

### 参数调优建议

| 场景 | cpu_threshold | mem_threshold | hours | 说明 |
|------|:------------:|:------------:|:-----:|------|
| 保守筛查 | 5.0 | 5.0 | 720 | 30天内持续极低利用率 |
| 标准治理（默认） | 10.0 | 10.0 | 360 | 15天内平均低于10% |
| 激进优化 | 20.0 | 20.0 | 168 | 7天内平均低于20% |

### 并发线程数

`max_workers` 控制同时向 CloudWatch 发起的 API 请求数。实测参考：

| 运行实例数 | 推荐 max_workers | 预计耗时 |
|:---------:|:---------------:|:-------:|
| < 100 | 10 | < 30s |
| 100 - 500 | 20 | 60-90s |
| > 500 | 30-50 | 视网络情况 |

> 设置过高可能触发 CloudWatch API 限流（ThrottlingException），建议不超过 50。

## 3. 运行方式

### 方式一：CLI 直接执行（推荐日常巡检）

无需 Claude API，直接调用 AWS SDK 扫描并输出报告。

```bash
# 使用 config.yaml 默认参数
python main.py --ec2

# 覆盖部分参数
python main.py --ec2 --cpu 5 --mem 5 --hours 720

# 仅查看帮助
python main.py --help
```

命令行参数优先级：`--cpu/--mem/--hours` > `config.yaml` > 代码默认值

### 方式二：Claude Agent 对话查询

需要 Claude API Key，支持自然语言交互。

```bash
# 自动调用 aws_ec2 工具
python main.py -q "查询 AWS EC2 闲置实例"

# 交互模式
python main.py
> 查一下 AWS 有哪些闲置的 EC2
```

Agent 调用 `aws_ec2` 时不传参数，默认值从 `config.yaml` 加载。

## 4. 报告输出格式

### 4.1 报告结构

```
📊 EC2 实例报告 [区域: us-east-2, us-west-2, ap-southeast-1]
  总计: 355 个实例 | 运行中: 335 | 已停止: 20
  检测条件: CPU < 10% 或 内存 < 10% (最近15天)
  us-east-2: 5 个 (运行: 5, 停止: 0)
  us-west-2: 300 个 (运行: 282, 停止: 18)
  ap-southeast-1: 50 个 (运行: 48, 停止: 2)

  已停止实例: 20 个
  低利用率实例: 244 个

🔴 已停止的实例 (20 个):
[AWS] i-0bba0adb469b06d9b
  名称: etcd_1806
  类型: c5.large
  状态: 🔴 已停止
  区域: us-west-2
  可用区: us-west-2c
  私有IP: 10.76.9.159
  公网IP: 无
  最后启动: 2025-09-25 03:12
  距今: 152天
  停止原因: User initiated (2025-09-25 09:42:20 GMT)
  EBS卷: vol-0abc123def456
  EBS卷数: 1
  安全组: k8s-sg(sg-0123456)
  标签: Project=k8s, Env=dev

⚠️ 低利用率实例 (244 个):
| 实例ID | 名称 | 类型 | 区域 | 私有IP | 平均CPU | 最高CPU | 平均内存 | 最高内存 | 标签 |
|--------|------|------|------|--------|---------|---------|----------|----------|------|
| i-0f41cbc41707f213f | us01-intl-k8s-0006 | m5.2xlarge | us-west-2 | 10.76.46.132 | 5.0% | 6.3% | - | - | Project=GPT |
| i-0a1b2c3d4e5f67890 | api-server-prod | t3.xlarge | us-west-2 | 10.76.12.55 | 3.2% | 8.7% | 8.1% | 12.4% | Env=prod |
```

### 4.2 输出格式规则

| 实例类别 | 输出格式 | 原因 |
|---------|---------|------|
| 已停止实例 | 多行详情 | 数量少（通常 < 30），需展示完整信息辅助决策 |
| 低利用率实例 | 紧凑 Markdown 表格（含平均/最高 CPU 和内存） | 数量多（可达数百），表格一目了然且节省上下文 |

## 5. 技术架构

### 5.1 核心函数调用链

```
list_ec2_aws()                    ← 统一入口，缓存层
  ├─ _ec2_scan_cache (命中?)      ← key: account|region|cpu|mem|hours
  │   ├─ 命中 → 直接返回
  │   └─ 未命中 ↓
  └─ _run_ec2_scan()              ← 完整扫描
      ├─ EC2 describe_instances   ← 收集全量实例（Paginator）
      │   ├─ stopped → stopped_details[]
      │   └─ running → running_instances[]
      └─ ThreadPoolExecutor       ← 并发查 CloudWatch
          └─ _check_instance_utilization()  ← 单实例 CPU + 内存
              ├─ AWS/EC2 CPUUtilization
              └─ CWAgent mem_used_percent
```

### 5.2 缓存机制

- **缓存 Key**：`account_name|region|cpu_threshold|mem_threshold|hours`
- **缓存 Value**：`(header_text, stopped_details, low_util_rows)`
- **生命周期**：进程级内存缓存，进程退出自动清除
- **手动清除**：调用 `ec2_clear_cache()`

首次调用执行完整 CloudWatch 扫描（~60-90s），后续同参数调用瞬间返回。

### 5.3 文件职责

| 文件 | 职责 |
|------|------|
| `config.yaml` | 检测参数定义 |
| `cloud_monitor/config.py` | `EC2CheckConfig` 数据类，解析 yaml |
| `cloud_monitor/tools/aws.py` | 检测逻辑实现（`list_ec2_aws`, `_run_ec2_scan`, `_check_instance_utilization`） |
| `cloud_monitor/agent.py` | Claude Agent 工具注册（`aws_ec2`），默认值注入 |
| `main.py` | CLI 入口（`--ec2` 直接执行 / `-q` Agent 查询） |

## 6. 前置条件与依赖

### AWS 权限要求

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*"
    }
  ]
}
```

### 内存监控（可选）

如需检测内存利用率，目标实例需安装 CloudWatch Agent 并配置 `mem_used_percent` 指标上报。未安装的实例仅检测 CPU，不会产生错误。

### Python 依赖

```
boto3          # AWS SDK
rich           # 终端格式化输出
pyyaml         # 配置文件解析
```

## 7. 治理建议

### 已停止实例

| 检查项 | 操作 |
|-------|------|
| 停止超过 30 天 | 评估是否可释放，先创建 AMI 快照 |
| 有关联 EBS 卷 | 释放前检查是否有重要数据 |
| 有弹性 IP | 释放实例后同步释放 EIP（空置 $3.65/月） |

### 低利用率实例

| CPU 利用率 | 建议 |
|:---------:|------|
| < 5% | 强烈建议降配或合并工作负载 |
| 5% - 10% | 评估是否可降配一个等级 |
| 10% - 20% | 持续观察，结合业务峰值判断 |

### 降配参考路径

```
c5.4xlarge (16C/32G) → c5.2xlarge (8C/16G) → c5.xlarge (4C/8G)
m5.2xlarge (8C/32G)  → m5.xlarge (4C/16G)  → t3.xlarge (4C/16G)
```

> 降配前务必确认业务峰值不受影响。建议在非高峰期执行，并配合 Auto Scaling 弹性策略。
