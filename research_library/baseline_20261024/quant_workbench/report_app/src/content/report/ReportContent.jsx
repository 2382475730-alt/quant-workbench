import React from "react";
import { EvidenceChart, DataComponent, DataTable, ReportSection, RichNarrative, useDataApp } from "../../data-app-public.jsx";
import cases from "./company-cases.json";

export function ReportContent() {
  const { reviewedRows, visible, appTitle, canEdit, mode, setAppTitle } = useDataApp();
  const rows = Object.fromEntries(["portfolio","stocks","nav","risk","company","audit"].map(q=>[q,reviewedRows(q)]));
  const narrative=(id,title,queryId,value,extra={})=>visible(id)&&<ReportSection id={id} title={title} queryId={queryId} sourceRows={rows[queryId]} showHeading={false} {...extra}>
    <RichNarrative id={id+":body"} value={value}/></ReportSection>;
  return <article className="report-content" aria-label="A股双主线量化研究报告">
    <header className="report-hero">
      <h1 data-data-app-title contentEditable={canEdit&&mode==="edit"} suppressContentEditableWarning onBlur={canEdit&&mode==="edit"?e=>setAppTitle(e.currentTarget.textContent.trim()||appTitle):undefined}>{appTitle}</h1>
      <RichNarrative id="report-introduction" className="report-deck" value="Portfolio 组合配置与单股持仓研究 · 观察截止 2026-10-23"/>
    </header>
    {narrative("executive-summary","主要结论","portfolio", "## 主要结论\n\n- **组合动量暂不直接采用。** 最终区间累计收益5.05%、最大回撤35.54%；同池等权分别为5.77%和7.63%。验证区间也未呈现稳定优势。\n- **单股波动控制值得继续观察。** 六个案例中五个的最大回撤低于买入持有，但平安银行是反例；降低风险不保证提高收益。\n- **当前产出是可检查的研究基础。** 原生工作台、183项区间结果、六公司财报核对及风险情景已就绪；尚无真正未来业绩。",
      {queryIds:["portfolio","stocks"],sourceRowsByQuery:{portfolio:rows.portfolio,stocks:rows.stocks}})}
    {narrative("portfolio-reading","组合主线","portfolio","## 组合主线：高仓位并没有换来稳定优势\n\n252日至21日前的动量排名选20股，月度等权调整。主模型最终平均股票暴露83.2%，等权基准53.0%；收益差不能直接解释为选股能力。100万元本金、整手约束和交易成本造成显著现金余额。\n\n最终区间经过查看结果后的换股核算修订，策略参数不变。原始版本保留；这不是第二次未接触的检验。")}
    <EvidenceChart id="portfolio-nav" queryId="nav" title="主模型经历更大的净值波动"
      spec={{type:"line",x:"date",y:"等权基准",fields:["等权基准","12个月动量20股"],stackable:false,yLabel:"净值（初始=1）",valueDecimals:3,startAtZero:false}}
      rows={rows.nav} sourceRows={rows.nav} height={340} description="2025-01-01至2026-10-23；扣模拟交易费，股息税前。"/>
    <EvidenceChart id="portfolio-results" queryId="portfolio" title="五项预登记组合版本的年化收益"
      spec={{type:"horizontalBar",x:"strategy",y:"cagr",stackable:false,xLabel:"年化收益（%）",valueDecimals:2}}
      rows={rows.portfolio.map(r=>({...r,strategy:r.strategy.replace("个月动量","月·")}))} sourceRows={rows.portfolio} height={320} description="各方案风险不同；保留亏损版本，不按最终成绩选参数。"/>
    {narrative("stock-reading","单股主线","stocks","## 单股主线：回撤改善需要付出机会成本\n\n每只股票分别比较买入持有、200日趋势、趋势加波动控制。下面展示最大回撤；中兴的风险控制效果明显，平安银行却出现反例。美的与长江电力的退出信号也错过了部分上涨。\n\n每个案例是独立的100万元研究子账户，仓位不能直接作为家庭全部资产的股票配置比例。六个当下选定案例也不能证明全市场有效。")}
    <EvidenceChart id="stock-results" queryId="stocks" title="同一持仓规则在不同股票上表现不同"
      spec={{type:"bar",x:"stock",y:"drawdown",series:"strategy",stackable:false,yLabel:"最大回撤（%）",valueDecimals:2}}
      rows={rows.stocks} sourceRows={rows.stocks} height={370} description="2025年至观察日；负值越靠近零，样本内最大回撤越小。年化收益在源数据及完整报告中保留。"/>
    <DataComponent id="company-evidence" title="六家公司的持有条件需要分别跟踪" kind="table" queryId="company" sourceRows={rows.company} displayRows={rows.company}>
      <DataTable rows={rows.company} columns={[{key:"stock",label:"公司"},{key:"revenue",label:"半年收入（亿元）"},{key:"profit",label:"归母利润（亿元）"}]} searchable={false} caption="2026半年报主要字段"/>
    </DataComponent>
    <ReportSection id="company-reading" title="财报中的关键区别" queryId="company" sourceRows={rows.company} showHeading={false}>
      <RichNarrative id="company-reading:body" value={cases.text} sourcePreviews={cases.previews}/>
    </ReportSection>
    {narrative("risk-reading","风险情景","risk","## 对历史漂移的处理，会显著改变风险判断\n\n当前20股目标按10月23日价格试算，整手配置后约28.5万元留在现金。下图使用实际试算权重和现金，比较未来60交易日的条件情景。739个共同有效观测日、20日联合分块、10000条路径。\n\n移除样本平均收益后，5%分位从−12.4%变为−20.2%；指定股票同步跳跌20%时为−24.2%。这些数值依赖模型，不是经校准的未来概率。")}
    <EvidenceChart id="risk-scenarios" queryId="risk" title="同一持仓的三种条件情景"
      spec={{type:"horizontalBar",x:"model",y:"p05",fields:["p05","median"],stackable:false,xLabel:"总资产收益（%）",valueDecimals:1,legend:{labels:{p05:"5%分位",median:"中位数"}}}}
      rows={rows.risk.map(r=>({...r,model:r.model.replace("指定股票跳跌20%","跳跌20%")}))} sourceRows={rows.risk} height={310} description="固定初始股数和现金；未模拟未来再平衡与新增公司行动。"/>
    {narrative("audit-reading","证据与核算边界","audit","## 证据边界决定结果能用到哪里\n\n数据覆盖历史月度沪深300成分并集667股。仍有5项高等级未解决源数据问题，但逐一核对后未跨越本次策略的实际持仓或可排名候选信号窗口；不能据此宣称全部数据正确。\n\n首次最终结果漏记海通证券和中国重工换股，修订后仅等权基准净值改变，期末资产减少255.42元，其余60条净值完全相同。信达证券200股仍处待换股阶段，旧报价代理估值3112元，不可视为可成交现金。\n\n月度成分是历史时点代理；当前财报缺少完整历史修订版本，未作为严格历史价值因子回测。收益扣交易费用、股息税前；比较区间未做全部研究尝试的多重检验校正。")}
    <RichNarrative id="methods-reading" value={"## Shreve理论如何落到工作台\n\nI卷的财富过程与信息适应性对应现金、股票、分红权益账本和次日成交；II卷的Itô公式用于带−σ²/2修正的GBM并检验解析矩。P与Q的区分保证风险中性定价不会被包装成现实上涨概率。跳跃过程用于组织压力情景，不伪造跳跃发生概率。\n\n## 下一阶段的研究路线\n\n1. 补齐历史公告时刻、财务修订版本、退市及并购权益；再扩大股票池和因子。\n2. 组合线研究价值、质量、盈利修正、低波及约束风险配置；单股线深化产业驱动、估值条件和持有逻辑失效条件。\n3. 预登记新的滚动检验，处理多重选择、整手和真实执行成本；不重复用已看过的最终区间挑赢家。\n4. 先积累前向模拟证据。当前入口只支持冻结试算持仓的报价观察；新增公司行动须复核，尚不自动再平衡。\n\n完整报告、可执行笔记和全部183项结果保存在quant_workbench/reports；主工作台继续使用独立原生窗口。"}/>
  </article>;
}

