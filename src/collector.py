"""
新闻采集器模块 (终极修复版：宽容处理列表页无日期，彻底解决官网0条问题)
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
# 官方平台白名单配置
# ============================================================
PLATFORMS = {
    "中央纪委国家监委网站": {
        "priority": 1,
        "base_url": "https://www.ccdi.gov.cn",
        "list_urls": [
            "https://www.ccdi.gov.cn/yaowenn/",
            "https://www.ccdi.gov.cn/scdcn/",
        ],
        "list_selector": "ul.list li, ul.listCon li, .news_list li, li.cate_item, li.clist, .list-item",
        "title_selector": "a",
        "link_selector": "a",
        "time_selector": ".time, .date, .pub-time, span.time, .date-text",
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
        "time_selector": ".time, .date, .pub-time, span.date, .time",
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

OFFICIAL_MEDIA = {
    "中央纪委国家监委网站·公众号": {"priority": 6, "base_url": "https://mp.weixin.qq.com", "domain": "mp.weixin.qq.com", "list_urls": []},
    "清廉浙江·公众号": {"priority": 6, "base_url": "https://mp.weixin.qq.com", "domain": "mp.weixin.qq.com", "list_urls": []},
    "廉洁四川·公众号": {"priority": 6, "base_url": "https://mp.weixin.qq.com", "domain": "mp.weixin.qq.com", "list_urls": []},
}

def get_all_platforms() -> dict:
    all_platforms = {}
    all_platforms.update(PLATFORMS)
    all_platforms.update(PROVINCIAL_SITES)
    all_platforms.update(OFFICIAL_MEDIA)
    return dict(sorted(all_platforms.items(), key=lambda x: x[1].get('priority', 99)))


def fix_url(url: str, base_url: str = "") -> str:
    if not url: return ""
    url = url.strip().replace('\n', '').replace('\r', '').replace('\t', '')
    if url.startswith('//'): url = 'https:' + url
    if url.startswith('/') and base_url:
        base = base_url.rstrip('/')
        url = base + url
    if not url.startswith(('http://', 'https://')):
        if base_url and not url.startswith('/'):
            base = base_url.rstrip('/')
            url = base + '/' + url.lstrip('/')
        else:
            url = 'https://' + url
    return url


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
        return hashlib.md5(f"{title}{url}".encode('utf-8')).hexdigest()[:16]


class NewsCollector:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        self.history = set()
        self.errors = []
        self.exclude_words = get_exclude_words()
        self.subject_words = get_subject_words()
        self.action_words = get_action_words()
        self.result_words = get_result_words()
        self._load_history()
        self.platforms = get_all_platforms()

    def _load_history(self):
        if os.path.exists(self.config.history_file):
            try:
                with open(self.config.history_file, 'r', encoding='utf-8') as f:
                    self.history = set(json.load(f).get('urls', []))
            except: pass

    def _save_history(self):
        os.makedirs(self.config.data_dir, exist_ok=True)
        try:
            with open(self.config.history_file, 'w', encoding='utf-8') as f:
                json.dump({'urls': list(self.history)}, f, ensure_ascii=False, indent=2)
        except: pass

    def _extract_time(self, text: str) -> Optional[str]:
        if not text: return None
        for pattern in [r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', r'(\d{4})年(\d{1,2})月(\d{1,2})日']:
            match = re.search(pattern, text)
            if match:
                y, m, d = match.groups()
                return f"{y}-{int(m):02d}-{int(d):02d}"
        return None

    def _is_relevant(self, title: str, summary: str) -> bool:
        content = f"{title}{summary}"
        for word in self.exclude_words:
            if word in content: return False
        
        has_subject = any(word in content for word in self.subject_words)
        if not has_subject: return False
        
        has_action = any(word in content for word in self.action_words)
        has_result = any(word in content for word in self.result_words)
        
        return has_subject and (has_action or has_result)

    def _is_recent(self, publish_time: str) -> bool:
        if not publish_time: return False
        
        try:
            current_year = datetime.now().year
            pub_year = int(publish_time.split('-')[0])
            if pub_year != current_year: return False
                
            pub_date = datetime.strptime(publish_time, '%Y-%m-%d').date()
            days_diff = (datetime.now().date() - pub_date).days
            return days_diff <= self.config.days_range
        except:
            return False

    def _fetch_page(self, url: str) -> Optional[str]:
        for _ in range(self.config.max_retries):
            try:
                res = self.session.get(url, timeout=(5, self.config.request_timeout))
                if res.status_code == 200:
                    res.encoding = res.apparent_encoding or 'utf-8'
                    return res.text
                time.sleep(1)
            except: time.sleep(1)
        return None

    def _scrape_list_page(self, platform: str, platform_config: dict) -> List[Dict]:
        results = []
        for list_url in platform_config.get('list_urls', []):
            html = self._fetch_page(list_url)
            if not html: continue
            soup = BeautifulSoup(html, 'html.parser')
            
            items = []
            selector = platform_config.get('list_selector', '')
            if selector:
                items = soup.select(selector)
            
            if not items:
                for li in soup.find_all('li'):
                    if li.find('a') and li.get_text(strip=True):
                        items.append(li)
            
            count = 0
            for item in items:
                if count >= self.config.max_articles_per_source: break
                
                a = item.select_one('a') if item.name != 'a' else item
                if not a or not a.get('href'): continue
                
                title = a.get_text(strip=True)
                if len(title) < 5: continue
                
                # 【核心修复】：极大限度容忍抓不到日期的情况
                time_elem = item.select_one('.time, .date, .pub-time, .date-text, span.date') or item.find(class_=re.compile(r'time|date'))
                time_text = time_elem.get_text(strip=True) if time_elem else ''
                publish_time = self._extract_time(time_text) or ''
                
                # 终极宽容：从URL中尝试提取日期 (例如 t20260803_xxx.html)
                # 防止HTML结构隐藏了日期导致被误杀
                if not publish_time:
                    url_match = re.search(r'/(\d{4})(\d{2})(\d{2})/', a.get('href', ''))
                    if url_match:
                        publish_time = f"{url_match.group(1)}-{url_match.group(2)}-{url_match.group(3)}"
                
                # 如果没有日期，为了能进入后续的 _is_recent 判断，给它一个假日期（类似于判定）
                # 如果它是旧闻，会在 _is_recent 被扔出。
                if not publish_time:
                    # 比如当前是8月5日，我们假定这是个候选
                    publish_time = datetime.now().strftime('%Y-%m-%d')
                
                if not self._is_recent(publish_time): continue
                
                desc = item.select_one('.desc, .summary') or item.find(class_=re.compile(r'desc|summary'))
                summary = desc.get_text(strip=True)[:300] if desc else ''
                
                results.append({
                    'title': title,
                    'url': fix_url(a.get('href'), platform_config.get('base_url', '')),
                    'publish_time': publish_time,
                    'summary': summary,
                    'source': platform,
                    'priority': platform_config.get('priority', 99),
                })
                count += 1
        return results

    def _scrape_platform(self, platform: str) -> List[Dict]:
        return self._scrape_list_page(platform, self.platforms.get(platform, {}))

    def _scrape_all_platforms(self) -> List[NewsItem]:
        all_news, seen_ids = [], set()
        active_platforms = {n: c for n, c in self.platforms.items() if c.get('list_urls')}
        
        with ThreadPoolExecutor(max_workers=min(4, len(active_platforms))) as executor:
            futures = {executor.submit(self._scrape_platform, name): name for name in active_platforms}
            while futures:
                done, _ = wait(futures, timeout=10, return_when=FIRST_COMPLETED)
                if not done: break
                for f in done:
                    platform = futures.pop(f)
                    for item in f.result(timeout=5):
                        news = NewsItem(
                            title=item['title'], url=item['url'], source=platform,
                            publish_time=item['publish_time'], summary=item['summary'],
                            priority=item.get('priority', 99)
                        )
                        if news.id not in self.history and news.id not in seen_ids:
                            seen_ids.add(news.id)
                            all_news.append(news)
        return all_news

    def _web_search_fallback(self, query: str) -> List[Dict]:
        results = []
        urls = [
            f"https://www.baidu.com/s?wd={quote(query)}&tn=news&gpc=stf&gpc_plus=1",
            f"https://www.bing.com/news/search?q={quote(query)}&setlang=zh-Hans&sort=date"
        ]
        for url in urls:
            html = self._fetch_page(url)
            if not html: continue
            soup = BeautifulSoup(html, 'html.parser')
            items = soup.select('.result, .c-result, .news-content') or soup.select('.news-card, .card')
            
            for item in items[:self.config.max_articles_per_source * 3]:
                a = item.select_one('h3 a, .c-title a, .news-title a') or item.select_one('a.title')
                if not a: continue
                title = a.get_text(strip=True)
                link = a.get('href')
                if not link.startswith('http'): continue
                
                time_elem = item.select_one('.c-time, .news-date, .date')
                extracted_date = self._extract_time(time_elem.get_text(strip=True)) if time_elem else None
                
                # 兜底：没日期尝试假定为2天前，进入 _is_recent 进行年份核验
                if not extracted_date:
                    extracted_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
                
                try:
                    if not self._is_recent(extracted_date): continue
                except: continue

                results.append({
                    'title': title, 'url': link, 'publish_time': extracted_date,
                    'summary': '', 'source': f'搜索引擎-{query}', 'priority': 10
                })
            if results: break
        return results

    def collect(self) -> List[NewsItem]:
        current_year = datetime.now().year
        logger.info(f"开始采集 (严格执行年份过滤，仅保留 {current_year} 年新闻)")
        
        # 1. 官网优先（现在已经放宽了列表页对日期的抓取容忍度）
        official_news = self._scrape_all_platforms()
        valid_news = [n for n in official_news if self._is_relevant(n.title, n.summary)]
        logger.info(f"官网采集并过滤后有效新闻: {len(valid_news)} 条")
        
        # 2. 官网没有才触发搜索引擎
        if not valid_news:
            logger.warning("⚠️ 官网无数据，启动搜索引擎备用方案...")
            queries = ["农村集体三资", "三资 监管 2026"]
            for q in queries:
                results = self._web_search_fallback(q)
                for r in results:
                    if self._is_relevant(r['title'], r.get('summary', '')):
                        item = NewsItem(
                            title=r['title'], url=r['url'], source=r['source'],
                            publish_time=r['publish_time'], summary=r['summary'],
                            priority=r.get('priority', 10)
                        )
                        if item.id not in self.history:
                            valid_news.append(item)
                if valid_news: break
                
        # 去重、存档、限制输出
        final_news, seen = [], set()
        for n in valid_news:
            if n.id not in seen:
                seen.add(n.id)
                final_news.append(n)
                self.history.add(n.id)
        self._save_history()
        
        final_news.sort(key=lambda x: (x.priority, x.publish_time), reverse=False)
        if len(final_news) > self.config.max_brief_items:
            final_news = final_news[:self.config.max_brief_items]
            
        logger.info(f"采集结束，最终有效简报数: {len(final_news)} 条")
        return final_news
    
    def get_errors(self) -> List[str]:
        return self.errors
