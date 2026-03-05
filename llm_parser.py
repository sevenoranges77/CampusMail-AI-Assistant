# ==============================================
# llm_parser.py (V3.0 - 指数退避重试 + 结构化日志)
# ==============================================

import json
import datetime
import re
from openai import OpenAI, AuthenticationError, APIConnectionError, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
from config import Config
from logger_config import setup_logger
import logging

logger = setup_logger("CampusAI.LLM")

class LLMParser:
    def __init__(self):
        # 初始化 OpenAI 客户端
        # 注意：网络流量由 main.py 中的 proxy_patch 接管
        logger.info("🤖 LLM Client 初始化...")
        self.client = OpenAI(
            api_key=Config.LLM_API_KEY,
            base_url=Config.LLM_API_BASE
        )
        self.model = Config.LLM_MODEL

    def test_connection(self):
        """
        连通性探针：用于在正式解析前测试 API Key 和网络状态
        """
        try:
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1
            )
            return True, "✅ API 连接正常"
        except AuthenticationError:
            return False, "❌ API Key 无效或已过期 (401)"
        except RateLimitError:
            return False, "❌ 账户余额不足或触发限流 (429)"
        except APIConnectionError:
            return False, "❌ 无法连接 API 服务器，请检查网络或代理"
        except Exception as e:
            return False, f"❌ API 未知错误: {str(e)[:50]}..."

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    def _call_llm(self, messages):
        """
        带指数退避重试的 LLM 调用封装。
        仅对 RateLimitError (429) 和 APIConnectionError 进行重试。
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1
        )
        return response

    def parse_email(self, email_body, received_time_str):
        """
        发送邮件内容给 LLM 进行解析
        """
        current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        system_prompt = """
你是一个极其精准的"校招邮件智能助理"。你的任务是将邮件解析为严格的 JSON 格式。

【核心规则：时间推算与清洗】
1. **DDL 精确度**：如果邮件中的截止时间包含具体时刻（如 "20:00" 或 "收到邮件后48小时"），**必须保留时分秒**，格式为 YYYY-MM-DDTHH:MM:SS。只有当邮件只给了日期时，才使用 YYYY-MM-DD。
2. **清洗脏数据**：邮件中的时间常带有干扰词（如 "星期六"、"GMT+8"、"北京时间"）。请**自动剔除**这些干扰，只提取标准时间。
   - 输入: "2025-11-22 15:00 星期六" -> 输出: "2025-11-22T15:00:00"
3. **缺省推断**：如果是 FIXED_SLOT 但只给了开始时间，自动假设持续 1 小时计算 end_time。
4. **广告过滤**：如果邮件中包含"退订"、"投诉"、"直播"、"宣讲"等广告高频词，请**自动剔除**这些邮件，不进行解析。

Schema:
{
  "category": "DDL" | "FIXED_SLOT" | "RESUME_UPDATE" | "APPLICATION_RECEIVED" | "ADVERTISEMENT" | "OTHER_RECRUITMENT" | "OTHER_PERSONAL",
  "event_title": "string | null",
  "start_time": "YYYY-MM-DDTHH:MM:SS | null",
  "end_time": "YYYY-MM-DDTHH:MM:SS | null",
  "ddl": "string | null (格式: YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS)", 
  "summary_info": "string | null"
}

分类说明:
- DDL: 测评/笔试 (务必尽可能精确到分钟)。
- FIXED_SLOT: 面试/特定时段考试 (务必清洗掉星期几等字符)。
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
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self._call_llm(messages)
            
            raw_content = response.choices[0].message.content.strip()
            
            # 清洗数据，提取 JSON
            match = re.search(r'\{.*\}', raw_content, re.DOTALL)
            if match:
                json_str = match.group(0)
            else:
                json_str = raw_content

            parsed_data = json.loads(json_str)
            return parsed_data

        except json.JSONDecodeError:
            logger.error(f"JSON 解析失败。原始返回: {raw_content}")
            return None
        except (RateLimitError, APIConnectionError) as e:
            # tenacity 重试耗尽后仍然失败
            logger.error(f"API 调用在重试后仍然失败: {e}")
            return None
        except Exception as e:
            logger.error(f"API 调用失败: {e}", exc_info=True)
            return None

if __name__ == "__main__":
    import proxy_patch
    proxy_patch.apply_proxy()
    parser = LLMParser()
    success, msg = parser.test_connection()
    print(msg)