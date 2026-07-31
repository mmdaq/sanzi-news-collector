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
        if not self.config.is_valid:
            missing = self.config.get_missing_fields()
            logger.error(f"邮件配置不完整，缺少: {', '.join(missing)}")
            return False

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    time.sleep(2 ** attempt)

                msg = MIMEMultipart('alternative')
                
                # =================================================================
                # 【超强清洗逻辑】：强制清理从环境变量读入的邮箱地址
                # 哪怕是 GitHub Secrets 里带了不可见空格、双引号、单引号，全清理掉！
                # =================================================================
                raw_sender = str(self.config.sender_email).strip().replace('"', '').replace("'", "").replace(" ", "")
                raw_receiver = str(self.config.receiver_email).strip().replace('"', '').replace("'", "").replace(" ", "")
                
                # 如果清洗后为空，直接报错
                if not raw_sender or not raw_receiver:
                    logger.error(f"❌ 清洗后的邮箱地址为空！请检查 GitHub Secrets (SENDER_EMAIL: '{raw_sender}', RECEIVER_EMAIL: '{raw_receiver}')")
                    return False

                # 设置邮件头
                msg['From'] = formataddr(("三资监管简报", raw_sender))
                msg['To'] = raw_receiver
                msg['Subject'] = Header(subject, 'utf-8')

                if text_content:
                    text_part = MIMEText(text_content, 'plain', 'utf-8')
                    msg.attach(text_part)

                html_part = MIMEText(html_content, 'html', 'utf-8')
                msg.attach(html_part)

                logger.info(f"发送邮件 (尝试 {attempt+1}/{self.max_retries})... [发件人: {raw_sender}]")

                # QQ邮箱强制使用 SSL 协议和 465 端口
                with smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port) as server:
                    server.login(raw_sender, self.config.sender_password)
                    server.sendmail(raw_sender, [raw_receiver], msg.as_string())

                logger.info(f"✅ 邮件发送成功")
                return True

            except smtplib.SMTPAuthenticationError as e:
                logger.error(f"❌ 邮件认证失败 (授权码错误或过期): {e}")
                return False
            except smtplib.SMTPServerDisconnected as e:
                logger.warning(f"邮件服务器断开连接 (尝试 {attempt+1}): {e}")
                # 如果是 550 错误，通常在断开连接里会有提示
                if "550" in str(e):
                    logger.error("⚠️ 检测到 QQ 邮箱 550 错误，通常是收件人地址无效或发件人地址清洗失败导致。")
            except Exception as e:
                logger.warning(f"邮件发送失败 (尝试 {attempt+1}): {e}")

        logger.error(f"❌ 邮件发送失败，已重试 {self.max_retries} 次")
        return False
