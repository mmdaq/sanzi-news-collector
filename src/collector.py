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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
# 官方平台白名单配置
# ============================================================
PLATFORMS = {
    "中央纪委国家监委网站": {
        "priority": 1,
        "base_url": "https://www.ccdi.gov.cn",
        "search_urls": [
            "https://search.ccdi.gov.cn/search",
        ],
        "params": {"site": "ccdi.gov.cn"},
        "list_selector": ".result-list li, .news-list li, .search-list li",
        "title_selector": "a",
        "link_selector": "a",
        "time_selector": ".time, .date, .pub-time",
        "desc_selector": ".desc, .summary, .abstract",
        "domain": "ccdi.gov.cn",
    },
    "农业农村部官网": {
        "priority": 2,
        "base_url": "https://www.moa.gov.cn",
        "search_urls": [
            "https://www.moa.gov.cn/search",
        ],
        "params": {"site": "moa.gov.cn"},
        "list_selector": ".list-item, .news-item, .conList-ul li",
        "title_selector": "a",
        "link_selector": "a",
        "time_selector": ".time, .date, .pub-time",
        "desc_selector": ".desc, .summary",
        "domain": "moa.gov.cn",
    },
    "人民网反腐倡廉频道": {
        "priority": 3,
        "base_url": "https://fanfu.people.com.cn",
        "search_urls": [
            "https://search.people.com.cn",
        ],
        "params": {"site": "fanfu.people.com.cn"},
        "list_selector": ".news-item, .list-item, .fl-list li",
        "title_selector": "a",
        "link_selector": "a",
        "time_selector": ".time, .date, .pubtime",
        "desc_selector": ".desc, .summary, .txt",
        "domain": "people.com.cn",
    },
    "中国纪检监察报": {
        "priority": 4,
        "base_url": "http://jjjcb.jcrb.com",
        "search_urls": [
            "http://search.jcrb.com",
        ],
        "params": {},
        "list_selector": ".news-list li, .list-con li",
        "title_selector": "a",
        "link_selector": "a",
        "time_selector": ".time, .date",
        "desc_selector": ".desc, .summary",
        "domain": "jcrb.com",
    },
}


# ============================================================
# 省级纪委监委网站（动态配置）
# ============================================================
PROVINCIAL_SITES = {
    "北京市纪委监委": {"priority": 5, "base_url": "https://www.bjsupervision.gov.cn", "domain": "bjsupervision.gov.cn"},
    "上海市纪委监委": {"priority": 5, "base_url": "https://www.shjw.gov.cn", "domain": "shjw.gov.cn"},
    "广东省纪委监委": {"priority": 5, "base_url": "https://www.gdjct.gd.gov.cn", "domain": "gdjct.gd.gov.cn"},
    "江苏省纪委监委": {"priority": 5, "base_url": "https://www.jssjw.gov.cn", "domain": "jssjw.gov.cn"},
    "浙江省纪委监委": {"priority": 5, "base_url": "https://www.zjsjw.gov.cn", "domain": "zjsjw.gov.cn"},
    "山东省纪委监委": {"priority": 5, "base_url": "https://www.sdjj.gov.cn", "domain": "sdjj.gov.cn"},
    "四川省纪委监委": {"priority": 5, "base_url": "https://www.scjc.gov.cn", "domain": "scjc.gov.cn"},
    "湖北省纪委监委": {"priority": 5, "base_url": "https://www.hbjwjc.gov.cn", "domain": "hbjwjc.gov.cn"},
    "湖南省纪委监委": {"priority": 5, "base_url": "https://www.sxfj.gov.cn", "domain": "sxfj.gov.cn"},
    "河南省纪委监委": {"priority": 5, "base_url": "https://www.hnsjct.gov.cn", "domain": "hnsjct.gov.cn"},
    "福建省纪委监委": {"priority": 5, "base_url": "https://www.fjcdi.gov.cn", "domain": "fjcdi.gov.cn"},
    "安徽省纪委监委": {"priority": 5, "base_url": "https://www.ahjjjc.gov.cn", "domain": "ahjjjc.gov.cn"},
    "河北省纪委监委": {"priority": 5, "base_url": "https://www.hebcdi.gov.cn", "domain": "hebcdi.gov.cn"},
    "辽宁省纪委监委": {"priority": 5, "base_url": "https://www.lnsupervision.gov.cn", "domain": "lnsupervision.gov.cn"},
    "陕西省纪委监委": {"priority": 5, "base_url": "https://www.qinfeng.gov.cn", "domain": "qinfeng.gov.cn"},
    "甘肃省纪委监委": {"priority": 5, "base_url": "https://www.gsjw.gov.cn", "domain": "gsjw.gov.cn"},
    "云南省纪委监委": {"priority": 5, "base_url": "https://www.ynjjjc.gov.cn", "domain": "ynjjjc.gov.cn"},
    "贵州省纪委监委": {"priority": 5, "base_url": "https://www.gzdis.gov.cn", "domain": "gzdis.gov.cn"},
    "江西省纪委监委": {"priority": 5, "base_url": "https://www.jxdi.gov.cn", "domain": "jxdi.gov.cn"},
    "广西自治区纪委监委": {"priority": 5, "base_url": "https://www.gxjjw.gov.cn", "domain": "gxjjw.gov.cn"},
    "内蒙古自治区纪委监委": {"priority": 5, "base_url": "https://www.nmgjjjc.gov.cn", "domain": "nmgjjjc.gov.cn"},
    "新疆自治区纪委监委": {"priority": 5, "base_url": "https://www.xjjw.gov.cn", "domain": "xjjw.gov.cn"},
    "山西省纪委监委": {"priority": 5, "base_url": "https://www.sxdi.gov.cn", "domain": "sxdi.gov.cn"},
    "吉林省纪委监委": {"priority": 5, "base_url": "https://www.jljw.gov.cn", "domain": "jljw.gov.cn"},
    "黑龙江省纪委监委": {"priority": 5, "base_url": "https://www.hljjj.gov.cn", "domain": "hljjj.gov.cn"},
    "海南省纪委监委": {"priority": 5, "base_url": "https://www.hncdi.gov.cn", "domain": "hncdi.gov.cn"},
    "重庆市纪委监委": {"priority": 5, "base_url": "https://www.cqjjjc.gov.cn", "domain": "cqjjjc.gov.cn"},
    "天津市纪委监委": {"priority": 5, "base_url": "https://www.tjjw.gov.cn", "domain": "tjjw.gov.cn"},
    "青海省纪委监委": {"priority": 5, "base_url": "https://www.qhjc.gov.cn", "domain": "qhjc.gov.cn"},
    "宁夏自治区纪委监委": {"priority": 5, "base_url": "https://www.nxjjjc.gov.cn", "domain": "nxjjjc.gov.cn"},
    "西藏自治区纪委监委": {"priority": 5, "base_url": "https://www.xzjjw.gov.cn", "domain": "xzjjw.gov.cn"},
    "平顶山市纪委监委": {"priority": 5, "base_url": "https://www.pdsjjw.gov.cn", "domain": "pdsjjw.gov.cn"},
    "烟台市纪委监委": {"priority": 5, "base_url": "https://www.ytjw.gov.cn", "domain": "ytjw.gov.cn"},
    "谯城区纪委监委": {"priority": 5, "base_url": "http://www.qcjjjc.gov.cn", "domain": "qcjjjc.gov.cn"},
}


# ============================================================
# 官方自媒体平台
# ============================================================
OFFICIAL_MEDIA = {
    "中央纪委国家监委网站·公众号": {"priority": 6, "base_url": "https://mp.weixin.qq.com", "domain": "mp.weixin.qq.com"},
    "清廉浙江·公众号": {"priority": 6, "base_url": "https://mp.weixin.qq.com", "domain": "mp.weixin.qq.com"},
    "廉洁四川·公众号": {"priority": 6, "base_url": "https://mp.weixin.qq.com", "domain": "mp.weixin.qq.com"},
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
    url = re.sub(r'[。，、；：！？""''（）\s]+$', '', url)
    url = re.sub(r'(?<!:)/{2,}', '/', url)
    url = url.replace(' ', '%20')
    return url


def validate_url(url: str, timeout: int = 5) -> Tuple[bool, str]:
    if not url:
        return False, url
    fixed_url = fix_url(url)
    urls_to_try = [fixed_url]
    if fixed_url.startswith('https://'):
        urls_to_try.append(fixed_url.replace('https://', 'http://'))
    if fixed_url.startswith('http://'):
        urls_to_try.append(fixed_url.replace('http://', 'https://'))
    urls_to_try = list(dict.fromkeys(urls_to_try))
    for test_url in urls_to_try:
        try:
            response = requests.head(test_url, timeout=timeout, allow_redirects=True)
            if response.status_code < 400:
                return True, test_url
        except:
            continue
    return False, fixed_url


# ============================================================
# 新闻数据模型
# ============================================================
class NewsItem:
    def __init__(self, title: str, url: str, source: str, publish_time: str = "",
                 summary: str = "", keywords: List[str] = None, link_valid: bool = True,
                 priority: int = 99, original_url: str = ""):
        self.id = self._generate_id(title, url)
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
        content = f"{title}{summary}"
        for word in self.exclude_words:
            if word in content:
                return False
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

    def _fetch_page(self, url: str, params: dict = None) -> Optional[str]:
        for attempt in range(self.config.max_retries):
            try:
                time.sleep(self.config.request_delay)
                response = self.session.get(url, params=params, timeout=self.config.request_timeout)
                if response.encoding is None or response.encoding == 'ISO-8859-1':
                    response.encoding = 'utf-8'
                if response.status_code == 200:
                    return response.text
                time.sleep(2 ** attempt)
            except:
                time.sleep(2 ** attempt)
        return None

    def _parse_search_page(self, html: str, platform: str, platform_config: dict) -> List[Dict]:
        results = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            selectors = [
                platform_config.get('list_selector', 'li'),
                '.result-list li', '.news-list li', '.search-list li',
                '.list-con li', '.article-list li',
            ]
            list_items = []
            for selector in selectors:
                items = soup.select(selector)
                if items:
                    list_items = items
                    break
            if not list_items:
                list_items = soup.find_all('li')

            for item in list_items[:self.config.max_articles_per_source]:
                try:
                    title_elem = item.select_one(platform_config.get('title_selector', 'a'))
                    if not title_elem:
                        title_elem = item.find('a')
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    if len(title) < 5:
                        continue

                    raw_link = title_elem.get('href', '')
                    if not raw_link:
                        continue

                    base_url = platform_config.get('base_url', '')
                    fixed_link = fix_url(raw_link, base_url)

                    if not fixed_link.startswith(('http://', 'https://')):
                        continue

                    time_elem = item.select_one(platform_config.get('time_selector', '.time, .date'))
                    if not time_elem:
                        time_elem = item.find(class_=re.compile(r'time|date|pub'))
                    publish_time = self._extract_time(time_elem.get_text(strip=True) if time_elem else '') or ''

                    # 时效性过滤
                    if not self._is_recent(publish_time):
                        continue

                    desc_elem = item.select_one(platform_config.get('desc_selector', '.desc, .summary'))
                    if not desc_elem:
                        desc_elem = item.find(class_=re.compile(r'desc|summary|abstract|txt'))
                    summary = desc_elem.get_text(strip=True) if desc_elem else ''

                    if self._is_relevant(title, summary):
                        results.append({
                            'title': title,
                            'url': fixed_link,
                            'original_url': raw_link,
                            'publish_time': publish_time,
                            'summary': summary[:300],
                            'source': platform,
                            'priority': platform_config.get('priority', 99),
                        })
                except:
                    continue
        except Exception as e:
            logger.error(f"解析页面失败 {platform}: {e}")
            self.errors.append(f"解析页面失败 {platform}: {str(e)}")
        return results

    def _search_platform(self, platform: str, keyword_group: List[str]) -> List[Dict]:
        platform_config = self.platforms.get(platform)
        if not platform_config:
            return []

        search_query = ' '.join(keyword_group)
        params = platform_config.get('params', {}).copy()
        params['q'] = search_query
        params.setdefault('sort', 'date')
        params.setdefault('order', 'desc')
        params.setdefault('page', '1')

        search_urls = platform_config.get('search_urls', [''])
        all_results = []
        for search_url in search_urls:
            if not search_url:
                continue
            html = self._fetch_page(search_url, params)
            if html:
                results = self._parse_search_page(html, platform, platform_config)
                if results:
                    all_results.extend(results)
                    break

        if all_results:
            for r in all_results:
                r['keywords'] = keyword_group
            logger.info(f"  [{platform}] 找到 {len(all_results)} 条")
        return all_results

    def _search_all_platforms(self, keyword_groups: List[List[str]]) -> List[NewsItem]:
        all_results = []
        seen_ids = set()

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            futures = []
            for platform in self.platforms.keys():
                for keyword_group in keyword_groups:
                    futures.append(executor.submit(self._search_platform, platform, keyword_group))

            for future in as_completed(futures):
                try:
                    results = future.result()
                    for result in results:
                        item_id = self._generate_id(result['title'], result['url'])
                        if item_id in self.history or item_id in seen_ids:
                            continue
                        seen_ids.add(item_id)

                        is_valid, working_url = validate_url(result['url'], self.config.link_verify_timeout)

                        news_item = NewsItem(
                            title=result['title'],
                            url=working_url if working_url else result['url'],
                            source=result['source'],
                            publish_time=result.get('publish_time', ''),
                            summary=result.get('summary', ''),
                            keywords=result.get('keywords', []),
                            link_valid=is_valid,
                            priority=result.get('priority', 99),
                            original_url=result.get('original_url', '')
                        )
                        all_results.append(news_item)
                except Exception as e:
                    logger.error(f"处理搜索结果失败: {e}")
                    self.errors.append(f"搜索失败: {str(e)}")

        return all_results

    def collect(self) -> List[NewsItem]:
        logger.info("=" * 60)
        logger.info(f"开始采集 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        all_news = []
        strategy_used = "P0"

        # 策略1: P0
        logger.info(">>> 策略1: P0高优先级搜索")
        p0_news = self._search_all_platforms(HIGH_PRIORITY_KEYWORDS)
        all_news.extend(p0_news)
        logger.info(f"P0 采集到 {len(p0_news)} 条")

        # 策略2: P1
        if len(all_news) < self.config.min_news_threshold:
            logger.info(f">>> 策略2: 补充P1 (当前 {len(all_news)} 条)")
            strategy_used = "P1"
            p1_news = self._search_all_platforms(MEDIUM_PRIORITY_KEYWORDS)
            existing_ids = {n.id for n in all_news}
            for news in p1_news:
                if news.id not in existing_ids:
                    all_news.append(news)
                    existing_ids.add(news.id)
            logger.info(f"P1 补充 {len(p1_news)} 条")

        # 策略3: P2
        if len(all_news) < self.config.min_news_threshold:
            logger.info(f">>> 策略3: 补充P2 (当前 {len(all_news)} 条)")
            strategy_used = "P2"
            p2_news = self._search_all_platforms(LOW_PRIORITY_KEYWORDS)
            existing_ids = {n.id for n in all_news}
            for news in p2_news:
                if news.id not in existing_ids:
                    all_news.append(news)
                    existing_ids.add(news.id)
            logger.info(f"P2 补充 {len(p2_news)} 条")

        # 策略4: 降级
        if len(all_news) < 1:
            logger.info(f">>> 策略4: 最终降级 (当前 {len(all_news)} 条)")
            strategy_used = "FALLBACK"
            fallback_news = self._search_all_platforms(FALLBACK_KEYWORDS)
            existing_ids = {n.id for n in all_news}
            for news in fallback_news:
                if news.id not in existing_ids:
                    all_news.append(news)
                    existing_ids.add(news.id)
            logger.info(f"FALLBACK 补充 {len(fallback_news)} 条")

        # 过滤无效链接
        valid_news = [n for n in all_news if n.url and n.url.startswith(('http://', 'https://'))]

        # 按优先级排序
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
