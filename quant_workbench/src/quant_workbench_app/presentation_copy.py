"""Reviewed display edits for inherited panels; source evidence stays verbatim."""
from tkinter import ttk
from .ui_presentation import NoteLabel


EDITS = {
    "持仓与约束方案": "持仓方案",
    "Agent如何复刻": "研究工具说明",
    "Agent复核说明": "运行与核验说明",
    "全部为已见历史回溯，尚无前向证据；实际约束仍可能超限。":
        "历史回测；实际持仓的超限记录见“约束与压力检验”。前向模拟尚未开始。",
    "实际持仓来自模拟成交账本；最近目标不是立即交易指令。现金与应收单列；非券商账户。":
        "持仓取自模拟成交账本，现金与应收单列。最近目标按原调仓日计算。",
    "旧方案与失败版本全部保留。当前应作为研究/模拟工具，不能据此宣布可靠跑赢或直接实盘。":
        "旧方案与失败记录已保留。实盘采用仍缺前向执行及稳定超额收益证据。",
    "Agent工具层可执行状态、完整性核验、固定实验、报告；尚未连接大模型或券商。":
        "研究工具支持查询状态、核验文件、运行固定实验及生成报告，尚未接入大模型或券商。",
    "少交易可以验证，收费优势尚未证明。": "不交易区间减少了成交笔数，服务费能否由收益覆盖仍缺证据。",
    "今天参考收盘试算不能冒称今天买入建议。": "执行前须按账户余额、交易权限和最新价格重算。",
    "此表不能改名为当前新资金买入计划；旧v1r4的特殊权限及股息税前口径保留。":
        "新资金试算另见“10万元新资金试算”。旧v1r4沿用特殊权限与股息税前口径。",
    "参考价格下整数方案可行；不等于已成交": "参考价格下的整数份额试算；尚未成交",
    "不是新资金买入建议": "新资金需另按当前账户试算",
    "不代表稳定跑赢或未来盈利概率": "稳定超额收益和未来盈利概率尚未得到验证",
    "完整解释见上方按钮。": "完整规则见“研究记录”。",
    "；这不是家庭总资产建议仓位。": "；应用到总资产时需乘以该子账户占总资产的比例。",
    "分位不等于低估。": "分位描述历史相对位置，价值判断还需盈利与资产质量。",
    "执行前必须核对实际账户佣金、可售份额、资金和下一交易日价格。执行前须按账户余额、交易权限和最新价格重算。":
        "执行前核对账户佣金、可售份额、资金、交易权限及下一交易日价格，再重算订单。",
    "历史500穿透缺失，未宣称全历史行业约束通过。": "中证500历史穿透缺失，历史行业约束尚无法完整核验。",
    "前向账户：尚未启动。参考份额不是历史账户期末持仓，也不是未来模拟成交。":
        "前向模拟尚未启动。参考份额按新资金与参考价格计算，历史期末持仓见“历史模拟持仓”。",
}


def plain_copy(text):
    for before, after in EDITS.items():
        text = text.replace(before, after)
    return text


def polish_panel(panel, text_fields=()):
    """Only fixed labels/buttons and explicitly selected readonly text fields."""
    def visit(widget):
        if isinstance(widget, NoteLabel) or (isinstance(widget, (ttk.Label, ttk.Button)) and not str(widget.cget("textvariable"))):
            old = str(widget.cget("text"))
            new = plain_copy(old)
            if old != new:
                widget.configure(text=new)
        for child in widget.winfo_children():
            visit(child)
    visit(panel)
    for name in text_fields:
        widget = getattr(panel, name, None)
        if widget is not None and str(widget.cget("state")) == "disabled":
            old = widget.get("1.0", "end-1c")
            new = plain_copy(old)
            if old != new:
                widget.configure(state="normal")
                widget.delete("1.0", "end")
                widget.insert("1.0", new)
                widget.configure(state="disabled")
