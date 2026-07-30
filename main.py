#!/usr/bin/env python3
"""
农村集体"三资"监管新闻自动采集简报系统
主程序入口
"""

import os
import sys
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import Config
from src.collector import NewsCollector
from src.brief_generator import BriefGenerator
from src.email_sender import EmailSender
from src.health_check import HealthChecker


def setup_logging(log_file: str, level: str = "INFO"):
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def main():
    logger = setup_logging("./data/collector.log", "INFO")

    print("=" * 60)
    print("  农村集体'三资'监管 · 新闻自动采集简报系统 v2.0")
    print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    config = Config()

    if not config.is_valid:
        missing = config.get_missing_fields()
        logger.error(f"❌ 配置不完整，缺少: {', '.join(missing)}")
        logger.error("请设置环境变量或在 GitHub Secrets 中配置")
        sys.exit(1)

    logger.info("✅ 配置加载成功")
    os.makedirs(config.data_dir, exist_ok=True)

    all_news = []
    errors = []

    try:
        collector = NewsCollector(config)
        news_list = collector.collect()
        all_news.extend(news_list)
        errors.extend(collector.get_errors())
        logger.info(f"✅ 采集到 {len(news_list)} 条新闻")

        health_checker = HealthChecker()
        health_checker.get_report(len(all_news), errors)

        # 【修复逻辑 1】：如果 0 条新闻，直接成功退出，不触发邮件发送，避免 550 SMTP 错误
        if not all_news:
            logger.warning("⚠️ 未采集到任何新闻，将保存空简报并跳过邮件发送流程")
            
            # 依然生成空简报并保存，以便在 Actions Artifacts 中查看
            generator = BriefGenerator(config)
            html_brief = generator.generate_html(all_news)
            text_brief = generator.generate_text(all_news)

            with open(f"{config.data_dir}/brief_{datetime.now().strftime('%Y%m%d')}.html", 'w', encoding='utf-8') as f:
                f.write(html_brief)
            logger.info("✅ 空简报已保存")

            logger.info("=" * 60)
            logger.info("✅ 程序执行完成（无新闻，跳过邮件）")
            logger.info("=" * 60)
            sys.exit(0)

        logger.info("生成简报...")
        generator = BriefGenerator(config)
        html_brief = generator.generate_html(all_news)
        text_brief = generator.generate_text(all_news)

        # 强制确保文件写入使用 utf-8，防止 Linux 环境下崩溃
        with open(f"{config.data_dir}/brief_{datetime.now().strftime('%Y%m%d')}.html", 'w', encoding='utf-8') as f:
            f.write(html_brief)
        logger.info("✅ 简报已保存")

        logger.info("发送邮件...")
        sender = EmailSender(config)
        subject = f"【三资监管简报】{datetime.now().strftime('%Y-%m-%d')} 集体资产相关新闻 {len(all_news)} 条"
        success = sender.send(subject, html_brief, text_brief)

        if success:
            logger.info("=" * 60)
            logger.info("✅ 程序执行完成！")
            logger.info("=" * 60)
        else:
            # 【修复逻辑 2】：即使邮件发失败，也视为任务本身执行完成，不终止 Action
            logger.error("=" * 60)
            logger.error("⚠️ 程序执行完成，但邮件发送失败")
            logger.error("   请检查邮箱配置 (SENDER_EMAIL/SENDER_PASSWORD)")
            logger.error("=" * 60)
            sys.exit(0)

    except KeyboardInterrupt:
        logger.info("程序被用户中断")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ 程序异常: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
