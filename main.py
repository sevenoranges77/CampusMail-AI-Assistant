# ==============================================
# V3.0 Main Controller - Agent Pipeline
# ==============================================
import proxy_patch
proxy_patch.apply_proxy()

import time
import datetime
import json
import os
from config import Config
from mail_reader import MailReader
from llm_parser import LLMParser
from storage_manager import StorageManager
from event_dedup import EventDeduplicator
from conflict_detector import ConflictDetector
from time_validator import TimeValidator
from feishu_pusher import FeishuPusher
from email.utils import parsedate_to_datetime
from win10toast import ToastNotifier
from logger_config import setup_logger

logger = setup_logger("CampusAI.Main")

# 停止信号文件
STOP_FLAG_FILE = ".stop_flag"


def log_msg(msg, callback=None):
    logger.info(msg)
    if callback:
        callback(msg)


def check_for_stop_signal():
    if os.path.exists(STOP_FLAG_FILE):
        try:
            os.remove(STOP_FLAG_FILE)
        except Exception as e:
            logger.warning(f"清除停止信号文件失败: {e}")
        return True
    return False


def reload_user_config():
    if os.path.exists("user_config.json"):
        try:
            with open("user_config.json", "r", encoding='utf-8') as f:
                data = json.load(f)
                Config.EMAIL_USER = data.get("EMAIL_USER", Config.EMAIL_USER)
                Config.EMAIL_PASS = data.get("EMAIL_PASS", Config.EMAIL_PASS)
                Config.LLM_API_KEY = data.get("LLM_API_KEY", Config.LLM_API_KEY)
                Config.LLM_API_BASE = data.get("LLM_API_BASE", Config.LLM_API_BASE)
                Config.LLM_MODEL = data.get("LLM_MODEL", Config.LLM_MODEL)
                Config.PROXY_HOST = data.get("PROXY_HOST", Config.PROXY_HOST)
                Config.FEISHU_WEBHOOK_URL = data.get("FEISHU_WEBHOOK_URL", Config.FEISHU_WEBHOOK_URL)
                try:
                    Config.PROXY_PORT = int(data.get("PROXY_PORT", Config.PROXY_PORT))
                except (ValueError, TypeError) as e:
                    logger.warning(f"代理端口配置无效: {e}")
        except Exception as e:
            logger.error(f"重新加载用户配置失败: {e}", exc_info=True)


def main(ui_callback=None):
    # 0. 清理旧的停止信号
    if os.path.exists(STOP_FLAG_FILE):
        try: os.remove(STOP_FLAG_FILE)
        except Exception as e:
            logger.warning(f"清理旧停止信号文件失败: {e}")

    reload_user_config()

    def ui_log(text):
        log_msg(text, ui_callback)

    ui_log("-" * 30)
    ui_log("🚀 进程启动 (V3.0)...")

    # ================= 1. 模块初始化与自检 =================
    try:
        reader = MailReader()
        llm = LLMParser()
        storage = StorageManager()
        dedup = EventDeduplicator(llm)
        conflict = ConflictDetector()
        feishu = FeishuPusher(Config.FEISHU_WEBHOOK_URL)
    except Exception as e:
        ui_log(f"❌ 模块初始化崩溃: {e}")
        logger.error("模块初始化崩溃", exc_info=True)
        return

    # [诊断 A] API 连通性测试
    ui_log("🔍 正在测试 API 连接...")
    api_ok, api_msg = llm.test_connection()
    if not api_ok:
        ui_log(api_msg)
        ui_log("🛑 流程终止：请先修复 API 配置")
        return
    ui_log(api_msg)

    # [诊断 B] 邮箱连通性测试
    ui_log("🔍 正在连接邮箱服务器...")
    try:
        reader.connect()
        ui_log("✅ 邮箱连接成功")
    except Exception as e:
        ui_log(str(e))
        ui_log("🛑 流程终止：请修复邮箱配置")
        return

    # ================= 2. 邮件获取 =================
    ui_log(f"📧 正在扫描最近 {Config.LOOKBACK_DAYS} 天的邮件...")
    if check_for_stop_signal():
        ui_log("🛑 用户取消操作")
        return

    try:
        emails = reader.get_recent_emails()
    except Exception as e:
        ui_log(f"❌ 扫描过程出错: {e}")
        logger.error("邮件扫描异常", exc_info=True)
        return

    if not emails:
        ui_log("⚠️ 未获取到新邮件 (可能是全已读或配置了只收最近30天)")
        
        # === 飞书推送 (即使没有新邮件也推送扫描完成状态) ===
        if feishu.enabled:
            feishu.send_scan_summary({"new_ddl": 0, "total_ddl": 0, "pending_ddl": 0, "new_interview": 0, "interview_details": []})
            
        return

    ui_log(f"✅ 准备处理 {len(emails)} 封邮件")

    # ================= 3. 核心循环 =================
    stats = {"saved": 0, "logged": 0, "skipped": 0, "errors": 0}
    scan_stats = {
        "new_ddl": 0, "total_ddl": 0, "pending_ddl": 0,
        "new_interview": 0, "interview_details": []
    }
    consecutive_errors = 0
    all_conflicts = []

    for i, email_data in enumerate(emails, 1):
        if check_for_stop_signal():
            ui_log("🛑 检测到停止信号，正在保存进度并退出...")
            break

        subject = email_data['subject']
        msg_id = email_data['message_id']
        received_time_str = email_data['received_time']

        try:
            received_time_obj = parsedate_to_datetime(received_time_str)
        except Exception as e:
            logger.warning(f"邮件时间解析失败 (Date={received_time_str}): {e}")
            received_time_obj = datetime.datetime.now()

        ui_log(f"[{i}/{len(emails)}] {subject[:15]}...")

        # 检查是否已处理
        if storage.is_processed(msg_id):
            ui_log(f"   🟡 跳过 (已存在)")
            stats["skipped"] += 1
            continue

        # 调用 LLM 解析
        ui_log(f"   🤖 解析中...")
        llm_result = llm.parse_email(email_data['body'], received_time_str)

        if not llm_result:
            ui_log("   ❌ 解析失败 (API返回异常)")
            stats["errors"] += 1
            consecutive_errors += 1
            if consecutive_errors >= 5:
                ui_log("🛑 连续 5 次解析失败，疑似 API 服务不稳定，自动停止。")
                break
            continue

        consecutive_errors = 0
        category = llm_result.get('category', 'UNKNOWN')
        ui_log(f"   ✅ 识别为: [{category}]")

        # === Phase 1: 三层去重 ===
        group_id = dedup.resolve_group(email_data, llm_result, storage.load_data())
        if group_id != msg_id:
            ui_log(f"   🔗 合并至已有事件组")

        # === Phase 2: 保存 ===
        success, new_row = storage.save_event(
            llm_json=llm_result,
            msg_id=msg_id,
            original_body=email_data['body'],
            received_time_obj=received_time_obj,
            event_group_id=group_id
        )

        if success:
            if category in ['DDL', 'FIXED_SLOT', 'RESUME_UPDATE']:
                stats["saved"] += 1

                # 更新扫描统计
                if category == 'DDL':
                    scan_stats["new_ddl"] += 1
                elif category == 'FIXED_SLOT':
                    scan_stats["new_interview"] += 1
                    scan_stats["interview_details"].append({
                        "title": llm_result.get("event_title", "未知面试"),
                        "time": new_row.get("Time_Info", "待确认")
                    })

                # === Phase 3: 冲突检测 ===
                is_flexible = llm_result.get('is_flexible_deadline', True)
                if not is_flexible and new_row.get("DDL_Datetime"):
                    conflicts = conflict.check_new_event_conflicts(
                        new_row, storage.load_data()
                    )
                    if conflicts:
                        all_conflicts.extend(conflicts)
                        for c in conflicts:
                            ui_log(f"   ⚠️ 冲突: {c['overlap_desc']}")
            else:
                stats["logged"] += 1
        else:
            ui_log("   ❌ 写入数据库失败 (文件被占用?)")
            stats["errors"] += 1

        time.sleep(0.5)

    # ================= 4. 收尾 =================
    ui_log("-" * 30)
    summary = f"新增 {stats['saved']} | 跳过 {stats['skipped']} | 失败 {stats['errors']}"
    ui_log(f"🏁 运行结束: {summary}")

    # 计算总体统计（含历史数据）
    df = storage.load_data()
    if not df.empty:
        ddl_df = df[(df["Category"] == "DDL") & (df["Status"] != "已忽略")]
        scan_stats["total_ddl"] = len(ddl_df)
        scan_stats["pending_ddl"] = len(ddl_df[ddl_df["Status"] == "未完成"])

    # === 飞书推送 ===
    if feishu.enabled:
        # 扫描摘要
        feishu.send_scan_summary(scan_stats)
        # 冲突告警
        if all_conflicts:
            feishu.send_conflict_alert(all_conflicts)

    # 桌面通知
    if stats['saved'] > 0:
        try:
            toaster = ToastNotifier()
            toaster.show_toast(
                "CampusAI 校招助手",
                f"处理完成！发现了 {stats['saved']} 个新事项。",
                duration=5,
                threaded=True
            )
        except Exception as e:
            logger.warning(f"桌面通知发送失败: {e}")


if __name__ == "__main__":
    main()