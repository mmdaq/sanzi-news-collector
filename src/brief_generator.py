"""
简报生成器模块
"""

from datetime import datetime
from typing import List
from .collector import NewsItem
from .config import Config


class BriefGenerator:
    def __init__(self, config: Config):
        self.config = config

    def _generate_summary(self, news: NewsItem) -> str:
        if news.summary and len(news.summary) > 10:
            summary = news.summary
        else:
            summary = news.title
        if len(summary) > self.config.brief_word_count:
            summary = summary[:self.config.brief_word_count] + '...'
        return summary

    def generate_html(self, news_list: List[NewsItem]) -> str:
        today = datetime.now().strftime('%Y年%m月%d日')

        priority_labels = {
            1: '🏆 中央纪委国家监委',
            2: '🌾 农业农村部',
            3: '📰 人民网反腐',
            4: '📖 中国纪检监察报',
            5: '🏛️ 省级/市级纪委监委',
            6: '📱 官方自媒体',
        }

        html_parts = [
            '<!DOCTYPE html><html><head><meta charset="UTF-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            '<title>三资监管每日简报</title><style>',
            '''
            body { font-family: -apple-system, "Microsoft YaHei", Arial, sans-serif; font-size: 14px; line-height: 1.8; color: #333; max-width: 820px; margin: 0 auto; padding: 20px; background: #f5f7fa; }
            .container { background: #fff; border-radius: 12px; padding: 30px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
            .header { background: linear-gradient(135deg, #1a3c6e 0%, #2a5a9a 100%); color: #fff; padding: 20px 25px; border-radius: 10px; margin-bottom: 25px; }
            .header h1 { margin: 0; font-size: 22px; font-weight: 700; }
            .header .sub { font-size: 13px; opacity: 0.85; margin-top: 6px; }
            .stats { background: #f0f4f8; padding: 12px 18px; border-radius: 8px; margin-bottom: 20px; font-size: 13px; color: #555; }
            .stats span { font-weight: 600; color: #1a3c6e; }
            .stats .count { font-size: 18px; color: #d32f2f; }
            .priority-legend { display: flex; flex-wrap: wrap; gap: 6px 15px; padding: 8px 0 15px 0; font-size: 12px; color: #666; border-bottom: 1px solid #eee; margin-bottom: 15px; }
            .priority-legend .tag { display: inline-block; padding: 1px 10px; border-radius: 10px; font-size: 11px; font-weight: 600; color: #fff; }
            .tag-p1 { background: #1a3c6e; }
            .tag-p2 { background: #2e7d32; }
            .tag-p3 { background: #e65100; }
            .tag-p4 { background: #6a1b9a; }
            .tag-p5 { background: #0d47a1; }
            .tag-p6 { background: #e67e22; }
            .news-item { border-bottom: 1px solid #e8ecf0; padding: 16px 0; }
            .news-item:last-child { border-bottom: none; }
            .news-index { display: inline-block; background: #1a3c6e; color: #fff; width: 28px; height: 28px; border-radius: 50%; text-align: center; line-height: 28px; font-size: 13px; font-weight: 700; flex-shrink: 0; margin-right: 12px; }
            .news-header { display: flex; align-items: flex-start; margin-bottom: 4px; }
            .news-title { font-size: 15px; font-weight: 600; color: #1a3c6e; text-decoration: none; flex: 1; }
            .news-title:hover { text-decoration: underline; }
            .news-meta { font-size: 12px; color: #999; margin: 4px 0 4px 40px; }
            .news-meta .source { color: #1a3c6e; font-weight: 600; }
            .news-meta .priority-tag { display: inline-block; padding: 0 10px; border-radius: 10px; font-size: 10px; font-weight: 600; margin-left: 8px; color: #fff; }
            .pt-1 { background: #1a3c6e; }
            .pt-2 { background: #2e7d32; }
            .pt-3 { background: #e65100; }
            .pt-4 { background: #6a1b9a; }
            .pt-5 { background: #0d47a1; }
            .pt-6 { background: #e67e22; }
            .news-summary { font-size: 13px; color: #555; margin: 6px 0 4px 40px; padding-left: 12px; border-left: 3px solid #d0d7e2; }
            .news-link { font-size: 12px; color: #1a73e8; margin-left: 40px; word-break: break-all; }
            .news-link a { color: #1a73e8; text-decoration: none; }
            .news-link a:hover { text-decoration: underline; }
            .footer { margin-top: 25px; padding-top: 18px; border-top: 2px solid #e8ecf0; font-size: 12px; color: #999; text-align: center; }
            .empty { text-align: center; color: #999; padding: 50px 0; font-size: 16px; }
            @media (max-width: 600px) {
                .container { padding: 15px; }
                .news-summary, .news-meta, .news-link { margin-left: 0; padding-left: 0; border-left: none; }
            }
            '''
            '</style></head><body><div class="container">'
        ]

        html_parts.append(f'''
        <div class="header">
            <h1>📋 农村集体"三资"监管 · 每日简报</h1>
            <div class="sub">{today} ｜ 共 <strong>{len(news_list)}</strong> 条最新相关信息</div>
        </div>
        ''')

        if news_list:
            sources = set(n.source for n in news_list)
            legend_html = '<div class="priority-legend">📌 来源优先级：'
            for p in sorted(set(n.priority for n in news_list)):
                label = priority_labels.get(p, f'P{p}')
                legend_html += f'<span class="tag tag-p{p}">{p}.{label}</span>'
            legend_html += '</div>'

            html_parts.append(f'''
            <div class="stats">
                📊 来源平台：<span>{', '.join(sources)}</span> ｜
                ⏱️ 采集时间：<span>{datetime.now().strftime('%H:%M:%S')}</span> ｜
                📰 新闻总数：<span class="count">{len(news_list)}</span> 条
            </div>
            {legend_html}
            ''')

        if not news_list:
            html_parts.append('<div class="empty">📭 今日暂无相关新闻</div>')
        else:
            for idx, news in enumerate(news_list, 1):
                summary = self._generate_summary(news)
                display_url = news.url[:60] + '...' if len(news.url) > 60 else news.url
                label = priority_labels.get(news.priority, f'P{news.priority}')
                pt_class = f'pt-{news.priority}' if news.priority in range(1, 7) else 'pt-6'

                html_parts.append(f'''
                <div class="news-item">
                    <div class="news-header">
                        <span class="news-index">{idx}</span>
                        <a href="{news.url}" target="_blank" class="news-title">{news.title}</a>
                    </div>
                    <div class="news-meta">
                        <span class="source">{news.source}</span>
                        <span style="margin:0 6px;color:#ddd;">|</span>
                        {news.publish_time if news.publish_time else '日期未知'}
                        <span class="priority-tag {pt_class}">{label}</span>
                        <span style="margin-left:6px;font-size:11px;">✅</span>
                    </div>
                    <div class="news-summary">{summary}</div>
                    <div class="news-link">🔗 <a href="{news.url}" target="_blank">{display_url}</a></div>
                </div>
                ''')

        html_parts.append(f'''
        <div class="footer">
            <p>本简报由「三资监管·自动采集系统」生成</p>
            <p>数据来源：中央纪委国家监委网站 · 农业农村部官网 · 人民网反腐倡廉频道 · 中国纪检监察报 · 各省/市纪委监委网站</p>
            <p>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p style="color:#ddd;font-size:11px;margin-top:8px;">— 仅供内部参考，请以官方原文为准 —</p>
        </div>
        ''')

        html_parts.append('</div></body></html>')
        return '\n'.join(html_parts)

    def generate_text(self, news_list: List[NewsItem]) -> str:
        priority_labels = {
            1: '🏆中央纪委国家监委',
            2: '🌾农业农村部',
            3: '📰人民网反腐',
            4: '📖中国纪检监察报',
            5: '🏛️省级/市级纪委监委',
            6: '📱官方自媒体',
        }

        lines = [
            "=" * 70,
            "📋 农村集体'三资'监管 · 每日简报",
            f"📅 {datetime.now().strftime('%Y年%m月%d日')} · 共 {len(news_list)} 条最新相关信息",
            "=" * 70,
            ""
        ]

        if not news_list:
            lines.append("今日暂无相关新闻")
        else:
            for idx, news in enumerate(news_list, 1):
                label = priority_labels.get(news.priority, f'P{news.priority}')
                lines.append(f"序号：{idx}")
                lines.append(f"发布时间：{news.publish_time}")
                lines.append(f"标题：{news.title}")
                lines.append(f"简述内容：{self._generate_summary(news)}")
                lines.append(f"原文来源：{news.source}")
                lines.append(f"原文链接：{news.url}")
                lines.append("")

        lines.extend([
            "-" * 70,
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "-" * 70,
            "本简报由「三资监管·自动采集系统」生成",
            "数据来源：中央纪委国家监委网站 · 农业农村部官网 · 人民网反腐倡廉频道 · 各省/市纪委监委网站",
            "— 仅供内部参考，请以官方原文为准 —",
            "=" * 70
        ])

        return '\n'.join(lines)
