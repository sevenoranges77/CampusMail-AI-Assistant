# ==============================================
# feishu_pusher.py (V3.0 - 飞书 Webhook 推送)
# ==============================================
import time
import requests
from logger_config import setup_logger

logger = setup_logger("CampusAI.Feishu")


class FeishuPusher:
    """
    飞书自定义机器人 Webhook 推送服务。
    - 扫描完成摘要卡片
    - DDL 临近批量提醒卡片
    - 冲突告警卡片
    - 内置发送限流 (防触发飞书频率限制)
    """

    MIN_SEND_INTERVAL = 1.0  # 秒

    def __init__(self, webhook_url: str = ""):
        self.webhook_url = webhook_url
        self.enabled = bool(webhook_url)
        self._last_send_time = 0

    # ==================== 公开接口 ====================

    def send_scan_summary(self, stats: dict):
        """
        扫描完成后推送摘要卡片。

        stats 结构:
        {
            "new_ddl": int, "total_ddl": int, "pending_ddl": int,
            "new_interview": int,
            "interview_details": [{"title": str, "time": str}]
        }
        """
        if not self.enabled:
            return

        # 取消拦截，始终推送扫描卡片
        # if stats.get("new_ddl", 0) == 0 and stats.get("new_interview", 0) == 0:
        #     return

        card = self._build_summary_card(stats)
        self._post(card)

    def send_batch_reminders(self, reminders: list):
        """
        批量 DDL 提醒：将多条临近提醒聚合为一张卡片。

        reminders = [{"title": str, "remaining_hours": float}, ...]
        """
        if not self.enabled or not reminders:
            return

        card = self._build_batch_reminder_card(reminders)
        self._post(card)

    def send_conflict_alert(self, conflicts: list):
        """
        冲突告警卡片。

        conflicts = [{"event_a": dict, "event_b": dict, "overlap_desc": str}]
        """
        if not self.enabled or not conflicts:
            return

        card = self._build_conflict_card(conflicts)
        self._post(card)

    def send_test_message(self):
        """发送测试消息，验证 Webhook 连通性。"""
        if not self.enabled:
            return False, "未配置 Webhook URL"

        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "🔔 CampusAI 测试消息"},
                    "template": "turquoise"
                },
                "elements": [{
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "✅ 飞书推送配置成功！后续扫描结果将自动推送至此。"
                    }
                }]
            }
        }

        return self._post(card)

    # ==================== 卡片构建 ====================

    def _build_summary_card(self, stats: dict) -> dict:
        elements = []

        # 测评摘要
        if stats.get("total_ddl", 0) > 0 or stats.get("new_ddl", 0) > 0:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"📝 **测评**: 新增 {stats.get('new_ddl', 0)} 份 | "
                        f"共 {stats.get('total_ddl', 0)} 份 | "
                        f"未完成 **{stats.get('pending_ddl', 0)}** 份"
                    )
                }
            })

        # 面试详情
        for iv in stats.get("interview_details", []):
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"🎤 **面试**: {iv['title']} | ⏰ {iv['time']}"
                }
            })

        if not elements:
            return {}

        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "📧 CampusAI 扫描报告"},
                    "template": "turquoise"
                },
                "elements": elements
            }
        }

    def _build_batch_reminder_card(self, reminders: list) -> dict:
        count = len(reminders)
        # 只要有一项 <= 2h, 整张卡用红色
        has_urgent = any(r.get("remaining_hours", 99) <= 2 for r in reminders)
        template = "red" if has_urgent else "orange"

        elements = []
        for r in reminders:
            hours = r.get("remaining_hours", 0)
            if hours >= 1:
                time_text = f"{int(hours)} 小时"
            else:
                time_text = f"{int(hours * 60)} 分钟"

            icon = "🔴" if hours <= 2 else "🟠"
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"{icon} **{r.get('title', '未知事项')}** — 还剩 {time_text}"
                }
            })

        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"⏰ DDL 提醒 ({count} 项即将截止)"
                    },
                    "template": template
                },
                "elements": elements
            }
        }

    def _build_conflict_card(self, conflicts: list) -> dict:
        elements = []
        for c in conflicts:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"⚠️ {c.get('overlap_desc', '时间冲突')}"
                }
            })

        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "请及时处理时间冲突！"
            }
        })

        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"⚠️ 时间冲突告警 ({len(conflicts)} 项)"},
                    "template": "red"
                },
                "elements": elements
            }
        }

    # ==================== 发送 (带限流) ====================

    def _post(self, payload: dict) -> tuple:
        """
        带限流的 HTTP POST。
        Returns: (success: bool, message: str)
        """
        if not payload:
            return False, "空消息体"

        # 限流
        elapsed = time.time() - self._last_send_time
        if elapsed < self.MIN_SEND_INTERVAL:
            time.sleep(self.MIN_SEND_INTERVAL - elapsed)

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=5)
            self._last_send_time = time.time()

            if resp.status_code == 200:
                resp_data = resp.json()
                if resp_data.get("code") == 0:
                    logger.info("✅ 飞书推送成功")
                    return True, "推送成功"
                else:
                    msg = f"飞书返回错误: {resp_data.get('msg', 'unknown')}"
                    logger.warning(msg)
                    return False, msg
            else:
                msg = f"飞书推送异常 (HTTP {resp.status_code})"
                logger.warning(msg)
                return False, msg
        except requests.Timeout:
            msg = "飞书推送超时"
            logger.error(msg)
            return False, msg
        except Exception as e:
            msg = f"飞书推送失败: {e}"
            logger.error(msg)
            return False, msg
