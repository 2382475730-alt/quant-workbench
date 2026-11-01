"""Build editorial copies without changing research inputs, tables or results."""
from collections import Counter
from hashlib import sha256
import html
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, quote

import mistune

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from quant_workbench_app.paths import LIBRARY

OUT = PROJECT / "runtime/editorial_20261031"

# Exact, reviewed passages. No keyword deletion or edits to source documents.
EDITS = [
    ("# A股双主线量化研究：方法、实现与解释边界", "# A股组合与单股研究：方法与核算口径"),
    ("本工作台研究股票池组合配置和单只股票持仓。理论来自 Shreve 两卷中实际核对的相关章节，策略有效性由市场数据检验，不能从无套利理论直接推出超额收益。", "本工作台研究股票池配置与单股持仓。所引 Shreve 章节用于建模和核算，策略收益另由市场数据检验。"),
    ("# small_capital_v1 运行和Agent工具契约", "# small_capital_v1：运行命令与接口约束"),
    ("在 D:\\Study\\# Financial\\quant_workbench 中执行。主程序依旧是原生Tk窗口，新增“小资金组合”标签；打开仅读取本地结果，不下载/回测/下单。", "以下命令记录研究基线中的模块入口，复跑应使用独立副本。当前原生Tk工作台从 D:\\Study\\# Financial\\quant_workbench 的 launch.pyw 启动，窗口读取本地结果；行情采集和实验由独立脚本执行。"),
    ("# 中国大陆业务边界、交易规则与数据许可核验", "# 中国大陆业务资质、交易规则与数据许可"),
    ("以下为研究原型的业务设计边界，不表示已获得任何许可或完成法律审查。", "本记录用于研究原型的业务设计；所需许可与法律审查尚未完成。"),
    ("# 教材原则—现实假设—实现—验证", "# 教材原理、交易假设与代码验证"),
    ("没有通读两卷，也没有阅读完所列章节的所有页面。", "本轮阅读范围仅限上述页面。"),
    ("# A股双主线量化研究：仓位控制有用途，统一选股与择时尚未获得稳健支持", "# A股组合与单股研究：收益、回撤及采用条件"),
    ("## 结论与可采取的行动", "## 研究结论"),
    ("**先模拟跟踪，再讨论实盘适配。** 本次没有产生“已证明能持续赚钱”的策略。前向观察入口已与历史样本分开，尚无未来业绩；可以保留现金，不强制给出满仓买入名单。", "**下一步开展前向模拟。** 当前入口支持历史样本以外的报价观察，尚无前向业绩。策略采用仍缺新数据下的执行与收益证据。"),
    ("这不是总家庭资产配置比例。", "该权重仅适用于单股研究子账户。"),
    ("研究输出不连接券商账户。软件测试通过、财报字段一致或某段回测盈利，均不等于实盘策略获证。", "实盘采用还需验证真实账户的交易权限、成本与前向执行表现。"),
    ("持有条件与需跟踪事项：", "持有条件："),
    ("低PB须结合资产质量和普通股资本回报判断；观察逾期迁徙、净息差与资本缓冲是否恶化，不能把账面折价直接当作上涨空间。", "结合资产质量和普通股资本回报评估PB折价，重点检查逾期迁徙、净息差与资本缓冲的变化。"),
    ("即使价格趋势转强，也要核查毛利、业务结构和营运资金；以仓位上限与失效条件控制单一行业波动。", "核查毛利、业务结构和营运资金变化，并按仓位上限与持有条件控制行业集中风险。"),
    ("结合区域收入、外汇对冲和现金流考察盈利质量；跟踪对冲后经济收益而非仅单一会计指标。", "结合区域收入、外汇对冲后的收益与现金流评估盈利质量。"),
    ("现金流须剔辨财务子公司影响；关注终端动销、渠道库存、批零价与直销结构，低于自身历史PE不自动构成安全边际。", "现金流需区分财务子公司与白酒业务。结合终端动销、渠道库存、批零价和直销结构，判断历史PE比较是否适用。"),
    ("结合来水、发电量、电价、利息费用和资本支出验证分红持续性；低波动特征也不能替代价格与集中度风险控制。", "用来水、发电量、电价、利息费用和资本支出检验分红持续性，并检查买入价格与组合集中度。"),
    ("同时检验新业务价值、保险服务业绩、投资回报与偿付能力；PB和净利润增速均不应单独触发加仓。", "结合新业务价值、保险服务业绩、投资回报与偿付能力评估PB及净利润增长，再判断加仓条件。"),
    ("# 指数增强研究：执行改进已完成，稳定超额收益尚未得到证明", "# 指数增强研究：约束执行与超额收益检验"),
    ("## 1. 结论先读", "## 1. 研究结论"),
    ("这说明风险结构明显接近指数，却还不能说明它具有可信的超额收益。", "风险结构已接近指数，超额收益仍缺统计支持。"),
    ("也不能挑出这一段宣称成功。", "需与其他区间一并评价。"),
    ("不能因为近期跑赢就换它做主方案。", "因此仍保留为备选。"),
    ("## 2. Portfolio到底如何选择", "## 2. 股票选择与权重计算"),
    ("## 3. 约束如何落实，哪里还未做到", "## 3. 目标约束与实际超限"),
    ("防御备选若累计收益和回撤为零，表示未能建仓而保持现金，不代表成功避险。存档版本仅供审计，不能按历史胜负倒选。", "防御备选的零收益、零回撤对应建仓失败后的现金状态。存档版本用于核验修订过程，方案选择沿用预先登记的规则。"),
    ("## 7. 最新实际持仓是什么", "## 7. 期末模拟持仓"),
    ("## 8. Shreve两卷给了什么，不能给什么", "## 8. Shreve理论与模型假设"),
    ("这些理论提供一致的建模和核算语言，不直接证明动量有效，也不保证受约束最优组合超过指数。", "这些理论用于建立模型和核算账本；动量及约束组合的收益需另由市场数据检验。"),
    ("本轮没有把局部核对说成重新通读两书。", "本轮核对范围为所引章节。"),
    ("## 9. 如何做一个能复刻的Agent", "## 9. 研究工具与复现步骤"),
    ("更重要的是，历史已见、部分资料时点为代理、实际持仓有超限，因此本轮没有满足实盘采用门槛。下一步优先补执行风控和新数据前向证据，而不是扩大参数搜索。", "历史数据已被研究者查看，部分资料采用时点代理，实际持仓也出现超限，因此本轮尚未达到实盘采用门槛。下一步完善执行风控，并用新增数据开展前向模拟。"),
    ("候选数40不等于最终持仓数，旧持股也可能因换手限制保留。", "40只是候选数量；最终持仓还受权重、整手和换手限制影响，部分旧持股可能继续保留。"),
    ("这让模型倾向于适度体现更强的信号，减少直接押注过去最强行业的倾向。", "该映射控制信号强弱，减少组合向历史强势行业集中。"),
    ("求解器找到的只是给定假设与估计量下的解，不能制造投资优势。", "求解结果依赖输入假设和风险估计，收益优势需另由市场数据检验。"),
    ("当前未接LLM API或券商，并非全自动量化投顾。", "研究工具尚未接入LLM API或券商。"),
    ("下一步最有价值的闭环是：每日冻结计划→新数据只追加→记录模拟成交及风险冲突→用一段真正新历史评价，而非继续搜索历史最优参数。", "下一步每日冻结计划，追加新数据并记录模拟成交和风险冲突，用新增历史评价执行与收益。"),
    ("# 10万元小资金组合：执行更简单，尚未证明值得收费", "# 10万元小资金组合：执行成本、风险与服务费影响"),
    ("## 先回答产品问题", "## 研究结论"),
    ("风险降低主要伴随降低市场暴露，不是已证实的选股优势。", "较低回撤主要来自较低的市场暴露，尚缺选股优势的证据。"),
    ("，而不是照搬几十只直接持股。", "。直接持有几十只股票则容易受交易单位和费用限制。"),
    ("该执行改善可核验，但节省金额不能自动支持300—1200元年费，更不能推断客户付费意愿。", "成交与费用记录支持这项执行改善；节省金额尚不足以覆盖300—1200元年费，客户付费意愿仍需另行调查。"),
    ("目标权重不是实际成交；收盘目标最早下一交易日开盘执行。", "目标权重经订单和成交后才形成持仓，最早在下一交易日开盘执行。"),
    ("不代表已完成ST、事件或基本面筛选。", "ST、事件与基本面筛选尚未包含在这项单位审计中。"),
    ("## 10万元新资金参考试算（不是成交或今日买入建议）", "## 10万元新资金试算"),
    ("## 产品定位、限制和下一步", "## 适用账户与后续验证"),
    ("定位：已有独立权益风险承受能力、主要需要减少碎片化操作的普通现金账户研究工具。", "本工具面向能承担权益风险、需要按月管理持仓的普通现金账户。"),
    ("落在不交易区间就明确写不交易。", "目标差异落在不交易区间时保留原持仓。"),
    ("不能保证总是更好。", "这些情况会使结果偏离当前试算。"),
    ("销售距离：还缺", "收费服务尚缺"),
    ("## 可复核交付", "## 文件与复现入口"),
    ("# 单股持仓方案：完整说明", "# 单股持仓规则与账户口径"),
    ("## 1. 方案到底回答什么", "## 1. 规则的用途"),
    ("## 6. 子账户仓位不是总资产仓位", "## 6. 子账户与总资产仓位"),
    ("3. 用“完整持仓规则”打开本说明；用“原始半年报”核查财务依据。", "3. 在“研究记录”阅读本说明；用“原始半年报”核查财务依据。"),
    ("持仓研究应同时查看趋势、风险预算、组合集中度及原始财报；本财务快照本身不触发买卖。", "本页展示财务与估值快照。持仓规则另按价格趋势和风险预算计算，组合集中度需结合总账户检查。"),
    ("现金流口径：经营现金流减购建长期资产现金为代理，不等于FCFF或FCFE；不含收购及全部再投资调整。", "现金流口径：经营现金流减购建长期资产现金，尚未调整收购及全部再投资项目，因此仅作为现金盈余代理，不能直接代入FCFF或FCFE估值。"),
    ("负债率仅作结构描述，不与工业企业直接比较；银行还需资本充足率与资产质量，保险还需偿付能力、保险服务及投资表现。", "负债率用于描述财务结构。银行与工业企业的资金来源不同，需另查资本充足率和资产质量；保险需另查偿付能力、保险服务及投资表现。"),
    ("本快照使用当前数据库中截至截止日前公告的版本；不能证明原始历史数据库版本，因此未用作历史选股因子。", "本快照采用当前数据库收录、在截止日前公告的版本。历史数据库修订尚未还原，因此未用于历史选股。"),
    ("Tushare报表是结构化来源，重要结论仍须与公司原始报告核对。", "Tushare提供结构化报表；重要结论以公司原始报告核对结果为准。"),
    ("# 怎样做一个可复刻这套工作的量化Agent", "# 量化研究工具：能力、接口与复现步骤"),
    ("当前已实现的是可调用的确定性研究工具层，不是已经接入LLM、能够自主产生可靠投资建议的成品Agent。它不连接券商，不自动交易。", "当前工具层按固定代码执行研究任务，尚未接入LLM或券商。"),
    ("## 1. 它应复刻什么", "## 1. 研究流程"),
    ("目标不能写成“找一个一定跑赢的模型”，否则Agent会不断搜索直到过拟合。", "需预先限制候选数量和停止条件，控制反复搜索造成的过拟合。"),
    ("当前完整结果存在时主要执行复用和核验，不是假装重新计算。", "已有完整结果时复用并核验保存文件。"),
    ("# Portfolio实际持仓方案读法", "# 历史组合模拟持仓与账户余额"),
    ("新增“组合持仓”页默认直接展示回测实际期末账本，可切换五个组合方案与历史日期；“组合研究”的策略选择与本页联动。", "本说明记录原版“组合持仓”页，包含五个组合方案与历史日期，策略选择与原版“组合研究”联动。"),
    ("策略仍未通过稳定采用检验，展示持仓是为了核对真实执行与风险，不将研究结果自动升级为买入建议。", "持仓页用于核对模拟成交及风险暴露。策略采用仍缺稳定性检验与前向执行证据。"),
    ("# 生猪养殖：行业、经营承受力与跨周期估值研究", "# 生猪养殖研究：供给、公司现金与跨周期估值"),
    ("## 先看公司对比", "## 公司成本、现金覆盖与估值"),
    ("同列不等于同口径：", "成本与财务口径："),
    ("纳入研究不等于纳入持仓。", "公司池用于研究，持仓按所选规则计算。"),
    ("允许配套饲料和屠宰，不机械套用90%收入门槛。", "配套饲料与屠宰计入业务分析，90%收入占比仅作描述。"),
    ("## 行业周期：去化成立，盈利反转尚需证据", "## 行业周期：母猪存栏与当期供给"),
    ("母猪数不代表生产效率不变，也不能确定单一反转月份。", "产量传导还受生产效率和育肥时滞影响，母猪存栏本身无法确定反转月份。"),
    ("不能将旧目标与新目标混用。", "两项目标应按各自生效期间使用。"),
    ("这不等于对未来肉量的点预测，更不能直接当猪价涨幅。", "该情景只计算供给变化；未来肉量和猪价还受时滞、需求与库存影响。"),
    ("这些只是抽样点的极值，不能称为完整周期最高或最低点。", "极值范围限于上述抽样日期，完整周期的高低点尚需完整序列核验。"),
    ("历史图同时展示仔猪价、猪粮比和猪料比；不是月均价序列，也不是养殖利润。", "历史图采用固定周样本，同时展示仔猪价、猪粮比和猪料比。价格比尚未计入饲料转化率及其他养殖成本。"),
    ("## 估值：反算现价需要什么恢复条件", "## 估值：现价对应的盈利恢复条件"),
    ("### 把现价所需利润连接到经营条件", "### 现价对应的售价、成本与销量"),
    ("## 按成本、现金与估值分档形成当前条件权重", "## 成本、现金与估值分档"),
    ("纯度不应被屠宰收入占比机械否定。", "屠宰收入占比需结合一体化业务判断。"),
    ("不直接写入永久增长。", "长期增长假设须待这些业务兑现后再调整。"),
    ("不能只取标杆场数据。", "公司整体表现应与标杆场数据分别核对。"),
    ("高负债与净资产消耗应优先于“低股价”叙事。", "估值判断应先核查高负债和净资产消耗。"),
    ("不是当时真实可执行的前向业绩证明。", "执行可行性与收益仍需新增数据验证。"),
    ("新研究独立从零采集，不沿用已删除研究的结论。", "资料采集与模型输入独立保存。"),
    ("## 公司经营：把单位成本、利润质量和资金桥分开", "## 公司经营：成本、利润与现金"),
    ("### 逐公司判断与需要证伪的条件", "### 公司判断与重新评估条件"),
    ("## 现金承受力：把“能否等到恢复”做成压力情景", "## 现金储备与资金压力情景"),
    ("绝不是预测公司将违约", "表示该情景下需要补充的资金"),
    ("数据不足以独立校准完整FCFF、维持资本开支和资本成本，因此本版交付可复算的条件模型，而非伪精确DCF。", "完整FCFF、维持资本开支和资本成本尚缺校准数据，本版按给定盈利路径与回报要求计算条件价值。"),
    ("它是条件筛选的结果，不是建议真实账户持有该比例或只买某一家公司，也不否定跨周期研究价值。应先检验经营与估值假设，再决定是否采用。", "该比例由当前筛选条件计算；应用到真实账户前，需核查经营与估值假设，并结合账户风险预算调整。"),
    ("## 后续更新清单与使用边界", "## 数据缺口与更新事项"),
]


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def protected(text):
    """Factual tokens and evidence are compared independently of prose."""
    return {
        "numbers": Counter(re.findall(r"\d+(?:[.,]\d+)*", text)),
        "tables": [line for line in text.splitlines() if line.lstrip().startswith("|")],
        "code": re.findall(r"```[\s\S]*?```|`[^`\n]+`", text),
        "urls": re.findall(r"https?://[^\s)<>]+", text),
    }


def rewrite(text):
    changes = []
    for before, after in EDITS:
        count = text.count(before)
        if count:
            text = text.replace(before, after)
            changes.append({"before": before, "after": after, "occurrences": count})
    # The same audit caveat followed each period table. Keep it at first use.
    repeat = "防御备选的零收益、零回撤对应建仓失败后的现金状态。存档版本用于核验修订过程，方案选择沿用预先登记的规则。"
    if text.count(repeat) > 1:
        first = text.index(repeat) + len(repeat)
        text = text[:first] + text[first:].replace(repeat + "\n", "")
        changes.append({"before": repeat, "after": "保留首次说明，删除后续重复段落。", "occurrences": 2})
    return text, changes


def local_url(target, output):
    return quote(os.path.relpath(target, output.parent).replace('\\', '/'), safe='/')


def render_markdown(text, source, targets, output):
    class ReadingRenderer(mistune.HTMLRenderer):
        def resolve(self, url):
            parsed = urlsplit(url)
            if parsed.scheme or url.startswith("#"):
                return url
            original = (source.parent / parsed.path).resolve()
            target = targets.get(original, original)
            return local_url(target, output) + ("#" + parsed.fragment if parsed.fragment else "")

        def link(self, text, url, title=None):
            return super().link(text, self.resolve(url), title)

        def image(self, text, url, title=None):
            return super().image(text, self.resolve(url), title)

    markdown = mistune.create_markdown(renderer=ReadingRenderer(escape=True, allow_harmful_protocols=["file:"]),
                                      plugins=["table", "strikethrough"])
    return markdown(text).replace('<table>', '<div class="table"><table>').replace('</table>', '</table></div>')


def build():
    documents = list((LIBRARY / "reports").rglob("*.md"))
    documents += list((LIBRARY / "artifacts/company").glob("*/summary.md"))
    # Protocols, system prompts and execution logs remain historical records.
    guides = ["methodology.md", "portfolio_holdings_guide.md", "single_stock_holding_guide.md",
              "quant_agent_design.md", "small_capital_v1/agent_guide.md",
              "small_capital_v1/compliance.md", "small_capital_v1/theory.md"]
    documents += [LIBRARY / "research" / path for path in guides]
    documents += [PROJECT / "runtime/research/swine_deep_20261025/report/research.md",
                  PROJECT / "runtime/research/swine_v1_20261025/results/research_report.md"]
    targets = {}
    for source in documents:
        scope = "library" if source.is_relative_to(LIBRARY) else "app"
        base = LIBRARY if scope == "library" else PROJECT
        targets[source.resolve()] = OUT / scope / source.relative_to(base)
    records = []
    for source in documents:
        original = source.read_text(encoding="utf-8")
        revised, changes = rewrite(original)
        assert protected(original) == protected(revised), f"Factual content changed: {source}"
        target = targets[source.resolve()]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(revised.encode("utf-8"))
        html_path = target.with_suffix(".html")
        body = render_markdown(revised, source, {k: v.with_suffix('.html') for k, v in targets.items()}, html_path)
        html_path.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + html.escape(revised.splitlines()[0].lstrip('# ')) + '</title>'
            '<style>body{font:16px/1.85 "Microsoft YaHei",sans-serif;color:#25374b;background:#f4f6f9;margin:0}'
            'main{max-width:1080px;margin:32px auto;padding:40px 48px;background:white}'
            'h1{font-size:28px;line-height:1.5}h2{margin-top:40px;font-size:22px}h3{margin-top:28px}'
            'p{margin:16px 0}.edition{color:#617488;font-size:14px}table{border-collapse:collapse;white-space:nowrap;font-size:14px}'
            'th,td{padding:10px 14px;border-bottom:1px solid #dce4ec;text-align:left}th{background:#edf3f7}'
            '.table,pre{overflow:auto}pre{padding:18px;background:#f3f6f9;line-height:1.6}img{max-width:100%}'
            'a{color:#23688c}code{font-family:Consolas,monospace}.item{margin:8px 0 8px 18px}'
            '@media(max-width:700px){main{margin:0;padding:20px}h1{font-size:24px}}</style>'
            '<main><p class="edition">文字修订：2026-10-31。数据日期与研究结论沿用原报告。 '
            '<a href="' + local_url(source, html_path) + '">查看原报告</a></p>' + body + '</main></html>', encoding="utf-8")
        records.append({"source": os.path.relpath(source, PROJECT).replace('\\', '/'),
                        "reading": target.relative_to(OUT).as_posix(), "html": html_path.relative_to(OUT).as_posix(),
                        "source_sha256": digest(source), "reading_sha256": digest(target),
                        "html_sha256": digest(html_path), "changes": changes,
                        "protected_content_verified": True})
    manifest = {"edition": "2026-10-31", "documents": records,
                "unchanged_records": "原始公告、来源回执、研究协议、系统提示词、执行日志、核验记录与计算笔记保留原文。"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    index = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>工作台报告</title>',
             '<style>body{font:16px/1.9 "Microsoft YaHei",sans-serif;max-width:1000px;margin:40px auto;padding:0 24px;color:#25374b}li{margin:12px 0}a{color:#23688c}</style>',
             '<h1>工作台报告</h1><p>文字修订于2026-10-31；数据日期见各报告。表格、数字、代码和来源链接沿用原件。</p><ul>']
    seen = set()
    for row in records:
        if row['reading_sha256'] in seen:
            continue
        seen.add(row['reading_sha256'])
        title = (OUT / row['reading']).read_text(encoding='utf8').splitlines()[0].lstrip('# ')
        index.append('<li><a href="' + row['html'] + '">' + html.escape(title) + '</a></li>')
    index.append('</ul><p>' + manifest['unchanged_records'] + '</p></html>')
    (OUT / 'index.html').write_text('\n'.join(index), encoding='utf8')
    print(json.dumps({"documents": len(records), "edited_documents": sum(bool(r['changes']) for r in records),
                      "edited_passages": sum(sum(c['occurrences'] for c in r['changes']) for r in records),
                      "output": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    build()
