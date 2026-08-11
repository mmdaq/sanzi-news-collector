"""
邮件发送模块（支持多收件人）
"""

import logging
import smtplib
import time
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from .config import Config

logger = logging.getLogger(__name__)


class EmailSender:
    def __init__(self, config: Config):
        self.config = config
        self.max_retries = 3

    @staticmethod
    def _clean_email(raw: str) -> str:
        """清洗环境变量中的不可见字符。"""
        if not raw:
            return ""
        cleaned = raw.strip()
        cleaned = cleaned.replace('"', "").replace("'", "")
        cleaned = "".join(ch for ch in cleaned if ord(ch) >= 32 or ch == ",")
        cleaned = cleaned.replace("，", ",").replace("、", ",")
        return cleaned

    def send(self, subject: str, html_content: str, text_content: str = None) -> bool:
        if not self.config.is_valid:
            missing = self.config.get_missing_fields()
            logger.error("❌ 邮件配置不完整，缺少: %s", ", ".join(missing))
            return False

        raw_sender = self._clean_email(self.config.sender_email)
        raw_receivers = self._clean_email(self.config.receiver_email)
        receiver_list = [e.strip() for e in raw_receivers.split(",") if e.strip()]
        if not raw_sender or not receiver_list:
            logger.error("❌ 发件人或收件人邮箱为空/格式非法")
            return False

        to_header = ", ".join(receiver_list)
        for attempt in range(1, self.max_retries + 1):
            try:
                if attempt > 1:
                    time.sleep(2 ** attempt)
                msg = MIMEMultipart("alternative")
                msg["From"] = formataddr(("三资监管简报", raw_sender))
                msg["To"] = to_header
                msg["Subject"] = Header(subject, "utf-8")
                if text_content:
                    msg.attach(MIMEText(text_content, "plain", "utf-8"))
                msg.attach(MIMEText(html_content, "html", "utf-8"))

                logger.info("📤 发送邮件 (尝试 %d/%d) 收件人: %s",
                            attempt, self.max_retries, receiver_list)
                with smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port) as server:
                    server.login(raw_sender, self.config.sender_password)
                    server.sendmail(raw_sender, receiver_list, msg.as_string())
                logger.info("✅ 邮件发送成功")
                return True
            except smtplib.SMTPAuthenticationError as e:
                logger.error("❌ 邮件认证失败（授权码错误或过期）: %s", e)
                return False
            except Exception as e:
                logger.warning("⚠️ 邮件发送失败 (尝试 %d): %s", attempt, e)
        logger.error("❌ 邮件发送失败，已重试 %d 次", self.max_retries)
        return False
