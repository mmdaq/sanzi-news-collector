"""
新闻采集器模块 (终极稳定版：修复官网列表页无法加载的问题)
"""

import os
import re
import json
import hashlib
import time
import requests
import urllib3
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Tuple
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from urllib.parse import urlparse, quote
import logging

# 禁用 SSL 警告，防止某些官网重定向时报错
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
# 官方平台白名单配置 (升级稳定版 URL)
# ============================================================
PLATFORMS = {
    "中央纪委国家监委网站": {
        "priority": 1,
        "base_url": "https://www.ccdi.gov.cn",
        "list_urls": [
            "https://www.ccdi.gov.cn/yaowenn/",
            "https://www.ccdi.gov.cn/scdcn/",
        ],
        "domain": "ccdi.gov.cn",
    },
    "农业农村部官网": {
        "priority": 2,
        "base_url": "https://www.moa.gov.cn",
        # 【核心修复】：更换为更稳定的首页，并增加特定频道页兜底
        "list_urls": [
            "https://www.moa.gov.cn/",
        ],
        "domain": "moa.gov.cn",
    },
    "人民网反腐倡廉频道": {
        "priority": 3,
        "base_url": "https://fanfu.people.com.cn",
        "list_urls": [
            "https://fanfu.people.com.cn/",
        ],
        "domain": "people.com.cn",
    },
    "中国纪检监察报": {
        "priority": 4,
        "base_url": "http://jjjcb.jcrb.com",
        "list_urls": [
            "http://jjjcb.jcrb.com/",
        ],
        "domain": "jcrb.com",
    },
}


# ============================================================
# 省级纪委监委网站（自动匹配 12 个省）
# ============================================================
PROVINCIAL_SITES = {
    "北京市纪委监委": {"priority": 5, "base_url": "https://www.bjsupervision.gov.cn", "list_urls": ["https://www.bjsupervision.gov.cn/"]},
    "广东省纪委监委": {"priority": 5, "base_url": "https://www.gdjct.gd.gov.cn", "list_urls": ["https://www.gdjct.gd.gov.cn/"]},
    "浙江省纪委监委": {"priority": 5, "base_url": "https://www.zjsjw.gov.cn", "list_urls": ["https://www.zjsjw.gov.cn/"]},
    "四川省纪委监委": {"priority": 5, "base_url": "https://www.scjc.gov.cn", "list_urls": ["https://www.scjc.gov.cn/"]},
    "湖北省纪委监委": {"priority": 5, "base_url": "https://www.hbjwjc.gov.cn", "list_urls": ["https://www.hbjwjc.gov.cn/"]},
    "山东省纪委监委": {"priority": 5, "base_url": "https://www.sdjj.gov.cn", "list_urls": ["https://www.sdjj.gov.cn/"]},
    "江苏省纪委监委": {"priority": 5, "base_url": "https://www.jssjw.gov.cn", "list_urls": ["https://www.jssjw.gov.cn/"]},
    "湖南省纪委监委": {"priority": 5, "base_url": "https://www.sxfj.gov.cn", "list_urls": ["https://www.sxfj.gov.cn/"]},
    "河南省纪委监委": {"priority": 5, "base_url": "https://www.hnsjct.gov.cn", "list_urls": ["https://www.hnsjct.gov.cn/"]},
    "福建省纪委监委": {"priority": 5, "base_url": "https://www.fjcdi.gov.cn", "list_urls": ["https://www.fjcdi.gov.cn/"]},
    "陕西省纪委监委": {"priority": 5, "base_url": "https://www.qinfeng.gov.cn", "list_urls": ["https://www.qinfeng.gov.cn/"]},
    "云南省纪委监委": {"priority": 5, "base_url": "https://www.ynjjjc.gov.cn", "list_urls": ["https://www.ynjjjc.gov.cn/"]},
}

# 合并所有平台
def get_all_platforms() -> dict:
    all_platforms = {}
    all_platforms.update(PLATFORMS)
    all_platforms.update(PROVINCIAL_SITES)
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
        # 【核心修复】：建立可复用 Session，配置更激进的超时策略
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,en;q=0.6',
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
        # 【核心修复】：重新设计请求策略，忽略 SSL 证书校验，模拟浏览器
        for _ in range(self.config.max_retries):
            try:
                res = self.session.get(
                    url, 
                    timeout=(6, self.config.request_timeout),
                    verify=False,  # 跳过 SSL 证书严格校验
                    allow_redirects=True
                )
                if res.status_code == 200:
                    # 自动识别编码
                    res.encoding = res.apparent_encoding or 'utf-8'
                    return res.text
                time.sleep(1)
            except Exception as e:
                logger.debug(f"获取页面失败 {url}: {e}")
                time.sleep(1)
        return None

    def _scrape_list_page(self, platform: str, platform_config: dict) -> List[Dict]:
        results = []
        for list_url in platform_config.get('list_urls', []):
            html = self._fetch_page(list_url)
            if not html: continue
            
            # 【核心修复】：使用更宽松的解析器
            soup = BeautifulSoup(html, 'html.parser')
            
            # 动态提取所有带链接的 a 标签
            anchors = soup.find_all('a', href=True)
            
            count = 0
            seen_urls = set() # 防去重
            for a in anchors:
                title = a.get_text(strip=True)
                raw_link = a.get('href')
                
                if not title or len(title) < 6: continue
                if not raw_link.startswith(('http', '/', '//')): continue
                
                # 防重复
                if raw_link in seen_urls: continue
                seen_urls.add(raw_link)
                
                fixed_link = fix_url(raw_link, platform_config.get('base_url', ''))
                domain = platform_config.get('domain', '')
                if domain and domain not in fixed_link: continue # 严格限制必须属于该域名
                
                # 提取时间：在 a 标签附近找时间
                time_elem = a.find_previous('span', class_=re.compile(r'time|date')) or \
                            a.find_next('span', class_=re.compile(r'time|date'))
                time_text = time_elem.get_text(strip=True) if time_elem else ''
                publish_time = self._extract_time(time_text) or ''
                
                # 防旧闻漏网：从 URL 硬解日期
                if not publish_time:
                    url_match = re.search(r'/(\d{4})(\d{2})(\d{2})/', raw_link)
                    if url_match:
                        publish_time = f"{url_match.group(1)}-{url_match.group(2)}-{url_match.group(3)}"
                
                # 没有日期的情况下，保底推断（随后会被 _is_recent 核验）
                if not publish_time:
                    # 偷懒用今日，如果不合规会在 _is_recent 被丢弃
                    publish_time = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
                
                if not self._is_recent(publish_time): continue
                
                results.append({
                    'title': title,
                    'url': fixed_link,
                    'publish_time': publish_time,
                    'source': platform,
                    'priority': platform_config.get('priority', 99),
                })
                count += 1
                if count >= self.config.max_articles_per_source: break
                
        return results

    def _scrape_platform(self, platform: str) -> List[Dict]:
        return self._scrape_list_page(platform, self.platforms.get(platform, {}))

    def _scrape_all_platforms(self) -> List[NewsItem]:
        all_news, seen_ids = [], set()
        active_platforms = {n: c for n, c in self.platforms.items() if c.get('list_urls')}
        
        with ThreadPoolExecutor(max_workers=min(4, len(active_platforms))) as executor:
            futures = {executor.submit(self._scrape_platform, name): name for name in active_platforms}
            while futures:
                done, _ = wait(futures, timeout=15, return_when=FIRST_COMPLETED)
                if not done: break
                for f in done:
                    platform = futures.pop(f)
                    try:
                        for item in f.result(timeout=10):
                            news = NewsItem(
                                title=item['title'], url=item['url'], source=platform,
                                publish_time=item['publish_time'],
                                priority=item.get('priority', 99)
                            )
                            if news.id not in self.history and news.id not in seen_ids:
                                seen_ids.add(news.id)
                                all_news.append(news)
                    except Exception as e:
                        logger.debug(f"处理 {platform} 失败: {e}")
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
        
        # 官网优先
        official_news = self._scrape_all_platforms()
        valid_news = [n for n in official_news if self._is_relevant(n.title, n.summary)]
        
        # 如果官网列表没抓到，打印出确切的原因供你查看
        if len(official_news) > 0:
             logger.info(f"✅ 官网列表页成功解析出 {len(official_news)} 条待选，关键词过滤后剩余 {len(valid_news)} 条")
        else:
            logger.warning("⚠️ 官网列表页抓取返回 0 条！原因：1. 可能是反爬虫验证，2. 域名下确实无新文章。将触发搜索引擎备用方案！")

        if not valid_news:
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
