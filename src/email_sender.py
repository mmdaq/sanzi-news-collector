"""
邮件发送模块
"""

import smtplib
import time
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from datetime import datetime

from .config import Config

logger = logging.getLogger(__name__)


class EmailSender:
    def __init__(self, config: Config):
        self.config = config
        self.max_retries = 3

    def send(self, subject: str, html_content: str, text_content: str = None) -> bool:
        # 【调试打印 1】：只要进入这个函数，立刻打印出发件人和收件人，防止程序提前静默退出
        print(f"【邮件调试】进入发件环节！")
        print(f"【邮件调试】发件人: {self.config.sender_email}")
        print(f"【邮件调试】收件人: {self.config.receiver_email}")
        
        if not self.config.is_valid:
            missing = self.config.get_missing_fields()
            logger.error(f"❌ 邮件配置不完整，缺少: {', '.join(missing)}")
            print("【邮件调试】配置校验失败，请检查 GitHub Secrets 是否配置了 SENDER_EMAIL 和 SENDER_PASSWORD")
            return False

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    logger.info(f"⏳ 等待 {2 ** attempt} 秒后进行第 {attempt+1} 次重试...")
                    time.sleep(2 ** attempt)

                msg = MIMEMultipart('alternative')
                
                # 强制清洗邮箱字符串
                raw_sender = str(self.config.sender_email).strip().replace('"', '').replace("'", "").replace(" ", "")
                raw_receiver = str(self.config.receiver_email).strip().replace('"', '').replace("'", "").replace(" ", "")
                
                if not raw_sender or not raw_receiver:
                    logger.error(f"❌ 清洗后的邮箱地址为空！请检查 GitHub Secrets 配置。")
                    return False

                msg['From'] = formataddr(("三资监管简报", raw_sender))
                msg['To'] = raw_receiver
                msg['Subject'] = Header(subject, 'utf-8')

                if text_content:
                    text_part = MIMEText(text_content, 'plain', 'utf-8')
                    msg.attach(text_part)

                html_part = MIMEText(html_content, 'html', 'utf-8')
                msg.attach(html_part)

                logger.info(f"📤 正在连接邮件服务器并发送 (尝试 {attempt+1}/{self.max_retries})... [发件人: {raw_sender}]")

                with smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port) as server:
                    server.login(raw_sender, self.config.sender_password)
                    server.sendmail(raw_sender, [raw_receiver], msg.as_string())

                logger.info(f"✅ 邮件发送成功！请检查 {raw_receiver} 的收件箱。")
                return True

            except smtplib.SMTPAuthenticationError as e:
                logger.error(f"❌ 邮件认证失败 (授权码错误或过期): {e}")
                print(f"【邮件调试】报错详情：{e}")
                return False
            except smtplib.SMTPServerDisconnected as e:
                logger.warning(f"⚠️ 邮件服务器断开连接 (尝试 {attempt+1}): {e}")
                if "550" in str(e):
                    logger.error("⚠️ 检测到 QQ 邮箱 550 错误，通常是收件人地址无效或发件人地址格式错误导致。")
            except Exception as e:
                logger.warning(f"⚠️ 邮件发送失败 (尝试 {attempt+1}): {e}")

        logger.error(f"❌ 邮件发送失败，已重试 {self.max_retries} 次")
        print("【邮件调试】3次重试均失败，请查看上面日志排查原因。")
        return False
