\# 农村集体"三资"监管 · 新闻自动采集简报系统



\[!\[GitHub stars](https://img.shields.io/github/stars/your-username/sanzi-news-collector)](https://github.com/your-username/sanzi-news-collector/stargazers)

\[!\[GitHub license](https://img.shields.io/github/license/your-username/sanzi-news-collector)](https://github.com/your-username/sanzi-news-collector/blob/main/LICENSE)



> 每日自动采集农村集体资金、资产、资源（三资）监管领域的新闻动态，生成简报发送至指定邮箱。



\## ✨ 功能特性



\- 🔍 \*\*多源采集\*\*：覆盖中央纪委国家监委网站、农业农村部官网、人民网反腐倡廉频道、中国纪检监察报、各省/市纪委监委网站

\- 🎯 \*\*智能检索\*\*：基于关键词词库，精准锁定"三资"监管、案例通报、追回资金、"蝇贪蚁腐"等信息

\- 📅 \*\*时效过滤\*\*：只采集当天及前1天的新闻，确保信息新鲜度

\- 🔗 \*\*链接修复\*\*：自动修复URL格式，验证链接可访问性

\- 📧 \*\*邮件简报\*\*：每日自动生成含序号、发布时间、标题、简述、来源、链接的HTML简报

\- 🗂️ \*\*去重机制\*\*：自动记录已采集内容，避免重复

\- ⚙️ \*\*自动化部署\*\*：支持GitHub Actions每日定时运行



\## 📦 快速开始



\### 1. Fork仓库



点击右上角 Fork 本仓库到你的 GitHub 账号



\### 2. 配置 GitHub Secrets



在仓库 Settings → Secrets and variables → Actions 中添加：



| Secret 名称 | 说明 |

|------------|------|

| `SMTP\_SERVER` | SMTP服务器（如 smtp.qq.com） |

| `SMTP\_PORT` | SMTP端口（如 465） |

| `SENDER\_EMAIL` | 发送邮箱 |

| `SENDER\_PASSWORD` | 邮箱授权码（不是登录密码） |

| `RECEIVER\_EMAIL` | 接收邮箱 |



\### 3. 手动触发运行



进入 Actions 页面，选择 "每日三资监管简报"，点击 "Run workflow" 手动触发测试



\## 📂 项目结构



sanzi-news-collector/

├── .github/workflows/daily\_brief.yml # GitHub Actions

├── src/

│ ├── config.py # 配置管理

│ ├── keywords.py # 关键词词库

│ ├── collector.py # 新闻采集器

│ ├── brief\_generator.py # 简报生成器

│ ├── email\_sender.py # 邮件发送器

│ ├── health\_check.py # 健康检查

│ └── keyword\_stats.py # 关键词统计

├── main.py # 主程序入口

├── requirements.txt # Python依赖

├── .env.example # 环境变量模板

├── .gitignore

├── LICENSE

└── README.md





\## 📧 简报示例



📋 农村集体"三资"监管 · 每日简报

📅 2026年07月30日 · 共 5 条最新相关信息



序号：1

发布时间：2026-07-29

标题：记者观察丨督促新任村干部勤廉履职

简述内容：纪检监察机关聚焦换届后村集体"三资"管理的关键环节...

原文来源：中央纪委国家监委网站

原文链接：https://www.ccdi.gov.cn/yaowenn/202607/t20260729\_504013\_m.html







\## ⚙️ 自定义关键词



编辑 `src/keywords.py` 文件，按需增删关键词组合。



\## 📝 注意事项



\- 部分网站可能有反爬机制，建议适当调整 `request\_delay` 参数

\- 网站页面结构变化可能导致采集失效，需定期维护

\- 建议使用QQ邮箱的SMTP服务



\## 📄 License



MIT License

