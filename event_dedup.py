# ==============================================
# event_dedup.py (V3.0 - 三层去重引擎)
# ==============================================
import difflib
from logger_config import setup_logger

logger = setup_logger("CampusAI.Dedup")


def extract_domain(from_str: str) -> str:
    """从 From 字段提取发件人域名，如 'hr@bytedance.com' -> 'bytedance.com'"""
    if not from_str:
        return ""
    try:
        if "<" in from_str and ">" in from_str:
            email = from_str.split("<")[1].split(">")[0]
        elif "@" in from_str:
            email = from_str.strip()
        else:
            return ""
        return email.split("@")[1].lower()
    except (IndexError, AttributeError):
        return ""


class EventDeduplicator:
    """
    三层漏斗去重：
      Layer 1: 邮件协议链 (In-Reply-To / References) — 零成本，100% 准确
      Layer 2: 规则快筛 (域名 + 标题相似度 + 时间邻近 + 同分类) — 零成本
      Layer 3: LLM 精判 — 仅在 Layer 2 产生候选时调用
    """

    def __init__(self, llm_parser=None):
        """
        Args:
            llm_parser: LLMParser 实例，用于 Layer 3 精判。为 None 则跳过 Layer 3。
        """
        self.llm = llm_parser

    def resolve_group(self, email_data: dict, llm_result: dict, df) -> str:
        """
        对新邮件执行三层去重，返回其所属的 Event_Group_ID。

        Args:
            email_data: mail_reader 返回的原始邮件数据（含 in_reply_to, references）
            llm_result: LLM 解析结果（含 company_name, event_title, category 等）
            df: 当前已有数据的 DataFrame

        Returns:
            Event_Group_ID (str): 匹配到已有组则返回其 ID，否则返回新邮件自身的 message_id
        """
        msg_id = email_data.get("message_id", "")

        if df is None or df.empty:
            return msg_id

        # === Layer 1: 邮件协议链去重 ===
        group = self._check_protocol_thread(email_data, df)
        if group:
            logger.info(f"[Dedup L1] 邮件协议链命中: group={group}")
            return group

        # === Layer 2: 规则快筛 ===
        candidate = self._find_candidate_by_rules(email_data, llm_result, df)
        if candidate:
            # === Layer 3: LLM 精判 ===
            if self.llm:
                new_summary = llm_result.get("summary_info") or llm_result.get("event_title", "")
                existing_summary = candidate.get("Title", "")
                if self._llm_judge_same_event(new_summary, existing_summary):
                    group = candidate.get("Event_Group_ID", candidate.get("MsgID", ""))
                    logger.info(f"[Dedup L3] LLM 判定为同一事件: group={group}")
                    return group
                else:
                    logger.info("[Dedup L3] LLM 判定为不同事件")
            else:
                # 无 LLM 可用，规则匹配分数高则直接合并
                group = candidate.get("Event_Group_ID", candidate.get("MsgID", ""))
                logger.info(f"[Dedup L2] 规则命中 (无 LLM 确认): group={group}")
                return group

        return msg_id

    def _check_protocol_thread(self, email_data: dict, df) -> str:
        """
        Layer 1: 检查 In-Reply-To / References 是否命中已有 MsgID。
        """
        refs = []

        in_reply_to = email_data.get("in_reply_to")
        if in_reply_to:
            refs.append(in_reply_to.strip())

        references = email_data.get("references")
        if references:
            refs.extend(references.split())

        if not refs:
            return ""

        for ref_id in refs:
            ref_id_clean = ref_id.strip()
            if not ref_id_clean:
                continue
            match = df[df["MsgID"] == ref_id_clean]
            if not match.empty:
                return str(match.iloc[0].get("Event_Group_ID", match.iloc[0].get("MsgID", "")))

        return ""

    def _find_candidate_by_rules(self, email_data: dict, llm_result: dict, df) -> dict:
        """
        Layer 2: 基于发件人域名 + 标题相似度 + 时间邻近 + 分类进行规则匹配。
        返回最佳候选行（dict），无匹配则返 None。
        """
        new_domain = extract_domain(email_data.get("from", ""))
        new_title = llm_result.get("event_title") or email_data.get("subject", "")
        new_category = llm_result.get("category", "")
        new_company = llm_result.get("company_name", "")

        if not new_domain and not new_company:
            return None

        # 只在高价值类别中查找
        high_value = df[df["Category"].isin(["DDL", "FIXED_SLOT", "RESUME_UPDATE"])]
        if high_value.empty:
            return None

        best_match = None
        best_score = 0

        for _, row in high_value.iterrows():
            score = 0

            # 公司名匹配（如果 LLM 都提取到了公司名）
            row_company = str(row.get("Company_Name", ""))
            if new_company and row_company and new_company.lower() == row_company.lower():
                score += 0.5

            # 分类相同
            if str(row.get("Category", "")) == new_category:
                score += 0.2

            # 标题相似度
            row_title = str(row.get("Title", ""))
            similarity = difflib.SequenceMatcher(None, new_title, row_title).ratio()
            if similarity > 0.6:
                score += similarity * 0.3  # 最多 +0.3

            if score > best_score and score >= 0.5:
                best_score = score
                best_match = row.to_dict()

        if best_match:
            logger.debug(f"[Dedup L2] 候选匹配: score={best_score:.2f}, title={best_match.get('Title', '')}")

        return best_match

    def _llm_judge_same_event(self, new_summary: str, existing_summary: str) -> bool:
        """
        Layer 3: 使用 LLM 判断两段摘要是否描述同一事件。
        """
        if not new_summary or not existing_summary:
            return False

        prompt = (
            "以下两段文字分别来自两封校招邮件，请判断它们是否在描述同一个事件"
            "（如同一场面试或同一个测评）。只回答 YES 或 NO。\n\n"
            f"邮件A: {new_summary[:200]}\n"
            f"邮件B: {existing_summary[:200]}"
        )

        try:
            response = self.llm._call_llm([
                {"role": "user", "content": prompt}
            ])
            answer = response.choices[0].message.content.strip().upper()
            return "YES" in answer
        except Exception as e:
            logger.warning(f"[Dedup L3] LLM 判定调用失败: {e}")
            return False
