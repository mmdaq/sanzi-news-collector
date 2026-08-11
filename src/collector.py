"""
新闻采集器（v3 重写版）

核心策略：
1. 官方平台优先：中央纪委国家监委网站、农业农村部、省级纪委监委，
   从列表页抓取候选，抓正文确认发布时间与相关性；
2. 官方结果不足时启用搜索引擎备用方案（360 新闻 > 搜狗新闻 > 百度新闻）；
3. 时效窗口默认近 7 天，简报按"今日/昨日/近3天/近7天"分层展示；
4. 标题 + 正文双重关键词判定，强排除词直接过滤；
5. 历史去重（标题归一化 + URL 哈希），配合 GitHub Actions Cache 持久化。
"""

import hashlib
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from .config import Config
from .keywords import (
    get_action_words,
    get_exclude_words,
    get_result_words,
    get_subject_words,
    get_title_hint_pairs,
)

logger = logging.getLogger(__name__)


NAV_NOISE = [
    "您现在所在的位置", "当前位置", "设为首页", "加入收藏", "首页 >",
    "首页>>", "返回首页", "字体大小", "字号：", "分享至", "打印本页",
    "【打印】", "【关闭】", "版权所有", "主办单位", "合作单位", "ICP备",
    "网站地图", "无障碍", "工作邮箱", "客户端下载", "版权声明",
    "上一篇", "下一篇", "相关附件",
]


def clean_text(text: str) -> str:
    """清理页面导航/版权噪音。"""
    cleaned = text or ""
    for noise in NAV_NOISE:
        cleaned = cleaned.replace(noise, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :：|-—·")
    return cleaned


def strip_leading_noise(text: str) -> str:
    """剥离摘要开头的面包屑、来源、日期、字号等噪音。"""
    if not text:
        return text
    t = text
    for _ in range(10):
        orig = t
        t = t.lstrip("|｜·>» ：: ")
        # 1) 面包屑以“正文”结束 → 从“正文”后截断
        m = re.search(r"正文", t[:150])
        if m:
            t = t[m.end():].lstrip(">»·| ")
            continue
        # 2) 站点名/栏目前缀
        if re.match(r"^(?:首页|当前位置|您现在所在的位置)[>»>\s]{0,12}", t):
            t = re.sub(r"^(?:首页|当前位置|您现在所在的位置)[>»>\s]{0,12}", "", t)
            continue
        # 3) 时间残留（日期被剥掉后留下的 HH:MM:SS）
        if re.match(r"^\d{1,2}:\d{2}(?::\d{2})?\s*", t):
            t = re.sub(r"^\d{1,2}:\d{2}(?::\d{2})?\s*", "", t)
            continue
        # 4) 元信息（允许标题等前导杂字，截到“来源：xxx ”之后）
        m = re.search(r"(?:来源|日期|发布时间)[：:][^\s]{0,30}|(?:编辑|责任编辑|分享到)[：:]", t[:140])
        if m:
            t = t[m.end():].lstrip("|｜· ")
            continue
        # 5) 字号/分享按钮
        if re.match(r"^(?:【\s*小\s*中\s*大\s*】|大\s*中\s*小|字体大小[：:]?|分享\s+QQ空间\s+新浪微博\s+QQ\s+微信|QQ空间\s+新浪微博\s+QQ\s+微信)\s*", t):
            t = re.sub(r"^(?:【\s*小\s*中\s*大\s*】|大\s*中\s*小|字体大小[：:]?|分享\s+QQ空间\s+新浪微博\s+QQ\s+微信|QQ空间\s+新浪微博\s+QQ\s+微信)\s*", "", t)
            continue
        break
    return t.strip(" ：:|-—·")


# ============================================================
# 官方平台白名单（2026-08 实测可访问、可从 URL 解析日期）
# ============================================================
PLATFORMS = {
    "中央纪委国家监委网站": {
        "priority": 1,
        "base_url": "https://www.ccdi.gov.cn",
        "domain": "ccdi.gov.cn",
        "list_urls": [
            "https://www.ccdi.gov.cn/",
            "https://www.ccdi.gov.cn/yaowenn/",
            "https://www.ccdi.gov.cn/scdcn/",
        ],
    },
    "农业农村部官网": {
        "priority": 2,
        "base_url": "https://www.moa.gov.cn",
        "domain": "moa.gov.cn",
        "list_urls": [
            "https://www.moa.gov.cn/",
            "https://www.moa.gov.cn/xw/zwdt/",
            "https://www.moa.gov.cn/xw/bmdt/",
        ],
    },
    "北京市纪委监委": {
        "priority": 5,
        "base_url": "https://www.bjsupervision.gov.cn",
        "domain": "bjsupervision.gov.cn",
        "list_urls": ["https://www.bjsupervision.gov.cn/"],
    },
    "广东省纪委监委": {
        "priority": 5,
        "base_url": "https://www.gdjct.gd.gov.cn",
        "domain": "gdjct.gd.gov.cn",
        "list_urls": ["https://www.gdjct.gd.gov.cn/"],
    },
    "四川省纪委监委": {
        "priority": 5,
        "base_url": "https://www.scjc.gov.cn",
        "domain": "scjc.gov.cn",
        "list_urls": ["https://www.scjc.gov.cn/"],
    },
    "湖北省纪委监委": {
        "priority": 5,
        "base_url": "https://www.hbjwjc.gov.cn",
        "domain": "hbjwjc.gov.cn",
        "list_urls": ["https://www.hbjwjc.gov.cn/"],
    },
    "山东省纪委监委": {
        "priority": 5,
        "base_url": "https://www.sdjj.gov.cn",
        "domain": "sdjj.gov.cn",
        "list_urls": ["https://www.sdjj.gov.cn/"],
    },
    "江苏省纪委监委": {
        "priority": 5,
        "base_url": "https://www.jssjw.gov.cn",
        "domain": "jssjw.gov.cn",
        "list_urls": ["https://www.jssjw.gov.cn/"],
    },
    "湖南省纪委监委": {
        "priority": 5,
        "base_url": "https://www.sxfj.gov.cn",
        "domain": "sxfj.gov.cn",
        "list_urls": ["https://www.sxfj.gov.cn/"],
    },
    "福建省纪委监委": {
        "priority": 5,
        "base_url": "https://www.fjcdi.gov.cn",
        "domain": "fjcdi.gov.cn",
        "list_urls": ["https://www.fjcdi.gov.cn/"],
    },
    "陕西省纪委监委": {
        "priority": 5,
        "base_url": "https://www.qinfeng.gov.cn",
        "domain": "qinfeng.gov.cn",
        "list_urls": ["https://www.qinfeng.gov.cn/"],
    },
    "云南省纪委监委": {
        "priority": 5,
        "base_url": "https://www.ynjjjc.gov.cn",
        "domain": "ynjjjc.gov.cn",
        "list_urls": ["https://www.ynjjjc.gov.cn/"],
    },
}


def get_all_platforms() -> dict:
    return dict(sorted(PLATFORMS.items(), key=lambda x: x[1].get("priority", 99)))


def fix_url(url: str, base_url: str = "") -> str:
    if not url:
        return ""
    url = url.strip().replace("\n", "").replace("\r", "").replace("\t", "")
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("/") and base_url:
        url = base_url.rstrip("/") + url
    if not url.startswith(("http://", "https://")):
        if base_url:
            url = base_url.rstrip("/") + "/" + url.lstrip("/")
        else:
            url = "https://" + url
    return url


def normalize_title(title: str) -> str:
    """标题归一化：去空白/标点/多余符号，用于跨来源去重。"""
    text = re.sub(r"\s+", "", title or "")
    text = re.sub(r"[\u3000·\-\u2014_—|｜,，。！!？?：“”\"'（）()《》<>【】\[\]]", "", text)
    # 去掉常见栏目前缀，避免同一篇被不同来源转载后因前缀不同无法去重
    for prefix in ["深度关注", "记者观察", "视频", "图解", "评论", "观察",
                   "要闻", "头条", "微观察", "中国纪检监察报", "中央纪委国家监委网站"]:
        if text.startswith(prefix) and len(text) > len(prefix) + 4:
            text = text[len(prefix):].lstrip("丨|：:·")
            break
    return text[:60]


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


class NewsItem:
    def __init__(self, title: str, url: str, source: str, publish_time: str = "",
                 summary: str = "", keywords: Optional[List[str]] = None,
                 priority: int = 99, is_official: bool = False,
                 original_url: str = ""):
        self.title = title
        self.url = url
        self.original_url = original_url or url
        self.source = source
        self.publish_time = publish_time
        self.summary = summary
        self.keywords = keywords or []
        self.priority = priority
        self.is_official = is_official
        self.collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.id = NewsItem._generate_id(title, url)

    @staticmethod
    def _generate_id(title: str, url: str) -> str:
        return hashlib.md5(f"{normalize_title(title)}|{url}".encode("utf-8")).hexdigest()[:16]

    @property
    def days_ago(self) -> Optional[int]:
        d = parse_date(self.publish_time)
        if not d:
            return None
        return (datetime.now().date() - d).days


def parse_date(text: str) -> Optional[object]:
    """把多种日期文本解析为 date 对象。"""
    if not text:
        return None
    text = str(text).strip()
    today = datetime.now().date()
    # 相对时间
    m = re.search(r"(\d+)\s*分钟前", text)
    if m:
        return today
    m = re.search(r"(\d+)\s*小时前", text)
    if m:
        return today
    m = re.search(r"昨天", text)
    if m:
        return today - timedelta(days=1)
    m = re.search(r"前天", text)
    if m:
        return today - timedelta(days=2)
    m = re.search(r"今天|刚刚", text)
    if m:
        return today
    m = re.search(r"(\d+)\s*天前", text)
    if m:
        return today - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s*天前更新", text)
    if m:
        return today - timedelta(days=int(m.group(1)))
    # 完整日期
    m = re.search(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})日?", text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        except ValueError:
            return None
    # 缺年份（月-日 / 月日）
    m = re.search(r"(?:^|[^0-9])(\d{1,2})[-/月](\d{1,2})日?(?:$|[^0-9])", text)
    if m:
        try:
            return datetime(today.year, int(m.group(1)), int(m.group(2))).date()
        except ValueError:
            return None
    return None


def extract_date_from_url(url: str) -> str:
    """从 URL 路径中解出 YYYY-MM-DD（多种官网 URL 规则）。"""
    if not url:
        return ""
    patterns = [
        r"/t?(\d{4})(\d{2})(\d{2})[_.]",            # ccdi/moa: t20260811_xxx.html
        r"/(\d{4})/(\d{1,2})[-/](\d{1,2})/",       # scjc: /2026/8/11/...; 部分政府站 /2026/08-07/
        r"/html/(\d{4})/[a-zA-Z_]*(\d{2})(\d{2})/",  # ynjjjc: /html/2026/toutiao_0811/
        r"/(\d{4})(\d{2})(\d{2})/",                # 通用 /20260811/
        r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})",      # 兜底：任意位置
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            groups = m.groups()
            try:
                y, mo, d = int(groups[0]), int(groups[1]), int(groups[2])
                if 2000 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                    return f"{y:04d}-{mo:02d}-{d:02d}"
            except (ValueError, IndexError):
                continue
    return ""


class NewsCollector:
    def __init__(self, config: Config):
        self.config = config
        # requests.Session 不是线程安全的，这里按线程各自维护一个 Session
        self._local = threading.local()
        self.history = set()
        self.title_seen = set()
        self.errors = []
        self.subject_words = get_subject_words()
        self.action_words = get_action_words()
        self.result_words = get_result_words()
        self.exclude_words = get_exclude_words()
        self.title_hint_pairs = get_title_hint_pairs()
        self.platforms = get_all_platforms()
        self._load_history()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update({
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,en;q=0.6",
            })
            self._local.session = session
        return session

    # ==================== 历史记录 ====================
    def _load_history(self):
        if os.path.exists(self.config.history_file):
            try:
                with open(self.config.history_file, "r", encoding="utf-8") as f:
                    self.history = set(json.load(f).get("urls", []))
            except Exception:
                pass

    def _save_history(self):
        os.makedirs(self.config.data_dir, exist_ok=True)
        try:
            with open(self.config.history_file, "w", encoding="utf-8") as f:
                json.dump({"urls": sorted(self.history)}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ==================== 基础请求 ====================
    def _fetch(self, url: str, timeout: Optional[int] = None) -> Optional[str]:
        timeout = timeout or self.config.request_timeout
        for attempt in range(self.config.max_retries):
            try:
                res = self._session().get(url, timeout=(6, timeout), verify=False,
                                          allow_redirects=True)
                if res.status_code == 200:
                    res.encoding = res.apparent_encoding or "utf-8"
                    return res.text
            except Exception as e:
                logger.debug("获取页面失败 %s: %s", url, e)
            time.sleep(self.config.request_delay + attempt * 0.8)
        return None

    def _resolve_final_url(self, url: str) -> str:
        """解析搜索引擎跳转链接到最终地址。"""
        try:
            res = self._session().get(url, timeout=(6, self.config.request_timeout),
                                      verify=False, allow_redirects=True, stream=True)
            final = res.url
            res.close()
            return final or url
        except Exception:
            return url

    # ==================== 相关性判断 ====================
    def _title_hint(self, title: str) -> bool:
        if any(w in title for w in self.subject_words):
            return True
        if any(w in title for w in self.result_words):
            return True
        for base, cues in self.title_hint_pairs:
            if base in title and any(c in title for c in cues):
                return True
        return False

    def _score(self, text: str) -> Tuple[int, int, int]:
        s = sum(1 for w in self.subject_words if w in text)
        a = sum(1 for w in self.action_words if w in text)
        r = sum(1 for w in self.result_words if w in text)
        return s, a, r

    def _excluded(self, text: str) -> bool:
        return any(w in text for w in self.exclude_words)

    def _relevant(self, title: str, body: str, official: bool) -> bool:
        content = f"{title}\n{body}"
        if self._excluded(content):
            return False
        s, a, r = self._score(content)
        if official and self._title_hint(title):
            # 官方平台放宽：标题有线索且正文至少触及主体或行为
            return s >= 1 or a >= 1 or r >= 1
        # 搜索引擎备用方案严格判定：主体词 + 行为/结果词
        return s >= 1 and (a >= 1 or r >= 1)

    # ==================== 日期工具 ====================
    def _within_window(self, date_str: str, days_range: Optional[int] = None) -> bool:
        d = parse_date(date_str)
        if not d:
            return False
        days = (datetime.now().date() - d).days
        return -1 <= days <= (days_range if days_range is not None else self.config.days_range)

    @staticmethod
    def _extract_meta_date(soup: BeautifulSoup) -> str:
        keys = {
            "pubdate", "publishdate", "published_time", "article:published_time",
            "og:published_time", "date", "paratime", "weibo:article:create_at",
        }
        for meta in soup.find_all("meta"):
            k = (meta.get("property") or meta.get("name") or "").strip().lower()
            v = (meta.get("content") or "").strip()
            if k in keys and v:
                d = parse_date(v)
                if d:
                    return d.strftime("%Y-%m-%d")
        return ""

    @staticmethod
    def _extract_body_date(text: str) -> str:
        for marker in ["发布时间", "日期", "时间：", "时间:", "来源："]:
            idx = text.find(marker)
            if idx >= 0:
                seg = text[idx: idx + 60]
                m = re.search(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})日?", seg)
                if m:
                    try:
                        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                    except ValueError:
                        pass
        return ""

    def _extract_article_info(self, url: str, html: str) -> Tuple[str, str, str]:
        """返回 (发布日期, 正文摘要, 全文文本)。"""
        soup = BeautifulSoup(html, "html.parser")
        date_str = self._extract_meta_date(soup)
        text = clean_text(re.sub(r"\s+", " ", soup.get_text(" ", strip=True)))
        if not date_str:
            date_str = self._extract_body_date(text)
        if not date_str:
            date_str = extract_date_from_url(url)
        # 候选正文容器：按关键词命中数 + 文本长度选最优（比固定顺序更抗改版）
        full_text = ""
        best_score = (0, 0)
        for sel in [".TRS_Editor", ".TRS_UEDITOR", ".content", "#content",
                    ".article", ".detail", ".article-content", ".text", ".zw",
                    ".zw-content", ".maincontent", ".detial-box", ".content.long",
                    ".article-box", ".content-detail-context", ".content-detail-wrapper",
                    ".Custom_UnionStyle", ".main-text", "article"]:
            for el in soup.select(sel):
                txt = clean_text(re.sub(r"\s+", " ", el.get_text(" ", strip=True)))
                if len(txt) < 60:
                    continue
                s = sum(1 for w in self.subject_words if w in txt) * 2
                a = sum(1 for w in self.action_words if w in txt)
                r = sum(1 for w in self.result_words if w in txt) * 2
                score = (s + a + r, len(txt))
                if score > best_score:
                    best_score = score
                    full_text = txt
        if not full_text:
            paras = [clean_text(p.get_text(" ", strip=True)) for p in soup.find_all("p")]
            paras = [p for p in paras if len(p) >= 30]
            paras.sort(key=len, reverse=True)
            full_text = " ".join(paras[:3])
        if not full_text:
            full_text = text
        raw_full_text = full_text
        # 页面标题之后截断，去掉面包屑/导航
        h1 = soup.find("h1")
        page_title = clean_text(h1.get_text(" ", strip=True)) if h1 else ""
        if len(page_title) >= 8 and page_title in full_text:
            idx = full_text.rfind(page_title) + len(page_title)
            full_text = full_text[idx:].strip(" ：:|-—·")
        full_text = strip_leading_noise(full_text)
        if len(full_text) < 20 and len(raw_full_text) >= 20:
            full_text = raw_full_text
        summary = full_text[: self.config.brief_word_count]
        return date_str, summary, full_text[:2000]

    # ==================== 官方平台列表抓取 ====================
    def _scrape_list_page(self, platform: str, pconf: dict) -> List[dict]:
        results: List[dict] = []
        base = pconf.get("base_url", "")
        domain = pconf.get("domain", "")
        for list_url in pconf.get("list_urls", []):
            html = self._fetch(list_url)
            if not html:
                self.errors.append(f"{platform} 列表页抓取失败: {list_url}")
                continue
            soup = BeautifulSoup(html, "html.parser")
            seen = set()
            count = 0
            for a in soup.find_all("a", href=True):
                title = a.get_text(strip=True)
                raw = a.get("href", "")
                if len(title) < 6:
                    continue
                if not raw.startswith(("http", "/", "//")):
                    continue
                fixed = fix_url(raw, base)
                if domain and domain not in domain_of(fixed):
                    continue
                if fixed in seen:
                    continue
                seen.add(fixed)
                if not self._title_hint(title):
                    continue
                date_str = extract_date_from_url(fixed)
                if date_str and not self._within_window(date_str):
                    continue
                results.append({
                    "title": title,
                    "url": fixed,
                    "date": date_str,
                    "source": platform,
                    "priority": pconf.get("priority", 99),
                    "official": True,
                })
                count += 1
                if count >= self.config.max_articles_per_source:
                    break
        return results

    def _scrape_all_platforms(self) -> List[dict]:
        candidates: List[dict] = []
        with ThreadPoolExecutor(max_workers=min(self.config.max_workers, 6)) as ex:
            futures = {ex.submit(self._scrape_list_page, n, c): n
                       for n, c in self.platforms.items()}
            for fut in as_completed(futures):
                try:
                    candidates.extend(fut.result())
                except Exception as e:
                    logger.debug("平台抓取异常: %s", e)
        return candidates

    # ==================== 正文抓取与校验 ====================
    def _enrich_candidate(self, cand: dict) -> Optional[NewsItem]:
        url = cand["url"]
        html = self._fetch(url)
        if not html:
            return None
        try:
            date_str, summary, full_text = self._extract_article_info(url, html)
        except Exception:
            date_str, summary, full_text = (cand.get("date", ""), cand.get("summary", ""),
                                            cand.get("summary", ""))
        if not date_str:
            date_str = cand.get("date", "")
        if not self._within_window(date_str):
            return None
        title = cand["title"]
        if not self._relevant(title, full_text or summary, official=cand.get("official", False)):
            return None
        return NewsItem(
            title=title,
            url=url,
            source=cand["source"],
            publish_time=date_str,
            summary=summary[: self.config.brief_word_count],
            priority=cand.get("priority", 99),
            is_official=cand.get("official", False),
        )

    def _enrich(self, candidates: List[dict], limit: Optional[int] = None) -> List[NewsItem]:
        if not candidates:
            return []
        cap = limit or self.config.body_fetch_limit
        pool = candidates[:cap]
        items: List[NewsItem] = []
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as ex:
            futures = [ex.submit(self._enrich_candidate, c) for c in pool]
            for fut in as_completed(futures):
                try:
                    item = fut.result()
                    if item:
                        items.append(item)
                except Exception as e:
                    logger.debug("正文校验异常: %s", e)
        return items

    # ==================== 搜索引擎备用方案 ====================
    SEARCH_BLACKLIST_DOMAINS = {
        "baike.baidu.com", "zhihu.com", "xueqiu.com", "360doc.com",
        "doc88.com", "wenku.baidu.com", "jianshu.com", "zhuanlan.zhihu.com",
        "taobao.com", "jd.com", "douban.com",
    }

    def _filter_search_hit(self, title: str, url: str, date_str: str) -> bool:
        if self._excluded(title):
            return False
        dom = domain_of(url)
        if any(b in dom for b in self.SEARCH_BLACKLIST_DOMAINS):
            return False
        if date_str and not self._within_window(date_str):
            return False
        return True

    def _search_360(self, query: str) -> List[dict]:
        url = "https://news.so.com/ns?q=" + quote(query)
        html = self._fetch(url)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        hits = []
        for li in soup.select("ul.result li.res-list"):
            a = li.select_one("h3.g-title a") or li.select_one("a[href]")
            if not a:
                continue
            title = (a.get("title") or a.get_text(strip=True) or "").strip()
            title = re.sub(r"\s+", " ", title)
            href = a.get("href", "")
            if len(title) < 8 or not href.startswith("http"):
                continue
            date_str = ""
            span = li.select_one("span[class*=time]")
            if span:
                date_str = span.get_text(strip=True)
            d = parse_date(date_str)
            if d:
                date_str = d.strftime("%Y-%m-%d")
            if not self._filter_search_hit(title, href, date_str):
                continue
            snippet = re.sub(r"\s+", " ", li.get_text(" ", strip=True))[:150]
            hits.append({"title": title, "url": href, "date": date_str,
                         "summary": snippet, "engine": "360新闻"})
        return hits

    def _search_sogou(self, query: str) -> List[dict]:
        url = "https://news.sogou.com/news?query=" + quote(query) + "&sort=1"
        html = self._fetch(url)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        hits = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if len(title) < 8:
                continue
            if not href.startswith(("/link?url=", "http")):
                continue
            if href.startswith("/link?url="):
                final = self._resolve_final_url("https://news.sogou.com" + href)
            else:
                final = href
            date_str = extract_date_from_url(final)
            if not self._filter_search_hit(title, final, date_str):
                continue
            hits.append({"title": title, "url": final, "date": date_str,
                         "summary": "", "engine": "搜狗新闻"})
            if len(hits) >= self.config.max_articles_per_source:
                break
        return hits

    def _search_baidu(self, query: str) -> List[dict]:
        url = "https://www.baidu.com/s?tn=news&rtt=4&bsst=1&cl=2&wd=" + quote(query)
        html = self._fetch(url)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        hits = []
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if len(title) < 8 or not href.startswith("http"):
                continue
            if "baidu.com/link" in href:
                href = self._resolve_final_url(href)
            date_str = extract_date_from_url(href)
            if not self._filter_search_hit(title, href, date_str):
                continue
            hits.append({"title": title, "url": href, "date": date_str,
                         "summary": "", "engine": "百度新闻"})
            if len(hits) >= self.config.max_articles_per_source:
                break
        return hits

    def _run_searches(self) -> List[dict]:
        engines = [self._search_360, self._search_sogou, self._search_baidu]
        all_hits: List[dict] = []
        seen_urls: Set[str] = set()
        for query in self.config.search_queries:
            for engine in engines:
                try:
                    for hit in engine(query):
                        if hit["url"] in seen_urls:
                            continue
                        seen_urls.add(hit["url"])
                        all_hits.append(hit)
                except Exception as e:
                    logger.debug("搜索失败 %s: %s", query, e)
            if len(all_hits) >= self.config.max_search_results:
                break
        return all_hits

    # ==================== 主流程 ====================
    def collect(self) -> List[NewsItem]:
        logger.info("开始采集：官方平台优先（窗口 %d 天）", self.config.days_range)

        # 1) 官方平台
        official_candidates = self._scrape_all_platforms()
        logger.info("官方平台列表页候选：%d 条", len(official_candidates))
        official_news = self._enrich(official_candidates)
        official_news = self._dedupe(official_news)
        logger.info("官方平台有效新闻：%d 条", len(official_news))

        # 2) 官方不足 → 搜索引擎备用方案
        if self.config.search_enabled and len(official_news) < self.config.min_official_results:
            logger.warning("官方平台有效新闻 %d 条 < 阈值 %d，启用搜索引擎备用方案",
                           len(official_news), self.config.min_official_results)
            search_hits = self._run_searches()
            logger.info("搜索引擎候选：%d 条", len(search_hits))
            search_candidates = [
                {**h, "source": f"搜索引擎·{h['engine']}",
                 "priority": 6, "official": False}
                for h in search_hits
            ]
            search_news = self._enrich(search_candidates, limit=min(40, len(search_candidates)))
            search_news = self._dedupe(search_news)
            logger.info("搜索引擎有效新闻：%d 条", len(search_news))
        else:
            search_news = []

        # 3) 合并、去重、排序（官方优先，其次 gov.cn，再按时间新→旧）
        merged = self._dedupe(official_news + search_news)
        merged.sort(key=lambda n: (
            0 if n.is_official else (1 if domain_of(n.url).endswith(".gov.cn") else 2),
            -int(n.days_ago if n.days_ago is not None else 999),
            n.priority,
        ))
        merged = merged[: self.config.max_brief_items]

        for n in merged:
            self.history.add(n.id)
            self.title_seen.add(normalize_title(n.title))
        self._save_history()

        logger.info("采集结束，最终简报 %d 条（官方 %d / 搜索 %d）",
                    len(merged),
                    sum(1 for n in merged if n.is_official),
                    sum(1 for n in merged if not n.is_official))
        return merged

    def _dedupe(self, items: List[NewsItem]) -> List[NewsItem]:
        seen_ids: Set[str] = set()
        seen_titles: Set[str] = set()
        out: List[NewsItem] = []
        for n in items:
            if n.id in seen_ids or n.id in self.history:
                continue
            t = normalize_title(n.title)
            if t in seen_titles or t in self.title_seen:
                continue
            seen_ids.add(n.id)
            seen_titles.add(t)
            out.append(n)
        return out

    def get_errors(self) -> List[str]:
        return self.errors
