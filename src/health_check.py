"""
健康检查模块
"""

import logging
from datetime import datetime
from typing import List

logger = logging.getLogger(__name__)


class HealthChecker:
    def __init__(self):
        self.status = {'healthy': True, 'warnings': [], 'errors': [], 'timestamp': datetime.now().isoformat()}

    def check_collection(self, news_count: int, errors: List[str], threshold: int = 1) -> dict:
        self.status['healthy'] = True
        self.status['warnings'] = []
        self.status['errors'] = []

        if news_count == 0:
            self.status['warnings'].append('⚠️ 未采集到任何新闻')
            self.status['healthy'] = False

        if errors:
            self.status['errors'] = errors[:5]
            self.status['healthy'] = False

        return self.status

    def get_report(self, news_count: int, errors: List[str]) -> str:
        status = self.check_collection(news_count, errors)
        lines = [
            "=" * 50,
            "📊 系统健康检查报告",
            "=" * 50,
            f"状态: {'✅ 正常' if status['healthy'] else '⚠️ 异常'}",
            f"新闻数量: {news_count} 条",
            f"警告: {', '.join(status['warnings']) if status['warnings'] else '无'}",
            f"错误: {', '.join(status['errors']) if status['errors'] else '无'}",
            f"检查时间: {status['timestamp']}",
            "=" * 50,
        ]
        report = '\n'.join(lines)
        logger.info(report)
        return report
