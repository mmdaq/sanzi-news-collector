"""
邮件发送模块
"""

import smtplib
import time
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
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
                msg['From'] = Header(f"三资监管简报 <{self.config.sender_email}>")
                msg['To'] = Header(self.config.receiver_email)
                msg['Subject'] = Header(subject, 'utf-8')

                if text_content:
                    text_part = MIMEText(text_content, 'plain', 'utf-8')
                    msg.attach(text_part)

                html_part = MIMEText(html_content, 'html', 'utf-8')
                msg.attach(html_part)

                logger.info(f"发送邮件 (尝试 {attempt+1}/{self.max_retries})...")

                with smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port) as server:
                    server.login(self.config.sender_email, self.config.sender_password)
                    server.sendmail(self.config.sender_email, [self.config.receiver_email], msg.as_string())

                logger.info(f"✅ 邮件发送成功")
                return True

            except smtplib.SMTPAuthenticationError as e:
                logger.error(f"❌ 邮件认证失败: {e}")
                return False
            except Exception as e:
                logger.warning(f"邮件发送失败 (尝试 {attempt+1}): {e}")

        logger.error(f"❌ 邮件发送失败，已重试 {self.max_retries} 次")
        return False
