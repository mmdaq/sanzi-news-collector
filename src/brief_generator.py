"""
简报生成器：HTML + 纯文本双版本
- 按时效分层：今日 / 昨日 / 近3天 / 近7天
- 标注来源类型：官方平台 / 搜索引擎
"""

from datetime import datetime
from typing import Dict, List, Tuple

from .collector import NewsItem
from .config import Config


OFFICIAL_LABELS = {
    1: "中央纪委国家监委",
    2: "农业农村部",
    5: "省级纪委监委",
    6: "搜索引擎",
}


def recency_bucket(days_ago) -> Tuple[int, str]:
    if days_ago is None:
        return 9, "日期未知"
    if days_ago <= 0:
        return 0, "今天"
    if days_ago == 1:
        return 1, "昨天"
    if days_ago <= 3:
        return 2, f"{days_ago}天前"
    return 3, f"{days_ago}天前"


class BriefGenerator:
    def __init__(self, config: Config):
        self.config = config

    def _summary(self, news: NewsItem) -> str:
        summary = news.summary if news.summary and len(news.summary) > 10 else news.title
        if len(summary) > self.config.brief_word_count:
            summary = summary[: self.config.brief_word_count] + "..."
        return summary

    @staticmethod
    def _stats(news_list: List[NewsItem]) -> Dict[str, int]:
        official = sum(1 for n in news_list if n.is_official)
        today = sum(1 for n in news_list if n.days_ago is not None and n.days_ago <= 0)
        return {
            "total": len(news_list),
            "official": official,
            "search": len(news_list) - official,
            "today": today,
        }

    # ==================== HTML ====================
    def generate_html(self, news_list: List[NewsItem]) -> str:
        today = datetime.now().strftime("%Y年%m月%d日")
        stats = self._stats(news_list)

        if stats["today"] > 0:
            sub = f"{today} ｜ 今日 {stats['today']} 条，近一周共 {stats['total']} 条"
        else:
            sub = f"{today} ｜ 今日暂无当日新闻，以下为近一周共 {stats['total']} 条"

        css = """
        body { font-family: -apple-system, "Microsoft YaHei", Arial, sans-serif; font-size: 14px; line-height: 1.8; color: #333; max-width: 820px; margin: 0 auto; padding: 20px; background: #f5f7fa; }
        .container { background: #fff; border-radius: 12px; padding: 30px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
        .header { background: linear-gradient(135deg, #1a3c6e 0%, #2a5a9a 100%); color: #fff; padding: 20px 25px; border-radius: 10px; margin-bottom: 22px; }
        .header h1 { margin: 0; font-size: 22px; font-weight: 700; }
        .header .sub { font-size: 13px; opacity: 0.9; margin-top: 6px; }
        .stats { background: #f0f4f8; padding: 12px 18px; border-radius: 8px; margin-bottom: 18px; font-size: 13px; color: #555; }
        .stats b { color: #1a3c6e; }
        .section { font-size: 15px; font-weight: 700; color: #1a3c6e; margin: 22px 0 10px 0; padding-left: 10px; border-left: 4px solid #2a5a9a; }
        .news-item { border-bottom: 1px solid #e8ecf0; padding: 14px 0; }
        .news-item:last-child { border-bottom: none; }
        .news-title { font-size: 15px; font-weight: 600; color: #1a3c6e; text-decoration: none; }
        .news-title:hover { text-decoration: underline; }
        .news-meta { font-size: 12px; color: #888; margin: 4px 0; }
        .badge-official { display: inline-block; background: #1a3c6e; color: #fff; border-radius: 4px; padding: 0 7px; font-size: 11px; margin-left: 6px; }
        .badge-search { display: inline-block; background: #e67e22; color: #fff; border-radius: 4px; padding: 0 7px; font-size: 11px; margin-left: 6px; }
        .badge-today { display: inline-block; background: #d32f2f; color: #fff; border-radius: 4px; padding: 0 7px; font-size: 11px; margin-left: 6px; }
        .news-summary { font-size: 13px; color: #555; margin: 6px 0 4px 0; padding-left: 12px; border-left: 3px solid #d0d7e2; }
        .news-link { font-size: 12px; color: #1a73e8; word-break: break-all; }
        .news-link a { color: #1a73e8; text-decoration: none; }
        .footer { margin-top: 25px; padding-top: 18px; border-top: 2px solid #e8ecf0; font-size: 12px; color: #999; text-align: center; }
        .empty { text-align: center; color: #999; padding: 40px 0; font-size: 16px; }
        """

        parts = [
            '<!DOCTYPE html><html><head><meta charset="UTF-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            "<title>三资监管每日简报</title><style>", css, "</style></head><body><div class='container'>",
            f"""
            <div class="header">
                <h1>📋 农村集体"三资"监管 · 每日简报</h1>
                <div class="sub">{sub}</div>
            </div>
            <div class="stats">
                📊 官方平台 <b>{stats['official']}</b> 条 ｜ 搜索引擎 <b>{stats['search']}</b> 条 ｜
                今日 <b>{stats['today']}</b> 条 ｜ 采集时间 <b>{datetime.now().strftime('%H:%M:%S')}</b>
            </div>
            """,
        ]

        if not news_list:
            parts.append(
                '<div class="empty">📭 近一周未检索到符合条件的相关新闻<br>'
                '<span style="font-size:13px;">建议检查关键词词库或网络环境，也可手动查看官方平台。</span></div>'
            )
        else:
            sections: Dict[int, List[NewsItem]] = {0: [], 1: [], 2: [], 3: []}
            for n in news_list:
                bucket, _ = recency_bucket(n.days_ago)
                sections.setdefault(bucket, []).append(n)
            section_titles = {
                0: "📅 今日",
                1: "🕐 昨日",
                2: "🕑 近3天",
                3: "🗓 近7天",
                9: "📌 其他",
            }
            for bucket in sorted(sections):
                items = sections[bucket]
                if not items:
                    continue
                parts.append(f'<div class="section">{section_titles[bucket]}（{len(items)} 条）</div>')
                for idx, news in enumerate(items, 1):
                    summary = self._summary(news)
                    label = OFFICIAL_LABELS.get(news.priority, f"P{news.priority}")
                    badge = ('<span class="badge-official">官方</span>'
                             if news.is_official else '<span class="badge-search">搜索</span>')
                    today_badge = '<span class="badge-today">今日</span>' if news.days_ago is not None and news.days_ago <= 0 else ""
                    parts.append(f"""
                    <div class="news-item">
                        <div><span style="color:#aaa;font-weight:700;margin-right:8px;">{idx}</span>
                        <a href="{news.url}" target="_blank" class="news-title">{news.title}</a></div>
                        <div class="news-meta">
                            {news.source}{badge}{today_badge}
                            <span style="margin:0 8px;color:#ddd;">|</span>
                            {news.publish_time if news.publish_time else '日期未知'}
                            <span style="margin:0 8px;color:#ddd;">|</span>{label}
                        </div>
                        <div class="news-summary">{summary}</div>
                        <div class="news-link">🔗 <a href="{news.url}" target="_blank">{news.url}</a></div>
                    </div>
                    """)

        parts.append(f"""
        <div class="footer">
            <p>本简报由「三资监管·自动采集系统」生成</p>
            <p>数据来源：中央纪委国家监委网站 · 农业农村部官网 · 各省/市纪委监委网站 · 搜索引擎</p>
            <p>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p style="color:#ddd;font-size:11px;margin-top:8px;">— 仅供内部参考，请以官方原文为准 —</p>
        </div>
        </div></body></html>""")
        return "\n".join(parts)

    # ==================== 纯文本 ====================
    def generate_text(self, news_list: List[NewsItem]) -> str:
        today = datetime.now().strftime("%Y年%m月%d日")
        stats = self._stats(news_list)
        lines = [
            "=" * 70,
            "📋 农村集体'三资'监管 · 每日简报",
            f"📅 {today} · 共 {stats['total']} 条（官方 {stats['official']} / 搜索 {stats['search']}，今日 {stats['today']}）",
            "=" * 70,
            "",
        ]
        if not news_list:
            lines.append("近一周未检索到符合条件的相关新闻")
        else:
            sections: Dict[int, List[NewsItem]] = {}
            for n in news_list:
                bucket, _ = recency_bucket(n.days_ago)
                sections.setdefault(bucket, []).append(n)
            section_titles = {
                0: "【今日】", 1: "【昨日】", 2: "【近3天】", 3: "【近7天】", 9: "【其他】",
            }
            for bucket in sorted(sections):
                items = sections[bucket]
                if not items:
                    continue
                lines.append(f"{section_titles[bucket]}（{len(items)} 条）")
                lines.append("-" * 50)
                for idx, news in enumerate(items, 1):
                    label = OFFICIAL_LABELS.get(news.priority, f"P{news.priority}")
                    tag = "官方" if news.is_official else "搜索"
                    lines.append(f"{idx}. [{tag}] {news.title}")
                    lines.append(f"   发布：{news.publish_time or '日期未知'} ｜ 来源：{news.source}（{label}）")
                    lines.append(f"   简述：{self._summary(news)}")
                    lines.append(f"   链接：{news.url}")
                    lines.append("")
        lines.extend([
            "-" * 70,
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "本简报由「三资监管·自动采集系统」生成",
            "— 仅供内部参考，请以官方原文为准 —",
            "=" * 70,
        ])
        return "\n".join(lines)
