# A股量化研究工作台

独立的原生桌面程序，包含 Portfolio 组合配置与单股持仓研究两条主线。全部新产物位于本文件夹，上级原工作台保持独立。数据截止2026-10-23。

## 先打开什么

**2026-10-24新增：小资金组合 small_capital_v1。** 默认打开独立“小资金组合”页，原指数增强和组合页面仍可选择。先读 `reports/small_capital_v1/report.md`；已执行复核笔记为 `reports/small_capital_v1/review.ipynb`，纯脚本复核为同目录 `review.py`。151项预登记实验、10万元整数份额试算、收费后客户价值与全部失败边界均独立保存。结论是订单减少可验证，尚未发现值得收费的稳定策略优势；前向观察0天，当前仅研究原型。协议、教材对应、官方合规来源和Agent说明在 `research/small_capital_v1/`。以下指数增强叙述是原项目存档，不能替代新模块的费用和资金口径。

1. 双击 `QuantWorkbench.bat`：打开原生窗口，默认进入“小资金组合”页；“指数增强”页继续提供原公平比较、实际持仓、行业偏离及约束压力检验。旧组合与单股页面全部保留。
2. 新增 `reports/enhancement_v1/report.html` / `report.md`：沪深300全收益对照、四个工程版本共108项完整实验、失败与约束说明。`enhancement_review.ipynb`为已执行复核笔记。
3. 原报告 `reports/量化研究报告.html` / `量化研究报告.md` 和 `research_review.ipynb` 保留，`all_registered_results.csv` 保存183项旧区间结果。

当前结论：组合主模型没有获得稳定采用证据；单股波动控制在部分案例降低回撤，但存在失败案例和机会成本。软件测试通过不代表策略有效。

指数增强v1r4主方案近期累计9.25%，全收益指数9.51%；最大回撤16.18%，原20股35.54%。风险结构改善，但不能宣布可靠跑赢；实际行业/单股/ETF底仓仍有超限，全部历史均已见。前三版防御备选早期无法建仓的零收益是失败结果；v1r4修复首次实际建仓前的重试状态，保留首次失败，不能把旧版零收益叫有效避险。

## 量化Agent工具层

`research/quant_agent_design.md`提供完整架构。已有确定性本地runner，尚未连接LLM或券商：

```powershell
.\.venv\Scripts\python.exe -m quant_workbench.quant_agent status
.\.venv\Scripts\python.exe -m quant_workbench.quant_agent verify
.\.venv\Scripts\python.exe -m quant_workbench.quant_agent run --minutes 240
.\.venv\Scripts\python.exe -m quant_workbench.quant_agent report
```

已完成实验复用并核验，不覆盖净值；report重建图表/对照，完整叙述与伴随笔记由`scripts/write_enhancement_report.py`从本轮冻结证据生成。四版计算代码、参数与输入已封存，修改研究规则必须另建版本。冻结规则见`research/enhancement_v1_protocol.md`、`enhancement_v1r2_protocol.md`、`enhancement_v1r3_protocol.md`、`enhancement_v1r4_protocol.md`。

## 窗口内容

- **指数增强**：12行全收益/ETF/旧方案/工程存档比较、最新实际股数与现金、ETF行业穿透代理、逐日实际超限统计及费用/时延压力；完整报告和Agent说明可直接打开。

- **组合研究**：五个登记版本、年化收益/回撤/实际仓位、净值与回撤图、成本和相对基准区间。
- **组合持仓**：所选策略及日期的回测账户实际股数、市值、权重、现金和应收权益；并列最近目标，保留未买入目标及目标外残留持仓，支持成交/执行事件查看和完整流水导出。
- **单股研究**：六家公司分别对照持有/趋势/风险仓位，提供财务、估值分位、原始半年报入口及持有条件。
- **新资金与风险**：最近计划内组合目标、100万元新资金整手配置试算、20/60/120交易日风险情景；该试算不同于历史账户实际期末持仓。
- **数据与核验**：未解决问题、停牌解释、换股处理与历史时点边界。
- **方法与边界**：Shreve I/II思想与实际代码、费用、交易和验证口径的对应关系。

窗口只读取本地结果，打开不会自动下载、回测或下单。若无窗口，可在此目录运行 `.\.venv\Scripts\python.exe -m quant_workbench.desktop` 查看错误信息。

完整使用说明见 `research/portfolio_holdings_guide.md` 和 `research/single_stock_holding_guide.md`。单股页的“完整持仓规则”按钮可直接打开后者；最新计算目标、已记录目标和实际持仓分别展示。

## 结果与冻结规则

2015—2016预热，2017—2021开发，2022—2024验证，2025年至截止日最终区间。每阶段61项预登记实验。

第一次最终区间打开后发现两项已完成换股漏记，随后在原策略和参数不变的情况下核算修订。原结果保存在 `artifacts/research/final`，原输入在 `artifacts/research_initial_frozen`，修订说明在 `artifacts/research/repair_plan.json` 与 `repair_comparison.json`。正式阅读使用 `final_repaired`；它不是新的未接触检验，禁止据此继续调参并冒称样本外。

现有最终结果不可静默覆盖。未来新增数据和研究应使用新的版本目录和预登记协议，不修改已冻结的面板、规则及最终输出。

## 安全复核命令

在本目录 PowerShell 执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests scripts
.\.venv\Scripts\python.exe scripts\verify_delivery.py
```

执行研究笔记只读取已保存结果：

```powershell
.\.venv\Scripts\python.exe -m jupyter nbconvert --execute --to notebook --inplace reports\research_review.ipynb
```

完整开发/验证计算命令为 `python -m quant_workbench.research development` 与 `validation`，重跑会先归档此前结果；日常查看不需要重跑。`final`、`final_repaired` 均已封存，重复执行会拒绝。复现首次最终结果时使用保留的冻结输入建立另一个隔离目录，不能覆盖本次研究。

环境由 `pyproject.toml` 和 `uv.lock` 固定；迁移到其他机器可用 `uv sync --extra dev --extra notebook` 重建。依赖中不包含数据访问权限，查看已有结果不需要凭据。

## 前向观察入口

当前是**冻结试算持仓的观察账本**，尚不自动再平衡，也不等于完整模拟交易系统。初始日2026-10-23，100万元新现金账户按收盘参考价试算，与历史回测的期末持仓不同。还没有未来观察记录。

`artifacts/paper/quote_template.csv` 包含16只实际试算持有股票；四只目标股因最小交易单位为零。准备未来真实交易日的CSV，保持 `date,code,close,adj_factor` 四列，每只持仓恰好一行。同一文件只能包含一个日期；停牌、缺报价、因子变化或公司行动未核对时不能直接沿用旧价格填入。

核对所有持仓的公司行动与报价有效性后，执行：

```powershell
.\.venv\Scripts\python.exe -m quant_workbench.paper observe --quotes "完整路径\quotes_YYYY-MM-DD.csv" --events-reviewed
```

新记录仅追加到 `artifacts/paper/observations`，保存输入文件和哈希；禁止回填旧日期、覆盖已有观察、缺失持仓或改变复权因子。因子未变也不能证明没有待处理事件，因此需要真实事件核对。失败时保留原账本，先修复数据或另建经核验的公司行动处理，再继续。该入口不连接券商、不自动买卖。

## 资料位置与边界

| 目录 | 内容 |
|---|---|
| `data/raw`、`data/queries` | 原始响应、查询参数、哈希及缓存 |
| `data/normalized`、`data/panels` | 标准化表及冻结计算输入 |
| `data/source_documents` | 已实际获取的公司公告、财报原文及来源回执 |
| `artifacts/research` | 分阶段日净值、持仓、成交、公司行动及审计 |
| `artifacts/company` | 六家公司快照、财报核对、估值敏感性 |
| `artifacts/outlook` | 当前试算及条件风险模拟 |
| `reports` | 报告、笔记、全部登记结果与输入来源 |
| `report_app` | 附属交互报告源文件；主工作台仍为原生窗口 |
| `research` | 原协议、方法说明及执行记录 |

行情通过Tushare取得，原始财报及公司行动公告另行核验。凭据优先取环境变量或本目录 `.env`，兼容只读读取上级 `.env`；不写入报告或日志。

重要限制包括历史成分公告时点代理、财务修订版本不完整、六股案例选样、股息税前、日线执行假设、配股默认不认购、并购尾数向下取整、少量待换股/退市权益陈旧估值，以及未做全部尝试多重检验校正。完整研究路线与采用门槛见报告第8节。
