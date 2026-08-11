"""
配置管理模块
支持环境变量与 .env 文件（.env 优先级低于环境变量）
"""

import os
from dataclasses import dataclass, field
from typing import List


def load_dotenv(path: str = ".env"):
    """极简 .env 解析器，避免引入额外依赖。"""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split("|") if item.strip()]


load_dotenv()


@dataclass
class Config:
    """系统配置类"""

    # ========== 邮件配置 ==========
    smtp_server: str = os.getenv("SMTP_SERVER", "smtp.qq.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "465"))
    sender_email: str = os.getenv("SENDER_EMAIL", "")
    sender_password: str = os.getenv("SENDER_PASSWORD", "")
    receiver_email: str = os.getenv("RECEIVER_EMAIL", "")

    # 是否在没有新闻时也发送一封"今日无相关新闻"的简报（默认发送）
    send_empty_email: bool = _env_bool("SEND_EMPTY_EMAIL", True)
    # 调试用：只生成简报，不真正发送邮件
    dry_run: bool = _env_bool("DRY_RUN", False)

    # ========== 采集配置 ==========
    max_articles_per_source: int = int(os.getenv("MAX_ARTICLES_PER_SOURCE", "12"))
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "12"))
    request_delay: float = float(os.getenv("REQUEST_DELAY", "0.2"))
    max_workers: int = int(os.getenv("MAX_WORKERS", "4"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "2"))
    link_verify_timeout: int = 5

    # 官方平台结果少于该值时，触发搜索引擎备用方案
    min_official_results: int = int(os.getenv("MIN_OFFICIAL_RESULTS", "2"))
    # 搜索结果最多合并条数（进入候选池，最终仍受 max_brief_items 限制）
    search_enabled: bool = _env_bool("SEARCH_ENABLED", True)
    max_search_results: int = int(os.getenv("MAX_SEARCH_RESULTS", "30"))
    # 正文抓取校验的候选上限（防止某天候选过多拖慢任务）
    body_fetch_limit: int = int(os.getenv("BODY_FETCH_LIMIT", "60"))
    search_queries: List[str] = field(default_factory=lambda: _env_list("SEARCH_QUERIES", [
        '农村集体 "三资" 监管',
        "村集体 资产 追回",
        "农村集体资产 整治 纪委",
        '农村集体 "三资" 清查',
        "集体经济 挪用 通报",
        "农村集体 资产 典型案例",
    ]))

    # 时效窗口：默认近 7 天（当天没有时自动放宽到近一周）
    days_range: int = int(os.getenv("DAYS_RANGE", "7"))

    # ========== 简报配置 ==========
    brief_word_count: int = 120
    max_brief_items: int = int(os.getenv("MAX_BRIEF_ITEMS", "30"))

    # ========== 数据存储 ==========
    data_dir: str = os.getenv("DATA_DIR", "./data")
    history_file: str = ""
    stats_file: str = ""
    log_file: str = ""
    log_level: str = "INFO"

    def __post_init__(self):
        self.history_file = os.path.join(self.data_dir, "history.json")
        self.stats_file = os.path.join(self.data_dir, "keyword_stats.json")
        self.log_file = os.path.join(self.data_dir, "collector.log")

    @property
    def is_valid(self) -> bool:
        return all([
            self.sender_email,
            self.sender_password,
            self.receiver_email,
            self.smtp_server,
        ])

    def get_missing_fields(self) -> list:
        missing = []
        if not self.sender_email:
            missing.append("SENDER_EMAIL")
        if not self.sender_password:
            missing.append("SENDER_PASSWORD")
        if not self.receiver_email:
            missing.append("RECEIVER_EMAIL")
        if not self.smtp_server:
            missing.append("SMTP_SERVER")
        return missing
