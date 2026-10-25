# 核验、交付与未完成项

2026-10-24。执行起点15:24:48（北京时间），3小时上限18:24:48。最终保存时间及实际耗时见artifacts/small_capital_v1/delivery_manifest.json。本轮不为用满预算增加参数搜索。

## 已实际执行

- 151/151预登记实验完成；其中148个新ETF账户、3个旧v1r4缩小重跑。计算异常0项，不表示约束失败或未成交为零；这些记录在audit/events/actual_constraints中。初始ETF数据审计失败仍保留。
- 149项计算输入哈希、1516项结果文件校验、3204项原冻结文件未变；原量化Agent另核验108项指数增强实验通过。
- 全项目83项pytest测试通过，含整数单位、非负现金、现金流/TWR、股息应收、2022拆分、未来价格不影响此前决策、触限风险、首次未成交及清仓后状态、Agent指令/范围/联合情景拒绝。
- review.py独立从成交和拆分事件重建148个账户逐日份额；现金及财富等式逐日复核。single/fixed/risk/band近期四个基准实验重新计算，与冻结净值、持仓、成交、订单和现金表完全一致。
- review.ipynb从头执行6个代码单元，保留输出与HTML。两张独立PNG图已实际查看，文字及图例可读；未完成整个HTML逐屏视觉检查。
- 原生Tk工作台实际启动，默认“小资金组合”成本与客户价值页已查看，5方案与4费用档完整显示。用户按Esc停止Computer Use后未再操作窗口，其余标签未完成人工交互验证；不把代码检查写成已点击验证。
- 原Agent入口实际调用small_capital_plan，独立事件哈希链验证通过；输出明确未成交、无券商连接。

## 后置审计修订（不更改冻结计算）

1. 4个追加资金结果的原annual_two_way_turnover使用TWR评价净值作分母，不应当成实际财富归一化换手。原值保留，all_experiments.csv新增annual_two_way_turnover_actual_wealth，用真实平均净财富重新计算。无现金流结果不受影响；收益、现金流、份额和订单均不改。
2. 旧v1r4三段另做持仓质量核查：未解释公司行动持仓为空，但2017—2021长停牌持仓最大权重4.21%，期末为零。legacy_holding_quality.json保存完整结果；该区间流动性标记需要复核，不当作可立即清算财富。
3. Agent包装层拒绝未登记联合组合：非10万元叠加服务费/成本压力，或服务费叠加双倍交易成本，均返回needs_research。计算核心不变，没有新增收益实验。
4. 初次采集/保全脚本加入已存在即停止的防覆盖保护；再次采集必须另建版本，不能重置旧基准。

## 明确未完成与不能据此声称的事

- B直接持股方案只做交易单位/权限/预算可行性审计，未做新选股策略回测。无跨资产组合研究。
- 中证500历史逐日穿透未恢复；当前采用滞后指数权重代理，不能声称所有历史行业约束通过。两基金零名称重叠不代表共同因子低相关。
- 当前风险动作只在月末，不是每日强制约束；风险缓冲与实际18%超限已分开报告。真实限价、盘口队列、停牌与委托回报数据不足，现用披露的模型。
- single分阶段情景为事先约定前三批买入，不能把其阶段标记作为C方案的永久建仓状态。C的首次实际建仓状态有专门测试，清仓不重置。
- 没有提取资金情景，没有前向模拟成交；forward_state为not_started、0天。参考收盘试算不能直接作为下个交易日订单。
- 真实账户佣金、权限、可售份额、风险承受能力未知；无销售许可或数据商业使用许可认定。没有接触客户、收取费用或连接券商。
- UI其余标签与完整报告HTML的人工视觉/交互核验未完成；已保留原生入口供继续检查。
- 项目内误建的空目录quant_workbench/仍保留：自动审批拦截了清理操作，未重试，不影响任何结果。

## 继续执行顺序

1. 先运行runner verify与review.py，读取本文件及冻结协议，不改旧结果。
2. 完成剩余原生标签交互检查；只修派生视图，计算变化另版本。
3. 新研究版本先补每日风险动作优先级、真实账户费用/权限/可售状态、交易限价与公司行动契约；登记新的输入范围和联合情景。
4. 取得规则冻结后的新行情，建立独立模拟事件账本再开始前向；期间不按收益换参数，至少观察12个月并覆盖压力阶段。该期限是研究路线，不是成功保证。
5. 若考虑商业化，由拟合作持牌机构核验业务实质、机构与人员资质、适当性、宣传、留痕/投诉及数据商业授权，再研究用户是否愿为可验证便利付费。

## 文件地图

| 内容 | 项目内路径 |
|---|---|
| 原生入口 | QuantWorkbench.bat；src/quant_workbench/desktop.py |
| 独立实现 | src/quant_workbench/small_capital_v1/ |
| 冻结协议/配置 | research/small_capital_v1/protocol.md；config/small_capital_v1.json |
| 数据与版本 | data/small_capital_v1/receipts.json、current_500_receipt.json；artifacts/small_capital_v1/freeze.json |
| 全部实验/失败 | artifacts/small_capital_v1/runs/；data_audit_initial_failure.json |
| 研究报告及表格 | reports/small_capital_v1/report.md、all_experiments.csv、annual_results.csv、client_value_fees.csv |
| 完整10万元份额 | reports/small_capital_v1/example_holdings_100k.csv；artifacts/small_capital_v1/example_plan.json |
| 可执行复核 | reports/small_capital_v1/review.py、review.ipynb |
| 教材与合规 | research/small_capital_v1/theory.md、compliance.md、sources/receipts.json |
| Agent任务和提示词 | research/small_capital_v1/agent_guide.md；artifacts/small_capital_v1/example_task.json |
| 冻结/交付核验 | artifacts/small_capital_v1/verification.json、delivery_manifest.json、tests_full.log |

本交付为研究原型。软件、账本和完整性通过不能代替策略有效性、前向证据或客户付费价值。

交付封存后可另运行 `.\.venv\Scripts\python.exe scripts\small_capital_release.py verify` 核对源文件、派生报告与实验manifest。正常Agent事件日志可追加，未纳入静态交付哈希；其自身另有哈希链。
