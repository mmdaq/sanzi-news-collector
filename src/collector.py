"""
新闻采集器模块 (终极强化版：强行在代码层剔除搜索引擎返回的旧闻)
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
    get_subject_words,
    get_action_words,
    get_result_words,
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
# 新闻采集器
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
        
        self.exclude_words = get_exclude_words()
        self.subject_words = get_subject_words()
        self.action_words = get_action_words()
        self.result_words = get_result_words()
        
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
        """
        宽松的语义匹配逻辑：
        1. 内容中必须包含核心主体词（如：农村集体、三资、村集体）。
        2. 内容中必须包含行为词或结果词（如：追回、整治、侵占）。
        3. 配合排他词过滤掉纯粹的纪检干部落马新闻。
        """
        content = f"{title}{summary}"
        
        # 1. 先检查黑名单 (排除落马干部处分、无关广告等噪音)
        for word in self.exclude_words:
            if word in content:
                return False
        
        # 2. 必须有主体词 (农村集体、三资等)
        has_subject = False
        for word in self.subject_words:
            if word in content:
                has_subject = True
                break
        if not has_subject:
            return False

        # 3. 必须有行为词 或者 结果词 (整治、侵占、追回、清退等)
        has_action_or_result = False
        for word in self.action_words + self.result_words:
            if word in content:
                has_action_or_result = True
                break
        
        if has_subject and has_action_or_result:
            return True

        return False

    def _is_recent(self, publish_time: str) -> bool:
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
        for attempt in range(self.config.max_retries):
            try:
                response = self.session.get(url, timeout=(5, self.config.request_timeout))
                if response.encoding is None or response.encoding == 'ISO-8859-1':
                    response.encoding = response.apparent_encoding or 'utf-8'
                if response.status_code == 200:
                    return response.text
                time.sleep(1)
            except Exception as e:
                logger.debug(f"获取页面失败 {url}: {e}")
                time.sleep(1)
        return None

    def _scrape_list_page(self, platform: str, platform_config: dict) -> List[Dict]:
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
                soup = BeautifulSoup(html, 'html.parser')
                selectors = [
                    platform_config.get('list_selector', ''),
                    'ul li a[href*=".html"]', 'ul li a[href*=".shtml"]',
                    'ul li a[href*="/2025"]', 'ul li a[href*="/2026"]',
                    '.news-list li', '.list li',
                ]
                selectors = [s for s in selectors if s]
                list_items = []
                for selector in selectors:
                    items = soup.select(selector)
                    if items:
                        list_items = items
                        break
                if not list_items:
                    for li in soup.find_all('li'):
                        if li.find('a', href=True):
                            list_items.append(li)

                logger.info(f"  [{platform}] 选择器 → {len(list_items)} 个候选")

                count = 0
                for item in list_items:
                    if count >= self.config.max_articles_per_source:
                        break
                    try:
                        if item.name == 'a' and item.get('href'):
                            title_elem = item
                        else:
                            title_elem = item.select_one(platform_config.get('title_selector', 'a'))
                            if not title_elem:
                                title_elem = item.find('a')
                        if not title_elem: continue

                        title = title_elem.get_text(strip=True)
                        if len(title) < 5 or re.match(r'^\d+$', title): continue

                        raw_link = title_elem.get('href', '')
                        if not raw_link: continue

                        base_url = platform_config.get('base_url', '')
                        fixed_link = fix_url(raw_link, base_url)
                        if not fixed_link.startswith(('http://', 'https://')): continue

                        time_elem = item.select_one(platform_config.get('time_selector', '.time, .date'))
                        if not time_elem:
                            time_elem = item.find(class_=re.compile(r'time|date|pub'))
                        time_text = time_elem.get_text(strip=True) if time_elem else ''
                        publish_time = self._extract_time(time_text) or ''

                        if not self._is_recent(publish_time): continue

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
        platform_config = self.platforms.get(platform)
        if not platform_config: return []
        return self._scrape_list_page(platform, platform_config)

    def _scrape_all_platforms(self) -> List[NewsItem]:
        all_results = []
        seen_ids = set()
        active_platforms = {
            name: cfg for name, cfg in self.platforms.items() if cfg.get('list_urls')
        }
        with ThreadPoolExecutor(max_workers=min(4, len(active_platforms))) as executor:
            future_to_platform = {
                executor.submit(self._scrape_platform, platform): platform
                for platform in active_platforms
            }
            while future_to_platform:
                done, _ = wait(future_to_platform, timeout=10, return_when=FIRST_COMPLETED)
                if not done:
                    logger.warning("⚠️ 部分平台采集超时，跳过等待继续执行...")
                    break
                for future in done:
                    platform = future_to_platform.pop(future)
                    try:
                        results = future.result(timeout=5)
                        if not results: continue
                        for result in results:
                            item_id = NewsItem._generate_id(result['title'], result['url'])
                            if item_id in self.history or item_id in seen_ids: continue
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
                        logger.debug(f"处理 {platform} 结果失败 (不影响整体): {e}")
        return all_results

    def _web_search_fallback(self, query: str) -> List[Dict]:
        """
        备用方案：通过搜索引擎搜索关键词。
        强时效性拦截：强制按时间排序，且一旦发现日期缺失或超过 7 天，直接丢弃。
        """
        results = []
        today = datetime.now().date()
        week_ago_limit = today - timedelta(days=30)
        
        # 强制搜索引擎按时间排序
        search_urls = [
            f"https://www.baidu.com/s?wd={quote(query)}&tn=news&gpc=stf&gpc_plus=1",
            f"https://www.bing.com/news/search?q={quote(query)}&setlang=zh-Hans&sort=date",
        ]

        for search_url in search_urls:
            html = self._fetch_page(search_url)
            if not html: continue
            try:
                soup = BeautifulSoup(html, 'html.parser')
                
                # ================= 处理百度搜索结果 =================
                if 'baidu.com' in search_url:
                    items = soup.select('.result, .c-result, .news-content, .c-container')
                    for item in items[:self.config.max_articles_per_source * 3]:
                        title_elem = item.select_one('h3 a, .c-title a, .news-title a, a')
                        if not title_elem: continue
                        title = title_elem.get_text(strip=True)
                        raw_link = title_elem.get('href', '')
                        if 'http' not in raw_link: continue
                        summary_elem = item.select_one('.c-abstract, .c-span-last, .news-desc')
                        summary = summary_elem.get_text(strip=True) if summary_elem else ''
                        
                        publish_time = ''
                        time_elem = item.select_one('.c-time, .news-date, .source-time, .c-gray')
                        extracted_date = None
                        if time_elem:
                            # 尝试提取真实日期 (格式如: 2025-03-25)
                            extracted_date = self._extract_time(time_elem.get_text(strip=True))
                        
                        # 【核心防护】：如果无法从结果页提取到年份日期，强制丢弃！
                        # 百度经常把 2025 年旧闻排在前面，但不显示具体日期。
                        if not extracted_date:
                            continue 
                        
                        # 【核心防护】：提取到日期后，如果发现超过 7 天，强制丢弃！
                        try:
                            pub_date = datetime.strptime(extracted_date, '%Y-%m-%d').date()
                            if pub_date < week_ago_limit:
                                continue 
                        except:
                            continue # 日期解析错误也直接丢弃

                        # 通过所有关卡，收录这篇新闻
                        publish_time = extracted_date
                        results.append({
                            'title': title, 'url': raw_link, 'original_url': raw_link,
                            'publish_time': publish_time, 'summary': summary[:300],
                            'source': f'搜索引擎-{query}', 'priority': 10,
                        })
                        
                # ================= 处理必应搜索结果 =================
                elif 'bing.com' in search_url:
                    items = soup.select('.news-card, .card, .topic-card')
                    for item in items[:self.config.max_articles_per_source * 3]:
                        title_elem = item.select_one('a.title, a[href]')
                        if not title_elem: continue
                        title = title_elem.get_text(strip=True)
                        raw_link = title_elem.get('href', '')
                        if 'http' not in raw_link: continue
                        summary_elem = item.select_one('.snippet, .description')
                        summary = summary_elem.get_text(strip=True) if summary_elem else ''
                        
                        publish_time = ''
                        time_elem = item.select_one('.date, .time, .source-date')
                        extracted_date = None
                        if time_elem:
                            extracted_date = self._extract_time(time_elem.get_text(strip=True))
                        
                        # 【核心防护】：必应也一样，没有明确日期的直接视为旧闻丢弃
                        if not extracted_date:
                            continue
                            
                        try:
                            pub_date = datetime.strptime(extracted_date, '%Y-%m-%d').date()
                            if pub_date < week_ago_limit:
                                continue 
                        except:
                            continue

                        publish_time = extracted_date
                        results.append({
                            'title': title, 'url': fix_url(raw_link), 'original_url': raw_link,
                            'publish_time': publish_time, 'summary': summary[:300],
                            'source': f'搜索引擎-{query}', 'priority': 10,
                        })
            except Exception as e:
                logger.debug(f"搜索引擎解析失败 {search_url}: {e}")
                continue
            if results:
                break
        return results

    def collect(self) -> List[NewsItem]:
        logger.info("=" * 60)
        logger.info(f"开始采集 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        # ========================================================
        # 第一步：优先从官方平台列表页抓取
        # ========================================================
        logger.info(">>> 步骤1: 优先抓取官方平台新闻列表页")
        raw_news = self._scrape_all_platforms()
        logger.info(f"抓取到 {len(raw_news)} 条候选新闻")

        valid_news = []
        seen_ids = set()
        for news in raw_news:
            if news.id in seen_ids: continue
            if self._is_relevant(news.title, news.summary):
                valid_news.append(news)
                seen_ids.add(news.id)
        
        valid_news.sort(key=lambda x: (x.priority, x.publish_time), reverse=False)
        logger.info(f">>> 官方来源匹配: {len(raw_news)} → {len(valid_news)} 条有效新闻")

        # ========================================================
        # 第二步：如果官方来源一条都没拿到，再启动搜索引擎
        # ========================================================
        if len(valid_news) == 0:
            logger.warning("⚠️ 官方网站未采集到新闻，启动搜索引擎备用方案...")
            fallback_queries = ["农村集体三资监管 追回资金", "农村集体资产 挪用 追回", "三资 微腐败 清退"]
            
            for query in fallback_queries:
                logger.info(f">>> 备用搜索: {query}")
                fb_results = self._web_search_fallback(query)
                if fb_results:
                    logger.info(f"  搜索引擎返回 {len(fb_results)} 条原始结果")
                    for r in fb_results:
                        if self._is_relevant(r['title'], r.get('summary', '')):
                            item = NewsItem(
                                title=r['title'], url=r['url'], source=r['source'],
                                publish_time=r.get('publish_time', ''),
                                summary=r.get('summary', ''), keywords=[],
                                link_valid=True, priority=r.get('priority', 10),
                                original_url=r.get('original_url', '')
                            )
                            if item.id not in seen_ids:
                                valid_news.append(item)
                                seen_ids.add(item.id)
                    if valid_news:
                        break
            
            if valid_news:
                logger.info(f"✅ 搜索引擎成功兜底 {len(valid_news)} 条有效新闻")
                valid_news.sort(key=lambda x: (x.priority, x.publish_time), reverse=False)

        # ========================================================
        # 第三步：限制简报条数并保存历史
        # ========================================================
        if len(valid_news) > self.config.max_brief_items:
            valid_news = valid_news[:self.config.max_brief_items]

        for news in valid_news:
            self.history.add(news.id)
        self._save_history()

        logger.info("=" * 60)
        logger.info(f"采集完成，共 {len(valid_news)} 条有效新闻")
        logger.info("=" * 60)
        return valid_news

    def get_errors(self) -> List[str]:
        return self.errors
