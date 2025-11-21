# ==============================================
import proxy_patch
proxy_patch.apply_proxy()
# ==============================================

import datetime
from googleapiclient.discovery import build
from google_auth import get_credentials
from config import Config

class CalendarWriter:
    def __init__(self):
        creds = get_credentials()
        self.service = build('calendar', 'v3', credentials=creds)
        self.calendar_id = Config.CALENDAR_ID

    # 【修改】新增参数 received_time_str
    def create_event(self, llm_json, source_message_id, received_time_str=None):
        """
        根据 LLM 返回的 JSON 创建日历事件
        """
        category = llm_json.get('category')
        title = llm_json.get('event_title')
        if not title: title = f"[{category}] 未命名校招事项"
        
        summary_info = llm_json.get('summary_info', '无详细信息')
        
        description = (
            f"{summary_info}\n\n"
            f"------------------------\n"
            f"🤖 AI 分类: {category}\n"
            f"📧 来源邮件ID: {source_message_id}"
        )

        event_body = {
            'summary': title,
            'description': description,
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 60},
                ],
            },
        }

        # --- 分支 A: 固定时间段 (面试/考试) ---
        if category == 'FIXED_SLOT':
            start_time_str = llm_json.get('start_time')
            end_time_str = llm_json.get('end_time')
            
            if not start_time_str: return False
            if not end_time_str:
                # 自动补全 +1h
                try:
                    dt_start = datetime.datetime.fromisoformat(start_time_str)
                    dt_end = dt_start + datetime.timedelta(hours=1)
                    end_time_str = dt_end.isoformat()
                except: return False

            event_body['start'] = {'dateTime': start_time_str, 'timeZone': 'Asia/Shanghai'}
            event_body['end'] = {'dateTime': end_time_str, 'timeZone': 'Asia/Shanghai'}

        # --- 分支 B: 简历完善 (特殊策略：收到邮件后 +3 天) ---
        elif category == 'RESUME_UPDATE':
            # 无论 LLM 说的 ddl 是哪天，我们都强制设为【收到邮件+3天】
            if received_time_str:
                try:
                    # 解析邮件接收时间 (格式如 "15 Nov 2025 10:00:00 +0800" 或 LLM 处理过的格式)
                    # 为了简单，我们直接用当前脚本运行时间或者尝试解析传入的时间
                    # 这里假设 received_time_str 是 main.py 传进来的标准格式
                    rec_dt = datetime.datetime.strptime(received_time_str, "%a, %d %b %Y %H:%M:%S %z")
                    # +3 天
                    action_dt = rec_dt + datetime.timedelta(days=3)
                    target_date = action_dt.strftime("%Y-%m-%d")
                    
                    # 修改标题以提示
                    event_body['summary'] = f"[建议3天内] {title}"
                    event_body['start'] = {'date': target_date}
                    event_body['end'] = {'date': target_date}
                    print(f"   💡 [策略] 简历完善类邮件，强制设定 DDL 为 3 天后 ({target_date})")
                except Exception as e:
                    print(f"   ⚠️ 时间计算失败 ({e})，回退到使用原始 DDL")
                    # 回退逻辑
                    ddl_date = llm_json.get('ddl')
                    if not ddl_date: return False
                    event_body['start'] = {'date': ddl_date}
                    event_body['end'] = {'date': ddl_date}
            else:
                # 如果没有传入接收时间，回退到原始 DDL
                ddl_date = llm_json.get('ddl')
                if not ddl_date: return False
                event_body['start'] = {'date': ddl_date}
                event_body['end'] = {'date': ddl_date}

        # --- 分支 C: 普通 DDL ---
        elif category == 'DDL':
            ddl_date = llm_json.get('ddl')
            if not ddl_date: return False
            event_body['start'] = {'date': ddl_date}
            event_body['end'] = {'date': ddl_date} 

        else:
            return False

        try:
            self.service.events().insert(calendarId=self.calendar_id, body=event_body).execute()
            return True
        except Exception as e:
            print(f"❌ [Error] Calendar API: {e}")
            return False