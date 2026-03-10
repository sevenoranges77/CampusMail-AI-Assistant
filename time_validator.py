# ==============================================
# time_validator.py (V3.0 - 时间合理性校验器)
# ==============================================
import datetime
from logger_config import setup_logger

logger = setup_logger("CampusAI.TimeValidator")


class TimeValidator:
    """
    时间合理性校验器：拦截 LLM 产生的脏数据（年份幻觉、极端未来等），
    防止错误时间参与冲突检测产生误报。
    """

    FORMATS = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]

    @staticmethod
    def validate(time_str: str, received_time: datetime.datetime = None) -> tuple:
        """
        校验时间是否合理。

        Args:
            time_str: 待校验的时间字符串
            received_time: 邮件接收时间（可选，用于辅助判断）

        Returns:
            (is_valid: bool, reason: str)
        """
        if not time_str or not isinstance(time_str, str):
            return False, "时间为空或类型异常"

        # 清洗 T 分隔符
        clean_str = time_str.strip().replace("T", " ")

        dt = None
        for fmt in TimeValidator.FORMATS:
            try:
                dt = datetime.datetime.strptime(clean_str, fmt)
                break
            except ValueError:
                continue

        if dt is None:
            return False, f"格式解析失败 (输入={time_str})"

        now = datetime.datetime.now()

        # 规则 1: 年份必须是当前年或次年
        if dt.year not in (now.year, now.year + 1):
            return False, f"年份异常 (解析={dt.year}, 当前={now.year})"

        # 规则 2: 不应早于当前时间超过 24 小时
        if dt < now - datetime.timedelta(hours=24):
            return False, f"时间早于当前超过24h (解析={clean_str})"

        # 规则 3: 不应晚于当前时间超过 180 天
        if dt > now + datetime.timedelta(days=180):
            return False, f"时间晚于当前超过180天 (解析={clean_str})"

        return True, "OK"

    @staticmethod
    def normalize(time_str: str) -> str:
        """
        将各种时间格式规范化为 'YYYY-MM-DD HH:MM'。
        如果只有日期没有时间，默认为当日 23:59。
        """
        if not time_str:
            return ""

        clean_str = time_str.strip().replace("T", " ")

        for fmt in TimeValidator.FORMATS:
            try:
                dt = datetime.datetime.strptime(clean_str, fmt)
                # 如果原始格式是纯日期，默认设为 23:59
                if fmt == "%Y-%m-%d":
                    dt = dt.replace(hour=23, minute=59)
                return dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                continue

        return ""
