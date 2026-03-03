"""配置管理 - 加载和验证多云平台凭证"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class HuaweiCloudConfig:
    enabled: bool = False
    ak: str = ""
    sk: str = ""
    project_id: str = ""
    region: str = "cn-north-4"


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
class AppConfig:
    huawei: HuaweiCloudConfig = field(default_factory=HuaweiCloudConfig)
    aliyun: AliyunConfig = field(default_factory=AliyunConfig)
    aws: AWSConfig = field(default_factory=AWSConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    ec2_check: EC2CheckConfig = field(default_factory=EC2CheckConfig)

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
        cfg.huawei = HuaweiCloudConfig(
            enabled=hw.get("enabled", False),
            ak=hw.get("ak", ""),
            sk=hw.get("sk", ""),
            project_id=hw.get("project_id", ""),
            region=hw.get("region", "cn-north-4"),
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

    return cfg
