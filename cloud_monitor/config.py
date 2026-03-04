"""配置管理 - 加载和验证多云平台凭证"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

_log = logging.getLogger("cloud_monitor.config")


@dataclass
class HuaweiCloudConfig:
    enabled: bool = False
    ak: str = ""
    sk: str = ""
    project_id: str = ""
    region: str = "cn-north-4"
    regions: list[str] = field(default_factory=list)
    region_projects: dict[str, str] = field(default_factory=dict)

    def get_regions(self) -> list[str]:
        """返回需要巡检的区域列表"""
        return self.regions if self.regions else [self.region]

    def for_region(self, region: str) -> "HuaweiCloudConfig":
        """返回指定区域的 config 副本（自动匹配 project_id）"""
        pid = self.region_projects.get(region, "")
        if not pid and region == self.region:
            pid = self.project_id
        return HuaweiCloudConfig(
            enabled=self.enabled, ak=self.ak, sk=self.sk,
            project_id=pid, region=region,
        )


@dataclass
class AliyunConfig:
    enabled: bool = False
    access_key_id: str = ""
    access_key_secret: str = ""
    region_id: str = "cn-hangzhou"


@dataclass
class AWSAccountConfig:
    """单个 AWS 账户配置"""
    name: str = "default"
    access_key_id: str = ""
    secret_access_key: str = ""
    region: str = "us-east-1"
    regions: list[str] = field(default_factory=list)
    vpn_region: str = ""
    elb_region: str = ""

    def get_vpn_region(self) -> str:
        return self.vpn_region or self.region

    def get_elb_region(self) -> str:
        return self.elb_region or self.region

    def get_regions(self) -> list[str]:
        """获取该账户的所有区域列表（用于 EC2 等区域性服务的多区域查询）"""
        return self.regions if self.regions else [self.region]


@dataclass
class AWSConfig:
    """AWS 多账户配置"""
    enabled: bool = False
    accounts: list[AWSAccountConfig] = field(default_factory=list)

    def get_account(self, name: str = "") -> AWSAccountConfig:
        if not self.accounts:
            raise ValueError("未配置任何 AWS 账户")
        if not name:
            return self.accounts[0]
        for acc in self.accounts:
            if acc.name == name:
                return acc
        available = ", ".join(a.name for a in self.accounts)
        raise ValueError(f"AWS 账户 '{name}' 不存在，可用账户: {available}")

    def list_account_names(self) -> list[str]:
        return [acc.name for acc in self.accounts]


@dataclass
class WebhookConfig:
    enabled: bool = False
    url: str = ""


@dataclass
class EC2CheckConfig:
    """EC2 闲置检测参数"""
    cpu_threshold: float = 10.0
    mem_threshold: float = 10.0
    hours: float = 360
    max_workers: int = 20


@dataclass
class MySQLConfig:
    """MySQL 存储配置"""
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    password: str = ""
    db_name: str = "cloud_monitor"


@dataclass
class TaskSchedule:
    """单个定时任务配置 — 使用 cron 调度（默认每周一凌晨2点）"""
    enabled: bool = True
    cron_day_of_week: str = "mon"
    cron_hour: int = 2
    params: dict = field(default_factory=dict)


@dataclass
class ScheduleConfig:
    """定时巡检配置"""
    enabled: bool = False
    run_on_startup: bool = True
    aws_ec2: TaskSchedule = field(default_factory=TaskSchedule)
    huawei_checks: dict[str, TaskSchedule] = field(default_factory=dict)


@dataclass
class AppConfig:
    huawei: HuaweiCloudConfig = field(default_factory=HuaweiCloudConfig)
    aliyun: AliyunConfig = field(default_factory=AliyunConfig)
    aws: AWSConfig = field(default_factory=AWSConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    ec2_check: EC2CheckConfig = field(default_factory=EC2CheckConfig)
    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)

    def enabled_clouds(self) -> list[str]:
        clouds = []
        if self.huawei.enabled:
            clouds.append("huawei")
        if self.aliyun.enabled:
            clouds.append("aliyun")
        if self.aws.enabled:
            clouds.append("aws")
        return clouds


def _env_override(env_key: str, default: str = "") -> str:
    return os.environ.get(env_key, default)


def _parse_aws_account(data: dict, name: str = "default") -> AWSAccountConfig:
    """从 dict 解析单个 AWS 账户配置"""
    regions_raw = data.get("regions", [])
    if isinstance(regions_raw, str):
        regions_raw = [r.strip() for r in regions_raw.split(",") if r.strip()]
    return AWSAccountConfig(
        name=data.get("name", name),
        access_key_id=data.get("access_key_id", ""),
        secret_access_key=data.get("secret_access_key", ""),
        region=data.get("region", "us-east-1"),
        regions=regions_raw,
        vpn_region=data.get("vpn_region", ""),
        elb_region=data.get("elb_region", ""),
    )


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """加载配置，优先级：环境变量 > config.yaml > 默认值"""
    cfg = AppConfig()

    if config_path is None:
        config_path = str(Path(__file__).parent.parent / "config.yaml")

    if Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        hw = data.get("huawei", {})
        hw_regions_raw = hw.get("regions", [])
        if isinstance(hw_regions_raw, str):
            hw_regions_raw = [r.strip() for r in hw_regions_raw.split(",") if r.strip()]
        cfg.huawei = HuaweiCloudConfig(
            enabled=hw.get("enabled", False),
            ak=hw.get("ak", "") or hw.get("access_key_id", ""),
            sk=hw.get("sk", "") or hw.get("secret_access_key", ""),
            project_id=hw.get("project_id", ""),
            region=hw.get("region", "cn-north-4"),
            regions=hw_regions_raw,
        )

        ali = data.get("aliyun", {})
        cfg.aliyun = AliyunConfig(
            enabled=ali.get("enabled", False),
            access_key_id=ali.get("access_key_id", ""),
            access_key_secret=ali.get("access_key_secret", ""),
            region_id=ali.get("region_id", "cn-hangzhou"),
        )

        aw = data.get("aws", {})
        aws_enabled = aw.get("enabled", False)
        accounts_raw = aw.get("accounts", [])

        if accounts_raw:
            accounts = [_parse_aws_account(a, name=a.get("name", f"account-{i}")) for i, a in enumerate(accounts_raw)]
        elif aw.get("access_key_id"):
            accounts = [_parse_aws_account(aw, name="default")]
        else:
            accounts = []

        cfg.aws = AWSConfig(enabled=aws_enabled, accounts=accounts)

        wh = data.get("webhook", {})
        cfg.webhook = WebhookConfig(
            enabled=wh.get("enabled", False),
            url=wh.get("url", ""),
        )

        ec2 = data.get("ec2_check", {})
        if ec2:
            cfg.ec2_check = EC2CheckConfig(
                cpu_threshold=float(ec2.get("cpu_threshold", 10.0)),
                mem_threshold=float(ec2.get("mem_threshold", 10.0)),
                hours=float(ec2.get("hours", 360)),
                max_workers=int(ec2.get("max_workers", 20)),
            )

        my = data.get("mysql", {})
        if my:
            cfg.mysql = MySQLConfig(
                enabled=my.get("enabled", False),
                host=my.get("host", "127.0.0.1"),
                port=int(my.get("port", 3306)),
                user=my.get("user", "root"),
                password=my.get("password", ""),
                db_name=my.get("db_name", "cloud_monitor"),
            )

        sch = data.get("schedule", {})
        if sch:
            aws_ec2_raw = sch.get("aws_ec2", {})
            aws_ec2_task = TaskSchedule(
                enabled=aws_ec2_raw.get("enabled", True),
                cron_day_of_week=str(aws_ec2_raw.get("cron_day_of_week", "mon")),
                cron_hour=int(aws_ec2_raw.get("cron_hour", 2)),
            )

            huawei_tasks: dict[str, TaskSchedule] = {}
            for check_type, check_cfg in sch.get("huawei_checks", {}).items():
                if isinstance(check_cfg, dict):
                    params = {k: v for k, v in check_cfg.items()
                              if k not in ("enabled", "cron_day_of_week", "cron_hour")}
                    huawei_tasks[check_type] = TaskSchedule(
                        enabled=check_cfg.get("enabled", True),
                        cron_day_of_week=str(check_cfg.get("cron_day_of_week", "mon")),
                        cron_hour=int(check_cfg.get("cron_hour", 2)),
                        params=params,
                    )

            cfg.schedule = ScheduleConfig(
                enabled=sch.get("enabled", False),
                run_on_startup=sch.get("run_on_startup", True),
                aws_ec2=aws_ec2_task,
                huawei_checks=huawei_tasks,
            )

    # 环境变量覆盖
    if v := _env_override("HUAWEI_AK"):
        cfg.huawei.ak = v
        cfg.huawei.enabled = True
    if v := _env_override("HUAWEI_SK"):
        cfg.huawei.sk = v
    if v := _env_override("HUAWEI_PROJECT_ID"):
        cfg.huawei.project_id = v
    if v := _env_override("HUAWEI_REGION"):
        cfg.huawei.region = v

    if v := _env_override("ALIYUN_ACCESS_KEY_ID"):
        cfg.aliyun.access_key_id = v
        cfg.aliyun.enabled = True
    if v := _env_override("ALIYUN_ACCESS_KEY_SECRET"):
        cfg.aliyun.access_key_secret = v
    if v := _env_override("ALIYUN_REGION_ID"):
        cfg.aliyun.region_id = v

    if v := _env_override("AWS_ACCESS_KEY_ID"):
        env_acc = AWSAccountConfig(
            name="env-default",
            access_key_id=v,
            secret_access_key=_env_override("AWS_SECRET_ACCESS_KEY"),
            region=_env_override("AWS_DEFAULT_REGION", "us-east-1"),
        )
        cfg.aws.accounts.insert(0, env_acc)
        cfg.aws.enabled = True

    if v := _env_override("WEBHOOK_URL"):
        cfg.webhook.url = v
        cfg.webhook.enabled = True

    if cfg.huawei.enabled and cfg.huawei.ak and cfg.huawei.get_regions():
        cfg.huawei.region_projects = _fetch_huawei_region_projects(cfg.huawei)

    return cfg


def _fetch_huawei_region_projects(hw: HuaweiCloudConfig) -> dict[str, str]:
    """通过 IAM API 自动查询所有区域的 project_id 映射"""
    try:
        from huaweicloudsdkcore.auth.credentials import GlobalCredentials
        from huaweicloudsdkiam.v3 import IamClient
        from huaweicloudsdkiam.v3.model import KeystoneListProjectsRequest
        from huaweicloudsdkiam.v3.region.iam_region import IamRegion

        credentials = GlobalCredentials(hw.ak, hw.sk)
        client = (
            IamClient.new_builder()
            .with_credentials(credentials)
            .with_region(IamRegion.value_of(hw.region))
            .build()
        )
        resp = client.keystone_list_projects(KeystoneListProjectsRequest())
        mapping = {p.name: p.id for p in resp.projects}
        needed = hw.get_regions()
        result = {r: mapping[r] for r in needed if r in mapping}
        _log.info("华为云 region→project_id: %s", result)
        return result
    except Exception as e:
        _log.warning("自动获取华为云 project_id 失败: %s", e)
        if hw.project_id and hw.region:
            return {hw.region: hw.project_id}
        return {}
