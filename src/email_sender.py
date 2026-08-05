"""
邮件发送模块 (支持多收件人，加入终极暴力清洗隐藏字符)
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

    def _super_clean_email(self, raw_str: str) -> str:
        """超强力清洗环境变量带来的不可见字符"""
        if not raw_str:
            return ""
        # 1. 去除首尾空格、换行符 \n、回车符 \r、制表符 \t
        cleaned = raw_str.strip()
        # 2. 去除可能存在的双引号、单引号
        cleaned = cleaned.replace('"', '').replace("'", "")
        # 3. 【核心修复】：暴力去除 ASCII 控制字符（包括不可见的换行符）
        # 这一步会把 \n, \r, \x0b, \x0c, \x1a 等全部删掉
        cleaned = ''.join([char for char in cleaned if ord(char) >= 32 or char in ','])
        # 4. 如果有中文逗号，强制转英文逗号
        cleaned = cleaned.replace('，', ',').replace('、', ',')
        return cleaned

    def send(self, subject: str, html_content: str, text_content: str = None) -> bool:
        print(f"【邮件调试】进入发件环节！")
        print(f"【邮件调试】原始发件人(打码): {self.config.sender_email}")
        print(f"【邮件调试】原始收件人(打码): {self.config.receiver_email}")

        if not self.config.is_valid:
            missing = self.config.get_missing_fields()
            logger.error(f"❌ 邮件配置不完整，缺少: {', '.join(missing)}")
            return False

        # ========== 使用超强力清洗函数 ==========
        # 1. 清理发件人
        raw_sender = self._super_clean_email(str(self.config.sender_email))
        if not raw_sender:
            logger.error("❌ 发件人邮箱为空或清洗后为空！")
            return False

        # 2. 清理收件人字符串
        raw_receivers = self._super_clean_email(str(self.config.receiver_email))
        
        # 3. 按英文逗号切分成列表
        receiver_list = [email.strip() for email in raw_receivers.split(',') if email.strip()]
        
        if not receiver_list:
            logger.error("❌ 收件人邮箱列表为空！请配置至少一个邮箱。")
            print(f"【报错详情】清洗后的收件人原始字符串是: '{raw_receivers}' (请检查是否包含非法字符)")
            return False

        # 4. 生成邮件头显示的 To
        to_header = ', '.join(receiver_list)
        
        print(f"【邮件调试】最终清洗后发件人: {raw_sender}")
        print(f"【邮件调试】最终确认收件人列表: {receiver_list}")

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    logger.info(f"⏳ 等待 {2 ** attempt} 秒后进行第 {attempt+1} 次重试...")
                    time.sleep(2 ** attempt)

                msg = MIMEMultipart('alternative')
                
                msg['From'] = formataddr(("三资监管简报", raw_sender))
                msg['To'] = to_header
                msg['Subject'] = Header(subject, 'utf-8')

                if text_content:
                    text_part = MIMEText(text_content, 'plain', 'utf-8')
                    msg.attach(text_part)

                html_part = MIMEText(html_content, 'html', 'utf-8')
                msg.attach(html_part)

                logger.info(f"📤 正在连接邮件服务器并发送 (尝试 {attempt+1}/{self.max_retries})... [发件人: {raw_sender}, 目标收件人数: {len(receiver_list)}]")

                with smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port) as server:
                    server.login(raw_sender, self.config.sender_password)
                    # 发送时传入发件人和收件人列表
                    server.sendmail(raw_sender, receiver_list, msg.as_string())

                logger.info(f"✅ 邮件发送成功！请检查收件箱。")
                return True

            except smtplib.SMTPAuthenticationError as e:
                logger.error(f"❌ 邮件认证失败 (授权码错误或过期): {e}")
                return False
            except smtplib.SMTPServerDisconnected as e:
                logger.warning(f"⚠️ 邮件服务器断开连接 (尝试 {attempt+1}): {e}")
                if "501" in str(e):
                    logger.error(f"⚠️ 检测到 QQ 邮箱 501 错误！说明收件人邮箱格式依然有问题。")
                    logger.error(f"⚠️ 当前尝试发送的收件人列表是: {receiver_list}")
                    logger.error(f"⚠️ 请务必去 GitHub Secrets 检查 RECEIVER_EMAIL 里是否隐藏了换行符或空格！")
            except Exception as e:
                logger.warning(f"⚠️ 邮件发送失败 (尝试 {attempt+1}): {e}")

        logger.error(f"❌ 邮件发送失败，已重试 {self.max_retries} 次")
        print("【邮件调试】3次重试均失败，请查看上面日志排查原因。")
        return False
