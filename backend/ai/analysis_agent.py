"""
缠论 + LLM 智能分析 — 将缠论分析结果交给大模型生成策略建议
"""
import json
import re
from typing import Optional


def _format_divergence_for_prompt(divergence: dict) -> str:
    """将结构类型、级别与指标证据分层格式化，避免模型混淆。"""
    force = divergence.get("macd_force")
    force_cn = {
        "directional": "同向柱累计",
        "abs": "绝对值面积(震荡回退)",
    }.get(str(force), str(force) if force is not None else "未知")

    def _yn(val: object) -> str:
        if val is True:
            return "是"
        if val is False:
            return "否"
        return "未知"

    osc = (
        f"RSI{_yn(divergence.get('rsi_confirm'))} "
        f"KDJ{_yn(divergence.get('kdj_confirm'))}"
    )

    lines = [
        f"  缠论分类:{divergence.get('chan_type_label', '力度背离')} "
        f"方向:{divergence.get('type')} 标准结构:{_yn(divergence.get('strict_chan'))}",
        f"  级别:{divergence.get('level_label', '未知')} "
        f"证据等级:{divergence.get('evidence_grade', '未知')}"
        "（证据等级不是走势级别）",
        f"  规则匹配度:{divergence.get('match_score', divergence.get('probability'))} "
        "（不是未来涨跌成功率） "
        f"MACD力度比:{divergence.get('macd_ratio')} 力度算法:{force_cn}",
        f"  振荡器背离确认:{osc}",
        f"  结构依据:{divergence.get('theory_note', '')}",
        f"  转折含义:{divergence.get('turn_scope', '')}",
        f"  描述:{divergence.get('description', '')}",
    ]
    if "price_drop" in divergence:
        lines.append(f"  价格下探幅度(相对前低):{divergence['price_drop']}")
    if "price_rise" in divergence:
        lines.append(f"  价格冲高幅度(相对前高):{divergence['price_rise']}")
    return "\n".join(lines) + "\n"


SYSTEM_PROMPT = """你是专业的缠论技术分析助手，帮助用户分析股票走势并给出操作建议。

分析规则：
1. 只基于用户提供的 K线/缠论数据进行分析，不臆测
2. 严格区分趋势背驰、盘整背驰和指标力度背离；力度背离不得表述为已确认缠论背驰
3. “走势/结构级别”与“A/B/C证据等级”含义不同，不得混用
4. 多级别趋势与低级别背驰可以同时存在；逆大级别趋势的 C 级盘整背驰只能视为反弹/回调观察，不得直接给出买入或卖出
5. 只有 RSI/KDJ 追加确认、当前级别趋势转强/转弱，或出现对应三买/三卖后，才可升级逆势操作建议
6. 结合中枢位置、力度算法与 RSI/KDJ 追加证据综合判断
7. 输出结构化 JSON，不要输出多余文字

回复格式（严格 JSON）：
{
  "direction": "买入|卖出|观望",
  "confidence": 0.0-1.0,
  "risk_level": "低|中|高",
  "entry_price": 数字或null,
  "stop_loss": 数字或null,
  "take_profit": 数字或null,
  "holding_period": "描述",
  "reasoning": "简明分析理由（50字内）"
}
"""


def build_analysis_prompt(
    code: str,
    level: str,
    klines: list,
    trend: str,
    divergence: Optional[dict],
    signals: list,
    zhongshus: list,
    bis: list,
    resonance: Optional[dict] = None,
) -> str:
    """构造发送给 LLM 的分析 prompt"""

    # 截取最近 30 根 K 线
    recent = klines[-30:] if len(klines) > 30 else klines
    kl_text = "\n".join(
        f"{k['date']}  开:{k['open']} 高:{k['high']} 低:{k['low']} 收:{k['close']} 量:{k.get('volume',0)}"
        for k in recent
    )

    # 笔信息
    bi_text = ""
    if bis:
        for b in bis[-5:]:
            bi_text += f"  [{b['start']} ~ {b['end']}] {b['direction']}段 高:{b['high']} 低:{b['low']}\n"

    # 中枢
    zs_text = ""
    if zhongshus:
        for z in zhongshus[-3:]:
            zs_text += f"  [{z['start']} ~ {z['end']}] 中枢 高:{z['range_high']} 低:{z['range_low']}\n"

    # 背驰（力度算法、振荡器确认一并给出，便于模型综合判断）
    div_text = ""
    if divergence:
        div_text = _format_divergence_for_prompt(divergence)

    # 买卖点
    sig_text = ""
    if signals:
        for s in signals[-5:]:
            sig_text += f"  {s.get('datetime','')} {s.get('type','')} @ {s.get('price','')} ({s.get('description','')})\n"

    resonance_text = "无"
    if resonance:
        trends = resonance.get("trends") or []
        trend_parts = [f"{item.get('level')}:{item.get('trend')}" for item in trends]
        direction = resonance.get("direction") or "无明确共振"
        resonance_text = f"{', '.join(trend_parts) or resonance.get('description', '')}；共振方向:{direction}"

    prompt = f"""分析股票 {code}（{level}级别），当前趋势：{trend}

【最近30根K线】
{kl_text}

【最近笔】
{bi_text or '无'}

【最近中枢】
{zs_text or '无'}

【背驰信号】
{div_text or '无'}

【多级别趋势背景】
{resonance_text}

【最近买卖点】
{sig_text or '无'}

请根据以上缠论数据，输出结构化操作建议（仅返回JSON）："""

    return prompt


def parse_llm_response(text: str) -> Optional[dict]:
    m = re.search(r"```(?:json)?\s*({\n.*?})\s*```", text, re.DOTALL)
    if m:
        raw = m.group(1)
    else:
        # 找第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = text[start:end + 1]
        else:
            raw = text.strip()

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        # 解析结果不是对象：返回 None，由调用方回退规则引擎信号并标记 llm.error
        return None
    except json.JSONDecodeError:
        # 解析失败同样返回 None，避免把“观望/0.0”当作 LLM 成功结果覆盖规则信号
        return None
