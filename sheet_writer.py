# ==============================================
import proxy_patch
proxy_patch.apply_proxy()
# ==============================================
import pandas as pd
import datetime
from googleapiclient.discovery import build
from google_auth import get_credentials
from config import Config

class SheetWriter:
    def __init__(self):
        creds = get_credentials()
        self.service = build('sheets', 'v4', credentials=creds)
        self.spreadsheet_id = Config.SPREADSHEET_ID
        self.sheet_name = "Log" 

    def is_message_processed_successfully(self, message_id):
        """
        智能查重 (逻辑修复版)：
        遍历该 ID 的所有日志记录。
        只要发现【至少有一条】是 "Created" 或 "Ignored"，就视为已完成 (返回 True)。
        只有当【所有记录】都是 "Failed" 时，才允许重试 (返回 False)。
        """
        range_name = f"{self.sheet_name}!D:F" 
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id, range=range_name).execute()
            rows = result.get('values', [])
            
            # 1. 先找出所有匹配该 ID 的记录
            matched_rows = [row for row in rows if len(row) >= 3 and row[0] == message_id]
            
            if not matched_rows:
                return False # 全新邮件，未处理
            
            # 2. 检查这些记录中是否有成功的
            for row in matched_rows:
                past_action = row[2]
                # 只要有一次成功或主动忽略，就彻底跳过
                if "Created" in past_action or "Ignored" in past_action:
                    # print(f"   🟡 检测到历史成功记录 ({past_action})，跳过。")
                    return True
            
            # 3. 如果代码走到这里，说明虽然有记录，但全都是 Failed
            print(f"   🔄 历史记录全为失败，正在重试...")
            return False

        except Exception as e:
            print(f"[Warning] 读取日志失败 ({e})，默认未处理。")
            return False
        

    def log_action(self, email_from, subject, message_id, category, action):
        """写入一行日志"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        values = [[timestamp, email_from, subject, message_id, category, action]]
        body = {'values': values}
        
        try:
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A:F",
                valueInputOption="USER_ENTERED",
                body=body
            ).execute()
            print(f"📝 [日志已记录] {category} -> {action}")
        except Exception as e:
            print(f"❌ [Error] 写入日志失败: {e}")

            
    def read_logs_as_df(self):
        """读取整个 Log 表格并转换为 Pandas DataFrame"""
        range_name = f"{self.sheet_name}!A:F"
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id, range=range_name).execute()
            rows = result.get('values', [])
            
            if not rows:
                return pd.DataFrame()

            # 假设第一行是表头
            # 表头: [时间, 发件人, 主题, Message-ID, 分类, 动作]
            headers = ["Time", "From", "Subject", "MsgID", "Category", "Action"]
            
            # 如果数据行不够，可能会报错，做个防御
            data = []
            for row in rows:
                # 补齐长度，防止某一行少列
                while len(row) < 6:
                    row.append("")
                data.append(row)

            df = pd.DataFrame(data, columns=headers)
            
            # 简单清洗：去掉空行，转换时间格式
            df = df[df["Time"] != ""]
            # 尝试转换时间列
            df["Time"] = pd.to_datetime(df["Time"], errors='coerce')
            
            return df
        except Exception as e:
            print(f"❌ 读取数据失败: {e}")
            return pd.DataFrame()

if __name__ == "__main__":
    print("SheetWriter logic updated.")