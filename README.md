# 农村集体"三资"监管 · 新闻自动采集简报系统

> 每日自动采集农村集体资金、资产、资源（三资）监管领域的最新新闻，生成简报发送至指定邮箱。
> 优先从官方纪委、农业农村部等平台抓取；官方当日信息不足时，自动启用搜索引擎备用方案；
> 当天没有相关新闻时，自动放宽到近一周。

## ✨ 功能特性

- 🏛️ **官方平台优先**：中央纪委国家监委网站、农业农村部官网、10 个省级纪委监委网站（均实测可访问）
- 🔍 **搜索引擎备用**：官方有效结果不足 2 条时，自动启用 360 新闻 / 搜狗新闻 / 百度新闻
- 🎯 **智能筛选**：标题 + 正文双重关键词判定，精准锁定"三资"监管、案例通报、追回资金、基层"微腐败"等
- 📅 **时效分层**：按 今日 → 昨日 → 近3天 → 近7天 分层展示；当天没有时自动放宽到近一周
- 🚫 **强排除词**：过滤招商、采购公告、人事任免、纯国际新闻等无关内容
- 🔗 **链接验证**：正文级校验，提取真实发布时间与内容摘要
- 📧 **邮件简报**：HTML 简报（手机友好），来源、时效、链接一目了然
- 🗂️ **跨日去重**：标题归一化去重 + GitHub Actions Cache 持久化历史，避免旧闻天天重复
- ⚙️ **自动部署**：GitHub Actions 每日 8:30（北京时间）自动运行

## 📦 快速开始

### 1. 更新你的仓库

把本项目 `main.py`、`src/`、`.github/workflows/daily_brief.yml` 等文件覆盖到你现有的
`sanzi-news-collector` 仓库并提交推送。

### 2. 配置 GitHub Secrets

在仓库 Settings → Secrets and variables → Actions 中添加：

| Secret 名称 | 说明 |
|------------|------|
| `SMTP_SERVER` | SMTP服务器（如 smtp.qq.com） |
| `SMTP_PORT` | SMTP端口（如 465） |
| `SENDER_EMAIL` | 发送邮箱 |
| `SENDER_PASSWORD` | 邮箱授权码（不是登录密码） |
| `RECEIVER_EMAIL` | 接收邮箱（多个用英文逗号分隔） |

### 3. 手动触发运行

进入 Actions 页面，选择 "每日三资监管简报"，点击 "Run workflow" 手动触发测试。

## ⚙️ 可选环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MIN_OFFICIAL_RESULTS` | `2` | 官方有效结果少于该值 → 启用搜索引擎备用方案 |
| `SEARCH_ENABLED` | `true` | 是否启用搜索引擎备用方案 |
| `SEARCH_QUERIES` | 内置 6 组 | 自定义搜索关键词，用 `\|` 分隔 |
| `DAYS_RANGE` | `7` | 时效窗口（天），当天没有时自动放宽到这里 |
| `SEND_EMPTY_EMAIL` | `true` | 没有新闻时是否仍发送"今日无相关新闻"简报 |
| `MAX_BRIEF_ITEMS` | `30` | 简报最多条数 |
| `MAX_ARTICLES_PER_SOURCE` | `12` | 每个来源最多候选条数 |
| `DRY_RUN` | `false` | 调试：只生成简报，不发送邮件 |

本地运行支持 `.env` 文件（参考 `.env.example`），环境变量优先级更高。

## 📂 项目结构

```
sanzi-news-collector/
├── .github/workflows/daily_brief.yml   # GitHub Actions 定时任务
├── src/
│   ├── config.py                       # 配置管理（支持 .env）
│   ├── keywords.py                     # 关键词词库（主体/行为/结果/强排除）
│   ├── collector.py                    # 新闻采集器（官方 + 搜索备用）
│   ├── brief_generator.py              # 简报生成器（HTML/文本）
│   ├── email_sender.py                 # 邮件发送
│   ├── health_check.py                 # 健康检查
│   └── keyword_stats.py                # 关键词统计
├── main.py                             # 主程序入口
├── requirements.txt
├── .env.example
└── README.md
```

## 🔧 自定义数据源

编辑 `src/collector.py` 中的 `PLATFORMS`，按以下格式增删官方平台：

```python
"某省纪委监委": {
    "priority": 5,                    # 1=中纪委 2=农业农村部 5=省级纪委 6=搜索
    "base_url": "https://xxx.gov.cn",
    "domain": "xxx.gov.cn",           # 只保留该域名下的链接
    "list_urls": ["https://xxx.gov.cn/"],
},
```

自定义关键词编辑 `src/keywords.py`：
- `SUBJECT_WORDS`：主体词（三资、集体资产、农业农村等）
- `ACTION_WORDS`：行为词（监管、整治、挪用、追缴等）
- `RESULT_WORDS`：结果词（追回、清退、返还等）
- `STRONG_EXCLUDE_WORDS`：强排除词（命中即丢弃）
- `TITLE_HINT_PAIRS`：标题线索（标题不含主体词但明显相关时使用）

## 📝 注意事项

- 部分网站有反爬机制，可适当调大 `REQUEST_DELAY` / `REQUEST_TIMEOUT`
- 网站改版可能导致个别来源失效，建议定期在 Actions 日志中查看"官方平台有效新闻"数量
- 官方平台结果 ≥ `MIN_OFFICIAL_RESULTS` 时不会启用搜索引擎，需要更多内容可调大该值或关闭搜索
- 建议使用 QQ 邮箱 SMTP，收件人邮箱格式务必在 Secrets 中写正确（不要带换行/空格）

## 📄 License

MIT License
