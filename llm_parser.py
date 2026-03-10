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
你是一个极其精准的"校招邮件智能分类与解析助理"。你的任务是将邮件精准分类，并转化为严格的 JSON 格式。

【第一步：核心意图分类（最重要）】
你必须首先根据邮件的真实意图进行分类。特别注意区分【群发引流宣讲】与【个人专属待办】。

1. ADVERTISEMENT（广告/宣讲/邀请报名 - 高优拦截）:
   - 邀请参加：线下/线上宣讲会、直播宣讲、Open Day、座谈会。
   - 鼓励投递：网申启动通知、简历投递邀请、人才库储备、各类赛事或训练营报名邀请。
   - 特征：包含大量“退订”、“精彩回顾”等营销词汇。
   - 注意：绝对不能因为邮件里有“宣讲会开始时间”或“报名截止时间”就将其判定为面试或测评。只要是群发邀请参与公共活动的，都是广告！

2. DDL（个人专属 - 测评/笔试/材料补充）:
   - 发给个人的专属在线测评、笔试链接。
   - 要求用户在某个期限前补充简历信息、提交作品集或填写信息收集表。
   - 注意：一定是在用户网申后产生的待办任务。单纯邀请“报名某个比赛”属于 ADVERTISEMENT。

3. FIXED_SLOT（个人专属 - 面试/定点时段考试）:
   - 单独为用户个人安排的具体面试（如一面、二面、HR面）或指明了准确参加时段的正式上机考试。
   - 注意：切勿将“某日举办宣讲会”误判为 FIXED_SLOT！

4. APPLICATION_RECEIVED / RESUME_UPDATE（状态流转）:
   - 投递成功/感谢信/简历进入人才库/状态流转通知。

5. OTHER_RECRUITMENT / OTHER_PERSONAL:
   - 不属于上述分类的其他招聘邮件或无关私人邮件。

【第二步：时间推算与清洗】（主要针对 DDL 和 FIXED_SLOT）
1. DDL 精确度：如包含具体时刻（"20:00"）保留时分秒 `YYYY-MM-DDTHH:MM:SS`，否则仅提取日期 `YYYY-MM-DD`。
2. 清洗脏数据：自动剔除“星期六”、“GMT+8”、“北京时间”等干扰词，只提取纯净的标准时间。
3. 缺省推断：如果是 FIXED_SLOT 但仅有开始时间，自动假设持续 1 小时计算 end_time。
4. 弹性截止判断 (is_flexible_deadline)：针对 DDL，判断是弹性期限（如"3天内完成", true）还是定点时段（如"仅限明日14:00进行", false）。FIXED_SLOT 此项固定为 false。

Schema:
{
  "category": "DDL" | "FIXED_SLOT" | "RESUME_UPDATE" | "APPLICATION_RECEIVED" | "ADVERTISEMENT" | "OTHER_RECRUITMENT" | "OTHER_PERSONAL",
  "event_title": "string | null (精简标题或活动名称)",
  "company_name": "string | null (发送方公司/组织名)",
  "start_time": "YYYY-MM-DDTHH:MM:SS | null",
  "end_time": "YYYY-MM-DDTHH:MM:SS | null",
  "ddl": "string | null (格式如 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS)", 
  "is_flexible_deadline": "boolean",
  "summary_info": "string | null"
}
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