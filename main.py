# ==============================================
# 1. 注入网络补丁 (确保 Google 服务能连通)
# ==============================================
import proxy_patch
proxy_patch.apply_proxy()
# ==============================================

import time
from config import Config
from mail_reader import MailReader
from llm_parser import LLMParser
from sheet_writer import SheetWriter
from calendar_writer import CalendarWriter

def main():
    print("\n" + "="*50)
    print("🚀 LLM 校招助手 (CampusMail AI) - 启动！")
    print("="*50 + "\n")

    # 1. 初始化各个模块
    print("📦 正在初始化模块...")
    try:
        reader = MailReader()
        llm = LLMParser()
        sheet = SheetWriter()
        calendar = CalendarWriter()
        print("✅ 模块初始化完成。")
    except Exception as e:
        print(f"❌ 初始化失败，请检查配置: {e}")
        return

    # 2. 获取邮件
    print(f"\n📧 正在扫描最近 {Config.LOOKBACK_DAYS} 天的邮件...")
    emails = reader.get_recent_emails()
    print(f"✅ 扫描结束，准备处理 {len(emails)} 封邮件。\n")

    # 统计数据
    stats = {"processed": 0, "skipped": 0, "created": 0, "errors": 0}

    # 3. 核心循环
    for i, email_data in enumerate(emails, 1):
        subject = email_data['subject']
        msg_id = email_data['message_id']
        sender = email_data['from']
        received_time = email_data['received_time']
        
        print(f"[{i}/{len(emails)}] 正在处理: {subject[:30]}...")

        # --- A. 幂等性检查 (查重) ---
        if sheet.is_message_processed_successfully(msg_id):
            print("   └── 🟡 [跳过] 日志显示已处理过。")
            stats["skipped"] += 1
            continue

        # --- B. LLM 智能解析 ---
        print("   └── 🤖 正在呼叫 LLM 解析...", end="", flush=True)
        llm_result = llm.parse_email(email_data['body'], received_time)
        
        if not llm_result:
            print("❌ 失败 (API错误)")
            stats["errors"] += 1
            continue
            
        category = llm_result.get('category', 'UNKNOWN')
        print(f"完成 -> 分类: [{category}]")

        # ================= 新增调试代码 =================
        # 打印出 LLM 返回的完整数据，让我们看看它到底漏了什么
        import json
        print(f"   🔍 [DEBUG] LLM原始数据: {json.dumps(llm_result, ensure_ascii=False)}")
        # ===============================================


        # --- C. 执行动作 (写日历) ---
        action_record = "Ignored" # 默认动作
        
        # 只有这三类才写日历
        if category in ['DDL', 'FIXED_SLOT', 'RESUME_UPDATE']:
            print(f"   └── 📅 发现高价值事件，正在写入日历...", end="", flush=True)
            
            # 【修改】传入 received_time
            success = calendar.create_event(llm_result, msg_id, received_time)
            if success:
                print("✅ 成功！")
                action_record = "Calendar Created"
                stats["created"] += 1
            else:
                print("❌ 失败 (参数缺失)")
                action_record = "Calendar Failed"
                stats["errors"] += 1
        else:
            print(f"   └── 🗑️ 低价值/无关邮件，忽略。")
            action_record = f"Ignored ({category})"
            stats["processed"] += 1

        # --- D. 风险审计 (写日志) ---
        # 无论如何，都要把这次判断写入 Google Sheet
        sheet.log_action(sender, subject, msg_id, category, action_record)
        
        # 礼貌性暂停，避免请求太快
        time.sleep(1)

    # 4. 总结
    print("\n" + "="*50)
    print("🏁 运行结束报告")
    print(f"Total Scanned : {len(emails)}")
    print(f"Skipped (Old): {stats['skipped']}")
    print(f"Processed    : {stats['processed']}")
    print(f"Calendar New : {stats['created']}  <-- 新增日程")
    print(f"Errors       : {stats['errors']}")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()