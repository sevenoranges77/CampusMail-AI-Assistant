import imaplib
import email
import socket
from email.header import decode_header
from email.utils import parsedate_to_datetime
import datetime
from bs4 import BeautifulSoup 
from config import Config
from logger_config import setup_logger

logger = setup_logger("CampusAI.MailReader")

class MailReader:
    def __init__(self):
        self.imap_server = Config.IMAP_SERVER
        self.email_user = Config.EMAIL_USER
        self.email_pass = Config.EMAIL_PASS
        self.mail = None

    def connect(self):
        """
        连接邮箱，具有精确的错误诊断功能
        """
        try:
            logger.info(f"🔌 正在连接 IMAP 服务器: {self.imap_server}...")
            self.mail = imaplib.IMAP4_SSL(self.imap_server, timeout=10) # 增加超时设置
            self.mail.login(self.email_user, self.email_pass)
            return True
        except imaplib.IMAP4.error as e:
            # 尝试解码 IMAP 错误信息 (通常是 bytes)
            err_msg = str(e)
            if isinstance(e.args[0], bytes):
                try:
                    err_msg = e.args[0].decode('utf-8', 'ignore')
                except Exception as decode_err:
                    logger.warning(f"IMAP 错误信息解码失败: {decode_err}")
            
            if "AUTHENTICATIONFAILED" in err_msg or "Login failed" in err_msg:
                raise Exception("❌ 登录失败：授权码错误或未开启 IMAP 服务。请检查QQ邮箱设置。")
            else:
                raise Exception(f"❌ IMAP 协议错误: {err_msg}")
        except socket.timeout:
            raise Exception("❌ 连接超时：网络不通。如果开启了代理，请检查代理配置。")
        except Exception as e:
            raise Exception(f"❌ 邮箱连接未知错误: {e}")

    def get_recent_emails(self, days=Config.LOOKBACK_DAYS):
        # 注意：这里不再 catch Exception，而是让 main.py 处理，以便显示具体错误
        if not self.mail:
             # 如果还没连接，尝试连接
             self.connect()

        self.mail.select("inbox")
        
        # 搜索邮件
        date_since = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%d-%b-%Y")
        status, messages = self.mail.search(None, f'(SINCE "{date_since}")')
        
        if status != "OK" or not messages[0]:
            logger.warning("⚠️ 未搜索到邮件")
            return []

        email_ids = messages[0].split()
        
        # 安全限制：只取最新的 30 封
        SAFE_LIMIT = 30
        process_ids = email_ids[-SAFE_LIMIT:] if len(email_ids) > SAFE_LIMIT else email_ids
        
        results = []
        limit_datetime = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days + 1)

        for e_id in reversed(process_ids):
            try:
                _, msg_data = self.mail.fetch(e_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # 日期检查
                        try:
                            email_date = parsedate_to_datetime(msg.get("Date"))
                            if email_date < limit_datetime:
                                break 
                        except Exception as e:
                            logger.warning(f"邮件日期解析失败 (Date={msg.get('Date')}): {e}")

                        # 提取主题
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding if encoding else "utf-8", errors="ignore")
                            
                        email_from = msg.get("From")
                        message_id = msg.get("Message-ID")
                        date_str = msg.get("Date")
                        
                        # 正文提取
                        body = self._get_email_body_robust(msg)
                        
                        if body:
                            clean_body = "\n".join([line.strip() for line in body.splitlines() if line.strip()])
                            
                            results.append({
                                "subject": subject,
                                "from": email_from,
                                "message_id": message_id,
                                "received_time": date_str,
                                "body": clean_body[:3000]
                            })
            except Exception as e:
                logger.warning(f"⚠️ 单封邮件解析出错 (跳过): {e}", exc_info=True)
                continue
                
        return results

    def _get_email_body_robust(self, msg):
        """
        增强版提取：优先提取 HTML 并转为纯文本
        """
        text_content = ""
        html_content = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if "attachment" in content_disposition:
                    continue

                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    decoded_content = payload.decode(charset, errors='ignore')

                    if content_type == "text/html":
                        html_content += decoded_content
                    elif content_type == "text/plain":
                        text_content += decoded_content
                except Exception as e:
                    logger.debug(f"邮件 Part 解码失败 (type={part.get_content_type()}): {e}")
        else:
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or 'utf-8'
                content = payload.decode(charset, errors='ignore')
                if msg.get_content_type() == "text/html":
                    html_content = content
                else:
                    text_content = content
            except Exception as e:
                logger.warning(f"非 Multipart 邮件体解码失败: {e}", exc_info=True)

        if html_content:
            try:
                soup = BeautifulSoup(html_content, "html.parser")
                return soup.get_text(separator="\n")
            except Exception as e:
                logger.warning(f"HTML 转文本失败: {e}")
        
        return text_content