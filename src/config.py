"""
配置管理模块
"""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """系统配置类"""
    
    # ========== 邮件配置 ==========
    smtp_server: str = os.getenv('SMTP_SERVER', 'smtp.qq.com')
    smtp_port: int = int(os.getenv('SMTP_PORT', '465'))
    sender_email: str = os.getenv('SENDER_EMAIL', '')
    sender_password: str = os.getenv('SENDER_PASSWORD', '')
    receiver_email: str = os.getenv('RECEIVER_EMAIL', '')
    
    # ========== 采集配置 ==========
    max_articles_per_source: int = 10
    request_timeout: int = 10
    request_delay: float = 0.3
    max_workers: int = 5
    max_retries: int = 2
    link_verify_timeout: int = 3
    min_news_threshold: int = 2
    
    # ========== 简报配置 ==========
    brief_word_count: int = 100
    max_brief_items: int = 30
    days_range: int = 7  # 7 天时效性窗口，保证不会收到太老的正常新闻
    
    # ========== 数据存储 ==========
    data_dir: str = "./data"
    history_file: str = "./data/history.json"
    stats_file: str = "./data/keyword_stats.json"
    
    # ========== 日志配置 ==========
    log_file: str = "./data/collector.log"
    log_level: str = "INFO"
    
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
            missing.append('SENDER_EMAIL')
        if not self.sender_password:
            missing.append('SENDER_PASSWORD')
        if not self.receiver_email:
            missing.append('RECEIVER_EMAIL')
        if not self.smtp_server:
            missing.append('SMTP_SERVER')
        return missing
