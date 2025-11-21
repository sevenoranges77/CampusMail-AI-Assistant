# ==============================================
# llm_parser.py (去繁从简版 - 依赖全局补丁)
# ==============================================

import json
import datetime
import re
from openai import OpenAI
from config import Config

class LLMParser:
    def __init__(self):
        # 1. 不需要再手动配置 httpx 代理了
        # 因为 main.py 里的 proxy_patch 已经接管了所有网络流量
        
        print("🤖 LLM Client 初始化 (将使用全局代理补丁)...")

        # 2. 直接初始化 OpenAI
        # 注意：这里去掉了 http_client 参数
        self.client = OpenAI(
            api_key=Config.LLM_API_KEY,
            base_url=Config.LLM_API_BASE
        )
        
        self.model = Config.LLM_MODEL

    def parse_email(self, email_body, received_time_str):
        """
        发送邮件内容给 LLM 进行解析
        """
        current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        system_prompt = """
你是一个极其精准的“校招邮件智能助理”。你的任务是将邮件解析为严格的JSON格式。

【核心规则：时间推算与补全】
1. **缺省推断**：如果是面试/会议 (FIXED_SLOT) 但邮件只给了开始时间，请**自动假设持续1小时**，计算出 end_time。
2. **考试时间段**：如果邮件给出了具体的考试窗口（如 "15:00开始，20:00结束"），请将其归类为 **FIXED_SLOT**，并填入 start/end time。不要归类为 DDL。
3. **相对时间**：必须根据 [CONTEXT] 中的 "Email Received Time" 推算绝对日期。如 "48小时内" + 接收时间 11-20 = ddl 11-22。

Schema:
{
  "category": "DDL" | "FIXED_SLOT" | "RESUME_UPDATE" | "APPLICATION_RECEIVED" | "ADVERTISEMENT" | "OTHER_RECRUITMENT" | "OTHER_PERSONAL",
  "event_title": "string | null",
  "start_time": "YYYY-MM-DDTHH:MM:SS | null (FIXED_SLOT 必填)",
  "end_time": "YYYY-MM-DDTHH:MM:SS | null (FIXED_SLOT 必填)",
  "ddl": "YYYY-MM-DD | null (DDL 必填)",
  "summary_info": "string | null"
}

分类说明:
- FIXED_SLOT: 面试、宣讲会、**特定时段的在线考试**。
- DDL: 只有截止日期的测评/笔试/任务。
"""
        
        user_prompt = f"""
[CONTEXT]
Current Time: {current_time_str}
Email Received Time: {received_time_str}

[EMAIL BODY]
{email_body}

[OUTPUT]
请返回 JSON:
"""

        try:
            # 调用 LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1
            )
            
            raw_content = response.choices[0].message.content.strip()
            
            # 清洗数据
            match = re.search(r'\{.*\}', raw_content, re.DOTALL)
            if match:
                json_str = match.group(0)
            else:
                json_str = raw_content

            parsed_data = json.loads(json_str)
            return parsed_data

        except json.JSONDecodeError:
            print(f"❌ [LLM Error] JSON 解析失败。原始返回: {raw_content}")
            return None
        except Exception as e:
            print(f"❌ [LLM Error] API 调用失败: {e}")
            return None

if __name__ == "__main__":
    # 单独运行此文件测试时，需要手动打补丁，因为 main.py 没运行
    import proxy_patch
    proxy_patch.apply_proxy()
    
    parser = LLMParser()
    fake_body = "测试内容"
    fake_time = "2025-01-01"
    print("🤖 测试连接...")
    # 这里可能会因为内容太短被模型拒绝，主要看会不会报 Connection Error
    try:
        parser.parse_email(fake_body, fake_time)
        print("✅ 连接成功 (即使解析失败也是成功的)")
    except:
        print("❌ 连接依然失败")