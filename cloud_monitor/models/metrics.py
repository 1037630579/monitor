"""通用指标数据模型 - 统一三大云平台的指标表示"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class MetricInfo:
    """指标元数据"""
    cloud: str
    namespace: str
    metric_name: str
    description: str = ""
    unit: str = ""
    dimensions: dict[str, str] = field(default_factory=dict)

    def display(self) -> str:
        dims = ", ".join(f"{k}={v}" for k, v in self.dimensions.items())
        parts = [
            f"[{self.cloud}] {self.namespace}/{self.metric_name}",
            f"  描述: {self.description}" if self.description else "",
            f"  单位: {self.unit}" if self.unit else "",
            f"  维度: {dims}" if dims else "",
        ]
        return "\n".join(p for p in parts if p)


@dataclass
class DataPoint:
    """单个数据点"""
    timestamp: datetime
    value: float
    unit: str = ""

    def display(self) -> str:
        ts = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        return f"  {ts}  {self.value:.2f} {self.unit}"


@dataclass
class MetricData:
    """一组指标查询结果"""
    cloud: str
    namespace: str
    metric_name: str
    instance_id: str = ""
    period: int = 300
    statistics: str = "average"
    data_points: list[DataPoint] = field(default_factory=list)

    def display(self) -> str:
        header = (
            f"[{self.cloud}] {self.namespace}/{self.metric_name}"
            f" | 实例: {self.instance_id} | 周期: {self.period}s"
            f" | 统计方式: {self.statistics}"
        )
        if not self.data_points:
            return f"{header}\n  (无数据)"
        lines = [header] + [dp.display() for dp in self.data_points]
        return "\n".join(lines)

    def summary(self) -> str:
        if not self.data_points:
            return f"[{self.cloud}] {self.metric_name}: 无数据"
        values = [dp.value for dp in self.data_points]
        avg = sum(values) / len(values)
        mn, mx = min(values), max(values)
        unit = self.data_points[0].unit
        return (
            f"[{self.cloud}] {self.metric_name} (实例 {self.instance_id}): "
            f"平均={avg:.2f}{unit}, 最小={mn:.2f}{unit}, 最大={mx:.2f}{unit}, "
            f"数据点数={len(values)}"
        )


@dataclass
class InstanceInfo:
    """云资源实例信息"""
    cloud: str
    instance_id: str
    instance_name: str = ""
    instance_type: str = ""
    status: str = ""
    region: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    def display(self) -> str:
        parts = [
            f"[{self.cloud}] {self.instance_id}",
            f"  名称: {self.instance_name}" if self.instance_name else "",
            f"  类型: {self.instance_type}" if self.instance_type else "",
            f"  状态: {self.status}" if self.status else "",
            f"  区域: {self.region}" if self.region else "",
        ]
        for k, v in self.extra.items():
            parts.append(f"  {k}: {v}")
        return "\n".join(p for p in parts if p)
