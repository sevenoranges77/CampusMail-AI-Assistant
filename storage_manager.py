# ==============================================
# storage_manager.py (V3.0 - 新增列 + 去重 + 提醒标记)
# ==============================================
import pandas as pd
import os
import time
import datetime
import tempfile
import shutil
from logger_config import setup_logger
from time_validator import TimeValidator

logger = setup_logger("CampusAI.Storage")


class StorageManager:
    def __init__(self, file_path="campus_data.xlsx"):
        self.file_path = file_path
        self.columns = [
            "MsgID",
            "Category",
            "Title",
            "Time_Info",
            "Status",           # 未完成 / 已完成 / 已忽略 / 待人工核实
            "Original_Body",
            "Created_At",
            # V3.0 新增
            "Event_Group_ID",   # 事件分组 ID (去重用)
            "DDL_Datetime",     # 规范化截止时间 (机器可计算)
            "Company_Name",     # 公司名
            "Is_Flexible",      # 是否弹性时段
            "Reminder_24h",     # T-24h 提醒标记
            "Reminder_2h",      # T-2h 提醒标记
        ]
        self._init_file()

    def _init_file(self):
        if not os.path.exists(self.file_path):
            df = pd.DataFrame(columns=self.columns)
            self._safe_write_excel(df)
        else:
            # 向后兼容：旧版 Excel 补全新列
            self._migrate_schema()

    def _migrate_schema(self):
        """向后兼容：检测旧版 Excel 并自动补全 V3.0 新增列"""
        try:
            df = pd.read_excel(self.file_path)
            new_cols_defaults = {
                "Event_Group_ID": df.get("MsgID", ""),  # 默认 = 自身 MsgID
                "DDL_Datetime": "",
                "Company_Name": "",
                "Is_Flexible": "",
                "Reminder_24h": 0,
                "Reminder_2h": 0,
            }
            changed = False
            for col, default in new_cols_defaults.items():
                if col not in df.columns:
                    if col == "Event_Group_ID" and "MsgID" in df.columns:
                        df[col] = df["MsgID"]
                    else:
                        df[col] = default
                    changed = True
                    logger.info(f"[Schema Migration] 新增列: {col}")

            if changed:
                self._safe_write_excel(df)
                logger.info("[Schema Migration] 旧版 Excel 已升级至 V3.0 Schema")
        except Exception as e:
            logger.error(f"Schema 迁移失败: {e}", exc_info=True)

    def _safe_write_excel(self, df, max_retries=3):
        """安全写入：临时文件 + 原子替换 + 重试"""
        for attempt in range(1, max_retries + 1):
            tmp_path = None
            try:
                target_dir = os.path.dirname(os.path.abspath(self.file_path))
                fd, tmp_path = tempfile.mkstemp(suffix='.xlsx', dir=target_dir)
                os.close(fd)
                df.to_excel(tmp_path, index=False)
                shutil.move(tmp_path, self.file_path)
                return True
            except PermissionError:
                logger.warning(f"文件被占用，第 {attempt}/{max_retries} 次重试...")
                if tmp_path and os.path.exists(tmp_path):
                    try: os.remove(tmp_path)
                    except Exception: pass
                time.sleep(1)
            except Exception as e:
                logger.error(f"Excel 写入失败: {e}", exc_info=True)
                if tmp_path and os.path.exists(tmp_path):
                    try: os.remove(tmp_path)
                    except Exception: pass
                break
        logger.error(f"写入 Excel 失败，已重试 {max_retries} 次")
        return False

    def load_data(self):
        try:
            return pd.read_excel(self.file_path)
        except PermissionError:
            logger.warning("Excel 文件被占用，返回空数据")
            return pd.DataFrame(columns=self.columns)
        except Exception as e:
            logger.error(f"读取 Excel 失败: {e}", exc_info=True)
            return pd.DataFrame(columns=self.columns)

    def is_processed(self, msg_id):
        df = self.load_data()
        if df.empty: return False
        return msg_id in df["MsgID"].values

    def on_event_saved(self, event_data: dict):
        """事件钩子：保存成功后触发，飞书等扩展可挂载于此。"""
        pass

    def save_event(self, llm_json, msg_id, original_body, received_time_obj=None,
                   event_group_id=None, force_status=None):
        """
        保存事件 (V3.0: 含去重、时间校验、新字段)
        """
        df = self.load_data()
        category = llm_json.get('category')
        title = llm_json.get('event_title')
        company_name = llm_json.get('company_name', '')
        is_flexible = llm_json.get('is_flexible_deadline', True)

        # 默认值
        final_time_str = ""
        ddl_datetime = ""
        status = "已忽略"

        # === 高价值邮件处理 ===
        if category in ['DDL', 'FIXED_SLOT', 'RESUME_UPDATE']:
            status = "未完成"
            if not title: title = f"[{category}] 未命名事项"

            if category == 'FIXED_SLOT':
                is_flexible = False  # FIXED_SLOT 永远是定点
                start = llm_json.get('start_time')
                end = llm_json.get('end_time')
                if start:
                    start_clean = start.replace('T', ' ')
                    if end:
                        try:
                            end_clean = end.replace('T', ' ').split(' ')[1][:5]
                        except (IndexError, AttributeError) as e:
                            logger.warning(f"FIXED_SLOT end_time 异常 (end={end}): {e}")
                            end_clean = end
                        final_time_str = f"{start_clean} ~ {end_clean}"
                    else:
                        final_time_str = start_clean
                    ddl_datetime = TimeValidator.normalize(start)

            elif category == 'RESUME_UPDATE':
                if received_time_obj:
                    try:
                        target_date = received_time_obj + datetime.timedelta(days=3)
                        final_time_str = target_date.strftime("%Y-%m-%d %H:%M") + " (建议)"
                        title = f"[建议3天内] {title}"
                        ddl_datetime = target_date.strftime("%Y-%m-%d %H:%M")
                    except Exception as e:
                        logger.warning(f"RESUME_UPDATE 时间推算失败: {e}")
                        final_time_str = llm_json.get('ddl', '')
                else:
                    final_time_str = llm_json.get('ddl', '')

            elif category == 'DDL':
                ddl = llm_json.get('ddl')
                if ddl:
                    final_time_str = ddl.replace('T', ' ')
                    ddl_datetime = TimeValidator.normalize(ddl)

        else:
            if not title: title = f"[{category}] 无标题"
            final_time_str = "-"

        # === 时间合理性校验 ===
        if ddl_datetime:
            is_valid, reason = TimeValidator.validate(ddl_datetime)
            if not is_valid:
                logger.warning(f"时间校验未通过: {reason}")
                ddl_datetime = ""
                if force_status is None:
                    force_status = "待人工核实"

        # 应用强制状态
        if force_status:
            status = force_status

        # 事件组 ID
        group_id = event_group_id if event_group_id else msg_id

        # --- 构造数据 ---
        new_row = {
            "MsgID": msg_id,
            "Category": category,
            "Title": title,
            "Time_Info": final_time_str,
            "Status": status,
            "Original_Body": original_body[:1000],
            "Created_At": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Event_Group_ID": group_id,
            "DDL_Datetime": ddl_datetime,
            "Company_Name": company_name,
            "Is_Flexible": is_flexible,
            "Reminder_24h": 0,
            "Reminder_2h": 0,
        }

        new_df = pd.DataFrame([new_row])
        df = pd.concat([df, new_df], ignore_index=True)

        success = self._safe_write_excel(df)

        if success:
            if status == "未完成":
                logger.info(f"💾 [Task Saved] {title}")
            elif status == "待人工核实":
                logger.info(f"⚠️ [Needs Review] {title}")
            else:
                logger.info(f"📝 [Log Saved] {category}")
            self.on_event_saved(new_row)
        else:
            logger.error(f"❌ [Excel Error] 写入失败: {title}")

        return success, new_row

    def update_status(self, msg_id, new_status):
        df = self.load_data()
        if msg_id in df["MsgID"].values:
            df.loc[df["MsgID"] == msg_id, "Status"] = new_status
            return self._safe_write_excel(df)
        return False

    def update_reminder_flag(self, msg_id, col_name):
        """标记某条提醒已发送"""
        df = self.load_data()
        if col_name not in df.columns:
            df[col_name] = 0
        if msg_id in df["MsgID"].values:
            df.loc[df["MsgID"] == msg_id, col_name] = 1
            return self._safe_write_excel(df)
        return False

    def merge_event_group(self, group_id, new_event_data: dict):
        """
        合并事件：将新邮件的时间信息更新到已有事件组中（取更精确的）。
        """
        df = self.load_data()
        mask = df["Event_Group_ID"] == group_id

        if not mask.any():
            return False

        # 用新时间覆盖旧时间（后续邮件通常包含更精确的时间）
        new_time = new_event_data.get("Time_Info", "")
        new_ddl = new_event_data.get("DDL_Datetime", "")

        if new_time and new_time != "-":
            df.loc[mask, "Time_Info"] = new_time
        if new_ddl:
            df.loc[mask, "DDL_Datetime"] = new_ddl
            # 重置提醒标记（时间变了需要重新提醒）
            df.loc[mask, "Reminder_24h"] = 0
            df.loc[mask, "Reminder_2h"] = 0

        return self._safe_write_excel(df)