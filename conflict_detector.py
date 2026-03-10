# ==============================================
# conflict_detector.py (V3.0 - 冲突检测引擎)
# ==============================================
import datetime
from logger_config import setup_logger

logger = setup_logger("CampusAI.Conflict")


class ConflictDetector:
    """
    智能冲突检测：
    - 仅定点时段（FIXED_SLOT / 定点笔试 DDL）参与冲突检测
    - 弹性 DDL（如"3天内完成测评"）永不冲突
    - 同一 Event_Group_ID 的事件永不冲突
    """

    @staticmethod
    def should_check_conflict(event: dict) -> bool:
        """判断该事件是否需要参与冲突检测"""
        # 弹性 DDL 不参与
        is_flexible = event.get("Is_Flexible")
        if is_flexible is True or str(is_flexible) == "1" or str(is_flexible).lower() == "true":
            return False

        # DDL_Datetime 为空（含待人工核实）不参与
        ddl_dt = event.get("DDL_Datetime")
        if not ddl_dt or str(ddl_dt).strip() in ("", "-", "nan"):
            return False

        # 只有未完成的任务参与
        status = str(event.get("Status", ""))
        if status not in ("未完成",):
            return False

        # 只有 FIXED_SLOT 和非弹性 DDL 参与
        category = str(event.get("Category", ""))
        if category not in ("FIXED_SLOT", "DDL"):
            return False

        return True

    @staticmethod
    def _parse_time_range(event: dict) -> tuple:
        """
        从事件中解析出 (start_datetime, end_datetime)。
        如果只有 start 没有 end，默认持续 1 小时。

        Returns:
            (start: datetime | None, end: datetime | None)
        """
        ddl_str = str(event.get("DDL_Datetime", "")).strip()
        time_info = str(event.get("Time_Info", "")).strip()

        start_dt = None
        end_dt = None

        # 优先从 Time_Info 解析范围（如 "2026-03-10 14:00 ~ 15:00"）
        if "~" in time_info:
            try:
                parts = time_info.split("~")
                start_part = parts[0].strip()
                end_part = parts[1].strip()

                # 解析 start
                start_dt = datetime.datetime.strptime(start_part, "%Y-%m-%d %H:%M")

                # end 可能是完整时间或只有时分
                if len(end_part) <= 5:
                    # 只有时分，如 "15:00"
                    end_time = datetime.datetime.strptime(end_part, "%H:%M")
                    end_dt = start_dt.replace(hour=end_time.hour, minute=end_time.minute)
                else:
                    end_dt = datetime.datetime.strptime(end_part, "%Y-%m-%d %H:%M")

                return start_dt, end_dt
            except (ValueError, IndexError):
                pass

        # 回退：从 DDL_Datetime 解析
        if ddl_str:
            try:
                start_dt = datetime.datetime.strptime(ddl_str, "%Y-%m-%d %H:%M")
                end_dt = start_dt + datetime.timedelta(hours=1)
                return start_dt, end_dt
            except ValueError:
                pass

        return None, None

    @staticmethod
    def _is_time_overlap(event_a: dict, event_b: dict) -> bool:
        """判断两个事件的时间段是否重叠"""
        a_start, a_end = ConflictDetector._parse_time_range(event_a)
        b_start, b_end = ConflictDetector._parse_time_range(event_b)

        if not all([a_start, a_end, b_start, b_end]):
            return False

        # 经典区间重叠判断: A_start < B_end AND B_start < A_end
        return a_start < b_end and b_start < a_end

    def check_new_event_conflicts(self, new_event: dict, df) -> list:
        """
        检查新事件是否与已有事件存在时间冲突。

        Args:
            new_event: 新事件数据（dict）
            df: 已有事件 DataFrame

        Returns:
            冲突列表: [{"event_a": {...}, "event_b": {...}, "overlap_desc": "..."}]
        """
        if not self.should_check_conflict(new_event):
            return []

        if df is None or df.empty:
            return []

        conflicts = []

        for _, row in df.iterrows():
            existing = row.to_dict()

            if not self.should_check_conflict(existing):
                continue

            # 同组事件永不冲突
            new_group = str(new_event.get("Event_Group_ID", ""))
            existing_group = str(existing.get("Event_Group_ID", ""))
            if new_group and existing_group and new_group == existing_group:
                continue

            if self._is_time_overlap(new_event, existing):
                a_start, a_end = self._parse_time_range(new_event)
                b_start, b_end = self._parse_time_range(existing)

                overlap_desc = (
                    f"{new_event.get('Title', '新事件')} "
                    f"({a_start.strftime('%m-%d %H:%M')}~{a_end.strftime('%H:%M')}) "
                    f"与 {existing.get('Title', '已有事件')} "
                    f"({b_start.strftime('%m-%d %H:%M')}~{b_end.strftime('%H:%M')}) "
                    f"时间重叠"
                )

                conflicts.append({
                    "event_a": new_event,
                    "event_b": existing,
                    "overlap_desc": overlap_desc
                })
                logger.warning(f"⚠️ 检测到冲突: {overlap_desc}")

        return conflicts
