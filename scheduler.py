# ==============================================
# scheduler.py (V3.0 - APScheduler 调度引擎)
# ==============================================
import datetime
import json
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from logger_config import setup_logger

logger = setup_logger("CampusAI.Scheduler")

# 上次扫描时间记录文件
LAST_SCAN_FILE = ".last_scan"


class TaskScheduler:
    """
    后台调度引擎：
    - 每日定时邮件扫描
    - 每小时 DDL 提醒检查
    """

    def __init__(self):
        self.scheduler = BackgroundScheduler(daemon=True)
        self._load_config()

    def _load_config(self):
        """从 user_config.json 读取调度相关配置"""
        self.scan_enabled = True
        self.scan_cron = "0 9 * * *"
        self.feishu_webhook = ""
        self.reminder_hours = [24, 2]

        if os.path.exists("user_config.json"):
            try:
                with open("user_config.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.scan_enabled = data.get("AUTO_SCAN_ENABLED", True)
                    self.scan_cron = data.get("AUTO_SCAN_CRON", "0 9 * * *")
                    self.feishu_webhook = data.get("FEISHU_WEBHOOK_URL", "")
                    self.reminder_hours = data.get("REMINDER_HOURS", [24, 2])
            except Exception as e:
                logger.error(f"调度器读取配置失败: {e}")

    def start(self):
        """启动调度器"""
        if self.scan_enabled:
            self.scheduler.add_job(
                func=self._run_scan_job,
                trigger=CronTrigger.from_crontab(self.scan_cron),
                id="daily_email_scan",
                replace_existing=True,
                misfire_grace_time=3600  # 错过 1 小时内仍补执行
            )
            logger.info(f"⏰ 每日扫描已启用: cron={self.scan_cron}")
        else:
            logger.info("⏰ 每日扫描已关闭")

        # 每小时提醒检查（整点触发）
        self.scheduler.add_job(
            func=self._run_reminder_check,
            trigger=CronTrigger(minute=0),
            id="hourly_reminder_check",
            replace_existing=True
        )
        logger.info("⏰ 每小时 DDL 提醒检查已启用")

        self.scheduler.start()

    def shutdown(self):
        """关闭调度器"""
        try:
            self.scheduler.shutdown(wait=False)
            logger.info("调度器已关闭")
        except Exception:
            pass

    @property
    def next_run_time(self) -> str:
        """下次扫描时间（供托盘菜单显示）"""
        try:
            job = self.scheduler.get_job("daily_email_scan")
            if job and job.next_run_time:
                return job.next_run_time.strftime("%H:%M")
        except Exception:
            pass
        return "未配置"

    @property
    def last_scan_time(self) -> str:
        """上次扫描时间"""
        try:
            if os.path.exists(LAST_SCAN_FILE):
                with open(LAST_SCAN_FILE, "r") as f:
                    return f.read().strip()
        except Exception:
            pass
        return "从未扫描"

    def run_scan_now(self):
        """手动立即触发扫描"""
        logger.info("🔄 手动触发扫描")
        self._run_scan_job()

    def _run_scan_job(self):
        """执行邮件扫描全流程"""
        logger.info("=" * 30)
        logger.info("⏰ [定时任务] 开始邮件扫描...")

        try:
            # 延迟导入，避免循环引用
            import main
            main.main(ui_callback=None)

            # 记录本次扫描时间
            with open(LAST_SCAN_FILE, "w") as f:
                f.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            logger.info("⏰ [定时任务] 扫描完成")
        except Exception as e:
            logger.error(f"⏰ [定时任务] 扫描异常: {e}", exc_info=True)

    def _run_reminder_check(self):
        """每小时运行一次：检查是否有需要提醒的事件"""
        logger.debug("[提醒检查] 开始...")

        try:
            from storage_manager import StorageManager
            from feishu_pusher import FeishuPusher

            storage = StorageManager()
            df = storage.load_data()
            feishu = FeishuPusher(self.feishu_webhook)

            if not feishu.enabled:
                return

            now = datetime.datetime.now()
            pending_reminders = []

            for _, row in df.iterrows():
                if str(row.get("Status", "")) != "未完成":
                    continue
                if str(row.get("Category", "")) not in ("DDL", "FIXED_SLOT"):
                    continue

                ddl_str = str(row.get("DDL_Datetime", "")).strip()
                if not ddl_str or len(ddl_str) < 10:
                    continue

                try:
                    ddl_time = datetime.datetime.strptime(ddl_str, "%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    continue

                remaining_hours = (ddl_time - now).total_seconds() / 3600

                # 检查各个提醒时间点
                for hours_before in self.reminder_hours:
                    col_name = f"Reminder_{hours_before}h"

                    # 是否已发送过该提醒
                    already_sent = False
                    if col_name in df.columns:
                        already_sent = bool(row.get(col_name))

                    if already_sent:
                        continue

                    # 判断是否在提醒窗口内 (±0.5 小时)
                    if (hours_before - 0.5) <= remaining_hours <= (hours_before + 0.5):
                        pending_reminders.append({
                            "title": str(row.get("Title", "未知事项")),
                            "remaining_hours": remaining_hours,
                            "msg_id": str(row.get("MsgID", "")),
                            "reminder_col": col_name
                        })

            if pending_reminders:
                # 批量推送
                feishu.send_batch_reminders(pending_reminders)

                # 标记已发送
                for r in pending_reminders:
                    storage.update_reminder_flag(r["msg_id"], r["reminder_col"])

                logger.info(f"[提醒检查] 已发送 {len(pending_reminders)} 条提醒")
            else:
                logger.debug("[提醒检查] 无需提醒")

        except Exception as e:
            logger.error(f"[提醒检查] 异常: {e}", exc_info=True)
