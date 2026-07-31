"""
新闻采集器模块
"""

import os
import re
import json
import hashlib
import time
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Tuple
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from urllib.parse import urlparse, quote
import logging

from .config import Config
from .keywords import (
    get_all_keywords,
    get_include_words,
    get_exclude_words,
    HIGH_PRIORITY_KEYWORDS,
    MEDIUM_PRIORITY_KEYWORDS,
    LOW_PRIORITY_KEYWORDS,
    FALLBACK_KEYWORDS,
)

logger = logging.getLogger(__name__)


# ============================================================
# 官方平台白名单配置 — 直接抓取新闻列表页
# ============================================================
PLATFORMS = {
    "中央纪委国家监委网站": {
        "priority": 1,
        "base_url": "https://www.ccdi.gov.cn",
        "list_urls": [
            "https://www.ccdi.gov.cn/yaowenn/",
            "https://www.ccdi.gov.cn/scdcn/",
        ],
        "list_selector": "ul.list li, ul.listCon li, .news_list li, li.cate_item, li.clist",
        "title_selector": "a",
        "link_selector": "a",
        "time_selector": ".time, .date, .pub-time, span.time",
        "desc_selector": ".desc, .summary, .abstract, p.desc",
        "domain": "ccdi.gov.cn",
    },
    "农业农村部官网": {
        "priority": 2,
        "base_url": "https://www.moa.gov.cn",
        "list_urls": [
            "https://www.moa.gov.cn/xw/zwdt/",
            "https://www.moa.gov.cn/",
        ],
        "list_selector": "ul.news-list li, .list-item, .news-item, .conList-ul li, li.common-list-item",
        "title_selector": "a",
        "link_selector": "a",
        "time_selector": ".time, .date, .pub-time, span.date",
        "desc_selector": ".desc, .summary, p.desc",
        "domain": "moa.gov.cn",
    },
    "人民网反腐倡廉频道": {
        "priority": 3,
        "base_url": "https://fanfu.people.com.cn",
        "list_urls": [
            "https://fanfu.people.com.cn/",
            "https://fanfu.people.com.cn/GB/143349/index.html",
        ],
        "list_selector": ".news-item, .list-item, .fl-list li, ul li.news_li, .ej_list_box li",
        "title_selector": "a",
        "link_selector": "a",
        "time_selector": ".time, .date, .pubtime, em.time",
        "desc_selector": ".desc, .summary, .txt, p.desc",
        "domain": "people.com.cn",
    },
    "中国纪检监察报": {
        "priority": 4,
        "base_url": "http://jjjcb.jcrb.com",
        "list_urls": [
            "http://jjjcb.jcrb.com/",
        ],
        "list_selector": ".news-list li, .list-con li, ul li.news-item",
        "title_selector": "a",
        "link_selector": "a",
        "time_selector": ".time, .date, span.time",
        "desc_selector": ".desc, .summary, p.desc",
        "domain": "jcrb.com",
    },
}


# ============================================================
# 省级纪委监委网站（动态配置）
# ============================================================
PROVINCIAL_SITES = {
    "北京市纪委监委": {"priority": 5, "base_url": "https://www.bjsupervision.gov.cn", "domain": "bjsupervision.gov.cn", "list_urls": ["https://www.bjsupervision.gov.cn/"]},
    "广东省纪委监委": {"priority": 5, "base_url": "https://www.gdjct.gd.gov.cn", "domain": "gdjct.gd.gov.cn", "list_urls": ["https://www.gdjct.gd.gov.cn/"]},
    "浙江省纪委监委": {"priority": 5, "base_url": "https://www.zjsjw.gov.cn", "domain": "zjsjw.gov.cn", "list_urls": ["https://www.zjsjw.gov.cn/"]},
    "四川省纪委监委": {"priority": 5, "base_url": "https://www.scjc.gov.cn", "domain": "scjc.gov.cn", "list_urls": ["https://www.scjc.gov.cn/"]},
    "湖北省纪委监委": {"priority": 5, "base_url": "https://www.hbjwjc.gov.cn", "domain": "hbjwjc.gov.cn", "list_urls": ["https://www.hbjwjc.gov.cn/"]},
    "山东省纪委监委": {"priority": 5, "base_url": "https://www.sdjj.gov.cn", "domain": "sdjj.gov.cn", "list_urls": ["https://www.sdjj.gov.cn/"]},
    "江苏省纪委监委": {"priority": 5, "base_url": "https://www.jssjw.gov.cn", "domain": "jssjw.gov.cn", "list_urls": ["https://www.jssjw.gov.cn/"]},
    "湖南省纪委监委": {"priority": 5, "base_url": "https://www.sxfj.gov.cn", "domain": "sxfj.gov.cn", "list_urls": ["https://www.sxfj.gov.cn/"]},
    "河南省纪委监委": {"priority": 5, "base_url": "https://www.hnsjct.gov.cn", "domain": "hnsjct.gov.cn", "list_urls": ["https://www.hnsjct.gov.cn/"]},
    "福建省纪委监委": {"priority": 5, "base_url": "https://www.fjcdi.gov.cn", "domain": "fjcdi.gov.cn", "list_urls": ["https://www.fjcdi.gov.cn/"]},
    "陕西省纪委监委": {"priority": 5, "base_url": "https://www.qinfeng.gov.cn", "domain": "qinfeng.gov.cn", "list_urls": ["https://www.qinfeng.gov.cn/"]},
    "云南省纪委监委": {"priority": 5, "base_url": "https://www.ynjjjc.gov.cn", "domain": "ynjjjc.gov.cn", "list_urls": ["https://www.ynjjjc.gov.cn/"]},
}


# ============================================================
# 官方自媒体平台
# ============================================================
OFFICIAL_MEDIA = {
    "中央纪委国家监委网站·公众号": {"priority": 6, "base_url": "https://mp.weixin.qq.com", "domain": "mp.weixin.qq.com", "list_urls": []},
    "清廉浙江·公众号": {"priority": 6, "base_url": "https://mp.weixin.qq.com", "domain": "mp.weixin.qq.com", "list_urls": []},
    "廉洁四川·公众号": {"priority": 6, "base_url": "https://mp.weixin.qq.com", "domain": "mp.weixin.qq.com", "list_urls": []},
}


# ============================================================
# 合并所有平台
# ============================================================
def get_all_platforms() -> dict:
    all_platforms = {}
    all_platforms.update(PLATFORMS)
    all_platforms.update(PROVINCIAL_SITES)
    all_platforms.update(OFFICIAL_MEDIA)
    return dict(sorted(all_platforms.items(), key=lambda x: x[1].get('priority', 99)))


# ============================================================
# URL修复工具
# ============================================================
def fix_url(url: str, base_url: str = "") -> str:
    if not url:
        return ""
    url = url.strip().replace('\n', '').replace('\r', '').replace('\t', '')
    if url.startswith('//'):
        url = 'https:' + url
    if url.startswith('/') and base_url:
        base = base_url.rstrip('/')
        url = base + url
    if not url.startswith(('http://', 'https://')):
        if base_url and not url.startswith('/'):
            base = base_url.rstrip('/')
            url = base + '/' + url.lstrip('/')
        else:
            url = 'https://' + url
    try:
        parsed = urlparse(url)
        if parsed.netloc:
            path_parts = parsed.path.split('/')
            encoded_parts = []
            for part in path_parts:
                if part and not re.match(r'^[a-zA-Z0-9\-_.~%]+$', part):
                    part = quote(part, safe='')
                encoded_parts.append(part)
            encoded_path = '/'.join(encoded_parts)
            if parsed.query:
                url = f"{parsed.scheme}://{parsed.netloc}{encoded_path}?{parsed.query}"
            else:
                url = f"{parsed.scheme}://{parsed.netloc}{encoded_path}"
    except:
        pass
    url = re.sub(r'[。，、；：！？\"\"''（）\\s]+$', '', url)
    url = re.sub(r'(?<!:)/{2,}', '/', url)
    url = url.replace(' ', '%20')
    return url


# ============================================================
# 新闻数据模型
# ============================================================
class NewsItem:
    def __init__(self, title: str, url: str, source: str, publish_time: str = "",
                 summary: str = "", keywords: List[str] = None, link_valid: bool = True,
                 priority: int = 99, original_url: str = ""):
        self.id = NewsItem._generate_id(title, url)
        self.title = title
        self.url = url
        self.original_url = original_url or url
        self.source = source
        self.publish_time = publish_time or datetime.now().strftime('%Y-%m-%d')
        self.summary = summary
        self.keywords = keywords or []
        self.link_valid = link_valid
        self.priority = priority
        self.collected_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    @staticmethod
    def _generate_id(title: str, url: str) -> str:
        content = f"{title}{url}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'original_url': self.original_url,
            'source': self.source,
            'publish_time': self.publish_time,
            'summary': self.summary,
            'keywords': self.keywords,
            'link_valid': self.link_valid,
            'priority': self.priority,
            'collected_at': self.collected_at,
        }


# ============================================================
# 新闻采集器 — 直接抓取新闻列表页 + 关键词过滤
# ============================================================
class NewsCollector:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        self.history: Set[str] = set()
        self._load_history()
        self.errors: List[str] = []
        self.include_words = get_include_words()
        self.exclude_words = get_exclude_words()
        self.platforms = get_all_platforms()

    def _load_history(self):
        if not os.path.exists(self.config.history_file):
            return
        try:
            with open(self.config.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.history = set(data.get('urls', []))
                logger.info(f"加载历史记录: {len(self.history)} 条")
        except:
            pass

    def _save_history(self):
        os.makedirs(self.config.data_dir, exist_ok=True)
        try:
            with open(self.config.history_file, 'w', encoding='utf-8') as f:
                json.dump({'urls': list(self.history)}, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _extract_time(self, text: str) -> Optional[str]:
        if not text:
            return None
        patterns = [
            r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
            r'(\d{4})年(\d{1,2})月(\d{1,2})日',
            r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})',
            r'(\d{4})\.(\d{1,2})\.(\d{1,2})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    groups = match.groups()
                    if len(groups) == 3:
                        if len(groups[0]) == 4:
                            y, m, d = groups
                        elif len(groups[2]) == 4:
                            y, m, d = groups[2], groups[1], groups[0]
                        else:
                            continue
                        return f"{y}-{int(m):02d}-{int(d):02d}"
                except:
                    pass
        return None

    def _is_relevant(self, title: str, summary: str) -> bool:
        """检查内容是否与三资监管相关（包含关键词）"""
        content = f"{title}{summary}"
        # 先过滤排除词
        for word in self.exclude_words:
            if word in content:
                return False
        # 再匹配包含词
        for word in self.include_words:
            if word in content:
                return True
        return False

    def _is_recent(self, publish_time: str) -> bool:
        """检查是否在指定天数内"""
        if not publish_time:
            return True
        try:
            pub_date = datetime.strptime(publish_time, '%Y-%m-%d')
            today = datetime.now().date()
            days_diff = (today - pub_date.date()).days
            return days_diff <= self.config.days_range
        except:
            return True

    def _fetch_page(self, url: str) -> Optional[str]:
        """获取页面HTML (优化版：成功时不等待，失败才等待重试)"""
        for attempt in range(self.config.max_retries):
            try:
                response = self.session.get(url, timeout=(5, self.config.request_timeout))
                # 自动检测编码
                if response.encoding is None or response.encoding == 'ISO-8859-1':
                    # 优先从 Content-Type 和 HTML meta 推断
                    response.encoding = response.apparent_encoding or 'utf-8'
                if response.status_code == 200:
                    return response.text
                time.sleep(1) # 状态码不对，短暂休息后重试
            except Exception as e:
                logger.debug(f"获取页面失败 {url}: {e}")
                time.sleep(1) # 发生异常才 Sleep 等重试
        return None

    def _scrape_list_page(self, platform: str, platform_config: dict) -> List[Dict]:
        """抓取某个平台的新闻列表页，提取所有文章条目"""
        results = []
        list_urls = platform_config.get('list_urls', [])

        if not list_urls:
            return results

        for list_url in list_urls:
            logger.info(f"  [{platform}] 抓取列表页: {list_url}")
            html = self._fetch_page(list_url)
            if not html:
                logger.warning(f"  [{platform}] 列表页无法访问: {list_url}")
                continue

            try:
                # 【优化点】：使用纯 Python 解析器，规避 Linux 环境可能存在的解析器依赖卡顿问题
                soup = BeautifulSoup(html, 'html.parser')

                # 尝试多种选择器查找列表项
                selectors = [
                    platform_config.get('list_selector', ''),
                    'ul li a[href*=".html"]',
                    'ul li a[href*=".shtml"]',
                    'ul li a[href*="/2025"]',
                    'ul li a[href*="/2026"]',
                    '.news-list li',
                    '.list li',
                ]
                selectors = [s for s in selectors if s]  # 去空

                list_items = []
                selector_used = None
                for selector in selectors:
                    items = soup.select(selector)
                    if items:
                        list_items = items
                        selector_used = selector
                        break

                if not list_items:
                    # 兜底：提取所有包含链接的li
                    for li in soup.find_all('li'):
                        if li.find('a', href=True):
                            list_items.append(li)
                    selector_used = "li > a[href]"

                logger.info(f"  [{platform}] 选择器 '{selector_used}' → {len(list_items)} 个候选")

                count = 0
                for item in list_items:
                    if count >= self.config.max_articles_per_source:
                        break

                    try:
                        # 提取标题和链接
                        # 如果匹配到的就是 <a> 本身，直接用它
                        if item.name == 'a' and item.get('href'):
                            title_elem = item
                        else:
                            title_elem = item.select_one(platform_config.get('title_selector', 'a'))
                            if not title_elem:
                                title_elem = item.find('a')
                        if not title_elem:
                            continue

                        title = title_elem.get_text(strip=True)
                        # 跳过过短或无意义的标题
                        if len(title) < 5 or re.match(r'^\d+$', title):
                            continue

                        raw_link = title_elem.get('href', '')
                        if not raw_link:
                            continue

                        base_url = platform_config.get('base_url', '')
                        fixed_link = fix_url(raw_link, base_url)

                        if not fixed_link.startswith(('http://', 'https://')):
                            continue

                        # 提取时间
                        time_elem = item.select_one(platform_config.get('time_selector', '.time, .date'))
                        if not time_elem:
                            time_elem = item.find(class_=re.compile(r'time|date|pub'))
                        time_text = time_elem.get_text(strip=True) if time_elem else ''
                        publish_time = self._extract_time(time_text) or ''

                        # 时效性过滤
                        if not self._is_recent(publish_time):
                            continue

                        # 提取摘要
                        desc_elem = item.select_one(platform_config.get('desc_selector', '.desc, .summary'))
                        if not desc_elem:
                            desc_elem = item.find(class_=re.compile(r'desc|summary|abstract|txt'))
                        summary = desc_elem.get_text(strip=True) if desc_elem else ''

                        results.append({
                            'title': title,
                            'url': fixed_link,
                            'original_url': raw_link,
                            'publish_time': publish_time,
                            'summary': summary[:300],
                            'source': platform,
                            'priority': platform_config.get('priority', 99),
                        })
                        count += 1

                    except Exception:
                        continue

            except Exception as e:
                logger.error(f"解析列表页失败 {platform}: {e}")
                self.errors.append(f"解析列表页失败 {platform}: {str(e)}")

        return results

    def _scrape_platform(self, platform: str) -> List[Dict]:
        """抓取单个平台的所有新闻条目（不经过关键词过滤）"""
        platform_config = self.platforms.get(platform)
        if not platform_config:
            return []
        return self._scrape_list_page(platform, platform_config)

    def _scrape_all_platforms(self) -> List[NewsItem]:
        """并发抓取所有平台 (优化版：防止Action卡死转圈)"""
        all_results = []
        seen_ids = set()

        # 只抓取有 list_urls 的平台
        active_platforms = {
            name: cfg for name, cfg in self.platforms.items()
            if cfg.get('list_urls')
        }

        # 控制最大并发数为 4 (减少极端情况下Action内存或网络带宽被打满的几率)
        with ThreadPoolExecutor(max_workers=min(4, len(active_platforms))) as executor:
            future_to_platform = {
                executor.submit(self._scrape_platform, platform): platform
                for platform in active_platforms
            }

            # 循环等待任务完成，一有任务完成就立刻处理，不等待其他慢任务
            while future_to_platform:
                # wait 设置超时 10 秒，防止某个线程死锁导致Action卡死
                done, _ = wait(
                    future_to_platform, 
                    timeout=10, 
                    return_when=FIRST_COMPLETED
                )
                
                # 如果 wait 超时返回空，说明有线程卡住了，我们强制跳出循环
                if not done:
                    logger.warning("⚠️ 部分平台采集超时，跳过等待继续执行...")
                    break

                for future in done:
                    platform = future_to_platform.pop(future)
                    try:
                        results = future.result(timeout=5) # result设置超时防止意外阻塞
                        if not results:
                            continue
                            
                        for result in results:
                            item_id = NewsItem._generate_id(result['title'], result['url'])
                            if item_id in self.history or item_id in seen_ids:
                                continue
                            seen_ids.add(item_id)

                            news_item = NewsItem(
                                title=result['title'],
                                url=result['url'],
                                source=result['source'],
                                publish_time=result.get('publish_time', ''),
                                summary=result.get('summary', ''),
                                keywords=[],
                                link_valid=True,
                                priority=result.get('priority', 99),
                                original_url=result.get('original_url', '')
                            )
                            all_results.append(news_item)
                    except Exception as e:
                        # 捕获所有并发异常，绝不报错退出，只打印日志
                        logger.debug(f"处理 {platform} 结果失败 (不影响整体): {e}")

        return all_results

    def _web_search_fallback(self, query: str) -> List[Dict]:
        """备用方案：通过搜索引擎搜索关键词"""
        results = []
        search_urls = [
            f"https://www.baidu.com/s?wd={quote(query)}&tn=news",
            f"https://www.bing.com/news/search?q={quote(query)}&setlang=zh-Hans",
        ]

        for search_url in search_urls:
            html = self._fetch_page(search_url)
            if not html:
                continue

            try:
                soup = BeautifulSoup(html, 'html.parser')

                # 尝试从搜索结果中提取
                if 'baidu.com' in search_url:
                    items = soup.select('.result, .c-result, .news-content, .c-container')
                    for item in items[:self.config.max_articles_per_source]:
                        title_elem = item.select_one('h3 a, .c-title a, .news-title a, a')
                        if not title_elem:
                            continue
                        title = title_elem.get_text(strip=True)
                        raw_link = title_elem.get('href', '')
                        # 百度会包装链接，需要提取真实URL
                        if 'http' not in raw_link:
                            continue
                        summary_elem = item.select_one('.c-abstract, .c-span-last, .news-desc')
                        summary = summary_elem.get_text(strip=True) if summary_elem else ''
                        results.append({
                            'title': title,
                            'url': raw_link,
                            'original_url': raw_link,
                            'publish_time': '',
                            'summary': summary[:300],
                            'source': f'搜索引擎-{query}',
                            'priority': 10,
                        })
                elif 'bing.com' in search_url:
                    items = soup.select('.news-card, .card, .topic-card')
                    for item in items[:self.config.max_articles_per_source]:
                        title_elem = item.select_one('a.title, a[href]')
                        if not title_elem:
                            continue
                        title = title_elem.get_text(strip=True)
                        raw_link = title_elem.get('href', '')
                        if 'http' not in raw_link:
                            continue
                        summary_elem = item.select_one('.snippet, .description')
                        summary = summary_elem.get_text(strip=True) if summary_elem else ''
                        results.append({
                            'title': title,
                            'url': fix_url(raw_link),
                            'original_url': raw_link,
                            'publish_time': '',
                            'summary': summary[:300],
                            'source': f'搜索引擎-{query}',
                            'priority': 10,
                        })
            except Exception as e:
                logger.debug(f"搜索引擎解析失败 {search_url}: {e}")
                continue

            if results:
                break  # 有一个搜索引擎出结果就停止

        return results

    def collect(self) -> List[NewsItem]:
        logger.info("=" * 60)
        logger.info(f"开始采集 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        logger.info(">>> 步骤1: 抓取所有平台新闻列表页")
        raw_news = self._scrape_all_platforms()
        logger.info(f"抓取到 {len(raw_news)} 条原始新闻")

        # 关键词过滤：使用 _is_relevant（匹配任意一个包含词即可）
        strategy_used = "关键词过滤"
        matched_news = []
        seen_ids = set()
        for news in raw_news:
            if news.id in seen_ids:
                continue
            if self._is_relevant(news.title, news.summary):
                matched_news.append(news)
                seen_ids.add(news.id)

        logger.info(f">>> 关键词过滤: {len(raw_news)} → {len(matched_news)} 条")

        # 如果关键词过滤命中太少，启用搜索引擎备用方案获取更精准的结果
        if len(matched_news) < self.config.min_news_threshold:
            logger.warning(f"⚠️ 关键词过滤仅命中 {len(matched_news)} 条，启动搜索引擎备用方案")
            fallback_queries = ["农村集体三资监管 通报", "农村集体资产 蝇贪蚁腐", "三资 微腐败 整治"]

            fb_news = []
            for query in fallback_queries:
                logger.info(f">>> 备用搜索: {query}")
                fb_results = self._web_search_fallback(query)
                if fb_results:
                    logger.info(f"  搜索引擎返回 {len(fb_results)} 条结果")
                    for r in fb_results:
                        # 搜索引擎的结果直接就是相关的，但也要过一下关键词
                        content = f"{r['title']} {r.get('summary', '')}"
                        if self._is_relevant(r['title'], r.get('summary', '')):
                            item = NewsItem(
                                title=r['title'],
                                url=r['url'],
                                source=r['source'],
                                publish_time=r.get('publish_time', ''),
                                summary=r.get('summary', ''),
                                keywords=[],
                                link_valid=True,
                                priority=r.get('priority', 10),
                                original_url=r.get('original_url', '')
                            )
                            if item.id not in seen_ids:
                                fb_news.append(item)
                                seen_ids.add(item.id)
                    if fb_news:
                        break

            if fb_news:
                logger.info(f"搜索引擎备用方案获取 {len(fb_news)} 条")
                matched_news = fb_news
                strategy_used = "搜索引擎"
            elif not matched_news:
                # 真的什么都没有，保留原始抓取结果（但会标记）
                logger.warning("⚠️ 所有方案均未命中，保留原始抓取结果")
                matched_news = raw_news
                strategy_used = "全部保留(未过滤)"

        # 过滤并排序
        valid_news = [n for n in matched_news if n.url and n.url.startswith(('http://', 'https://'))]
        valid_news.sort(key=lambda x: (x.priority, x.publish_time), reverse=False)

        # 限制数量
        if len(valid_news) > self.config.max_brief_items:
            valid_news = valid_news[:self.config.max_brief_items]

        # 更新历史
        for news in valid_news:
            self.history.add(news.id)
        self._save_history()

        logger.info("=" * 60)
        logger.info(f"采集完成，共 {len(valid_news)} 条有效新闻 (策略: {strategy_used})")
        logger.info("=" * 60)

        return valid_news

    def get_errors(self) -> List[str]:
        return self.errors
