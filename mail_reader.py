import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import datetime
from bs4 import BeautifulSoup  # <--- 新增：专门用来处理 HTML
from config import Config

class MailReader:
    def __init__(self):
        self.imap_server = Config.IMAP_SERVER
        self.email_user = Config.EMAIL_USER
        self.email_pass = Config.EMAIL_PASS

    def connect(self):
        try:
            self.mail = imaplib.IMAP4_SSL(self.imap_server)
            self.mail.login(self.email_user, self.email_pass)
            return True
        except Exception as e:
            print(f"❌ [Mail Error] 登录失败: {e}")
            return False

    def get_recent_emails(self, days=Config.LOOKBACK_DAYS):
        if not self.connect():
            return []

        self.mail.select("inbox")
        
        # 搜索邮件
        date_since = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%d-%b-%Y")
        status, messages = self.mail.search(None, f'(SINCE "{date_since}")')
        
        if status != "OK" or not messages[0]:
            print("⚠️ 未搜索到邮件")
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
                        except: pass

                        # 提取主题
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding if encoding else "utf-8", errors="ignore")
                            
                        email_from = msg.get("From")
                        message_id = msg.get("Message-ID")
                        date_str = msg.get("Date")
                        
                        # ================= 关键修改：更强的正文提取 =================
                        body = self._get_email_body_robust(msg)
                        # ==========================================================
                        
                        if body:
                            # 稍微清洗一下多余的空行，省点 Token
                            clean_body = "\n".join([line.strip() for line in body.splitlines() if line.strip()])
                            
                            results.append({
                                "subject": subject,
                                "from": email_from,
                                "message_id": message_id,
                                "received_time": date_str,
                                "body": clean_body[:3000] # 放宽限制到3000字符，防止HTML转文字后依然很长
                            })
            except Exception as e:
                print(f"⚠️ 解析出错: {e}")
                continue
                
        return results

    def _get_email_body_robust(self, msg):
        """
        增强版提取：优先提取 HTML 并转为纯文本，
        如果 HTML 提取失败，再尝试提取纯文本。
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
                except:
                    pass
        else:
            # 非 multipart
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or 'utf-8'
                content = payload.decode(charset, errors='ignore')
                if msg.get_content_type() == "text/html":
                    html_content = content
                else:
                    text_content = content
            except:
                pass

        # 策略：优先用 HTML (因为它通常包含完整格式)，转为 Text
        if html_content:
            try:
                soup = BeautifulSoup(html_content, "html.parser")
                # get_text 会把 <tr><td> 变成换行，保留表格结构
                return soup.get_text(separator="\n")
            except Exception as e:
                print(f"   (HTML解析失败: {e}, 降级使用纯文本)")
        
        return text_content