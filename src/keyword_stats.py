"""
关键词效果统计
"""

import os
import json
from collections import defaultdict
from datetime import datetime


class KeywordStats:
    def __init__(self, stats_file: str = "./data/keyword_stats.json"):
        self.stats_file = stats_file
        self.data = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.stats_file):
            return defaultdict(lambda: {'hits': 0, 'last_use': '', 'total_found': 0})
        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
                return defaultdict(lambda: {'hits': 0, 'last_use': '', 'total_found': 0}, raw)
        except:
            return defaultdict(lambda: {'hits': 0, 'last_use': '', 'total_found': 0})

    def record(self, keyword_group: tuple, found: int):
        key = ' + '.join(keyword_group)
        self.data[key]['hits'] = self.data[key].get('hits', 0) + 1
        self.data[key]['total_found'] = self.data[key].get('total_found', 0) + found
        self.data[key]['last_use'] = datetime.now().strftime('%Y-%m-%d')
        self._save()

    def _save(self):
        os.makedirs(os.path.dirname(self.stats_file), exist_ok=True)
        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(dict(self.data), f, ensure_ascii=False, indent=2)

    def get_ineffective(self, threshold: int = 3) -> list:
        return [k for k, v in self.data.items() if v.get('hits', 0) < threshold]

    def get_top_keywords(self, limit: int = 10) -> list:
        sorted_items = sorted(self.data.items(), key=lambda x: x[1].get('total_found', 0), reverse=True)
        return [(k, v.get('total_found', 0)) for k, v in sorted_items[:limit]]
