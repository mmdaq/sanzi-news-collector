#!/usr/bin/env python3
"""
农村集体"三资"监管新闻自动采集简报系统
主程序入口（v3）
"""

import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.brief_generator import BriefGenerator
from src.collector import NewsCollector
from src.config import Config
from src.email_sender import EmailSender
from src.health_check import HealthChecker


def setup_logging(log_file: str, level: str = "INFO"):
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(__name__)


def build_subject(total: int, today: int) -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    if total == 0:
        return f"【三资监管简报】{date_str} 今日及近一周均无相关新闻"
    if today > 0:
        return f"【三资监管简报】{date_str} 今日 {today} 条 · 近一周共 {total} 条"
    return f"【三资监管简报】{date_str} 今日暂无 · 近一周 {total} 条"


def main():
    config = Config()
    logger = setup_logging(config.log_file, config.log_level)

    print("=" * 60)
    print("  农村集体'三资'监管 · 新闻自动采集简报系统 v3.0")
    print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not config.is_valid:
        missing = config.get_missing_fields()
        logger.error("❌ 配置不完整，缺少: %s", ", ".join(missing))
        logger.error("请设置环境变量、GitHub Secrets 或 .env 文件")
        sys.exit(1)

    logger.info("✅ 配置加载成功")
    os.makedirs(config.data_dir, exist_ok=True)

    collector = NewsCollector(config)
    news_list = collector.collect()
    errors = collector.get_errors()

    HealthChecker().get_report(len(news_list), errors)

    generator = BriefGenerator(config)
    html_brief = generator.generate_html(news_list)
    text_brief = generator.generate_text(news_list)

    brief_path = os.path.join(config.data_dir,
                              f"brief_{datetime.now().strftime('%Y%m%d')}.html")
    with open(brief_path, "w", encoding="utf-8") as f:
        f.write(html_brief)
    logger.info("✅ 简报已保存: %s", brief_path)

    if config.dry_run:
        logger.info("🧪 DRY_RUN=true：跳过邮件发送，仅输出文本简报供检查")
        print("\n" + text_brief + "\n")
        return

    if not news_list and not config.send_empty_email:
        logger.info("没有新闻且 SEND_EMPTY_EMAIL=false，跳过邮件发送")
        return

    today_count = sum(1 for n in news_list if n.days_ago is not None and n.days_ago <= 0)
    subject = build_subject(len(news_list), today_count)
    logger.info("发送邮件... subject=%s", subject)

    sender = EmailSender(config)
    success = sender.send(subject, html_brief, text_brief)
    if success:
        logger.info("✅ 程序执行完成！")
    else:
        logger.error("⚠️ 程序执行完成，但邮件发送失败，请检查邮箱配置")
        sys.exit(0)


if __name__ == "__main__":
    main()
