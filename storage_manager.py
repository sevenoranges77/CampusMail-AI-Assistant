import pandas as pd
import os
import datetime

class StorageManager:
    def __init__(self, file_path="campus_data.xlsx"):
        self.file_path = file_path
        self.columns = [
            "MsgID",        
            "Category",     
            "Title",        
            "Time_Info",    
            "Status",       # 未完成 / 已完成 / 已忽略
            "Original_Body",
            "Created_At"    
        ]
        self._init_file()

    def _init_file(self):
        if not os.path.exists(self.file_path):
            df = pd.DataFrame(columns=self.columns)
            df.to_excel(self.file_path, index=False)

    def load_data(self):
        try:
            return pd.read_excel(self.file_path)
        except Exception as e:
            return pd.DataFrame(columns=self.columns)

    def is_processed(self, msg_id):
        """
        查重：只要 Excel 里有这个 ID (无论是任务还是垃圾)，都算处理过。
        """
        df = self.load_data()
        if df.empty: return False
        return msg_id in df["MsgID"].values

    def save_event(self, llm_json, msg_id, original_body, received_time_obj=None):
        """
        保存事件 (全量保存版：既存任务，也存日志)
        """
        df = self.load_data()
        category = llm_json.get('category')
        title = llm_json.get('event_title')
        
        # 默认值
        final_time_str = "" 
        status = "已忽略"  # 默认是忽略，只有高价值才改为 "未完成"
        
        # === 高价值邮件处理 (DDL, 面试, 简历) ===
        if category in ['DDL', 'FIXED_SLOT', 'RESUME_UPDATE']:
            status = "未完成" # 标记为待办任务
            
            if not title: title = f"[{category}] 未命名事项"
            
            # --- 时间处理逻辑 (保持 V2.1 的优化) ---
            if category == 'FIXED_SLOT':
                start = llm_json.get('start_time')
                end = llm_json.get('end_time')
                if start:
                    start_clean = start.replace('T', ' ')
                    if end:
                        try:
                            end_clean = end.replace('T', ' ').split(' ')[1][:5]
                        except:
                            end_clean = end
                        final_time_str = f"{start_clean} ~ {end_clean}"
                    else:
                        final_time_str = start_clean

            elif category == 'RESUME_UPDATE':
                if received_time_obj:
                    try:
                        target_date = received_time_obj + datetime.timedelta(days=3)
                        final_time_str = target_date.strftime("%Y-%m-%d %H:%M") + " (建议)"
                        title = f"[建议3天内] {title}"
                    except:
                        final_time_str = llm_json.get('ddl')
                else:
                     final_time_str = llm_json.get('ddl')

            elif category == 'DDL':
                ddl = llm_json.get('ddl')
                if ddl:
                    final_time_str = ddl.replace('T', ' ')
        
        # === 低价值邮件处理 (广告, 拒信等) ===
        else:
            # 低价值邮件不需要时间，标题如果 LLM 没给，就用分类代替
            if not title: title = f"[{category}] 无标题"
            final_time_str = "-"

        # --- 构造数据 ---
        new_row = {
            "MsgID": msg_id,
            "Category": category,
            "Title": title,
            "Time_Info": final_time_str,
            "Status": status, # 关键字段：区分任务和日志
            "Original_Body": original_body[:1000], 
            "Created_At": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        new_df = pd.DataFrame([new_row])
        df = pd.concat([df, new_df], ignore_index=True)
        
        try:
            df.to_excel(self.file_path, index=False)
            if status == "未完成":
                print(f"💾 [Task Saved] {title}")
            else:
                print(f"📝 [Log Saved] 已记录低价值邮件: {category}")
            return True
        except Exception as e:
            print(f"❌ [Excel Error] 写入失败: {e}")
            return False

    def update_status(self, msg_id, new_status):
        df = self.load_data()
        if msg_id in df["MsgID"].values:
            df.loc[df["MsgID"] == msg_id, "Status"] = new_status
            df.to_excel(self.file_path, index=False)
            return True
        return False