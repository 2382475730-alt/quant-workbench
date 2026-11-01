# 猪逻辑公园

双击工作区根目录的 `LaunchWorkbench.bat` 启动。工作台包含生猪养殖研究、单股研究、指数增强和小资金配置，打开时读取本地数据快照。行情日期、财报期间和模型假设在各页列示。

## 页面与报告

- 生猪养殖研究：总览展示产能、调控状态、价格及六家公司；行业周期、公司经营和估值页提供明细，其后是建仓实验、资金适配和讨论记录。
- 单股研究：比较六家公司的持仓规则、财务与估值，以及历史模拟账户。财务快照的观察日固定，不随回测区间切换。
- 指数增强：比较组合收益、跟踪误差、模拟持仓和约束超限。区间选择和历史版本对照独立保存。
- 小资金配置：比较ETF方案的收益、回撤与费用，分别展示10万元新资金试算和历史模拟持仓。

侧栏“研究报告”打开报告目录；各模块的“研究记录”和报告按钮打开对应正文。文字修订版位于 `runtime/editorial_20261031/`，同时提供Markdown和HTML。表格、数字、代码与来源链接沿用原件，修改记录及原文哈希见 `manifest.json`。若原报告或阅读版内容变化，界面回退到原报告。重新生成阅读版：

```powershell
.\.venv\Scripts\python.exe scripts\build_plain_reports.py
```

原始公告、研究协议、系统提示词、计算笔记与核验记录保留原文。历史报告的数据日期沿用原件；文字修订日期不代表数据已更新。报告中的旧版命令应在独立研究副本中使用。

## 生猪数据与模型

总览观察日为2026-10-29。能繁母猪主图按方案公开日期切换调控区间，状态由公开规则计算；全国生猪存栏是期末数，出栏和猪肉产量是累计数。价格图采用集贸市场固定周样本。PSY来自正式年报引述的行业样本，全国官方均值尚缺。

公司表保留成本的“≤”“＜”及未核实状态，列示可动用现金、资产负债率和PB。可动用现金按合并货币资金扣除已披露受限资金及不重叠的专用资金计算，统一核实至2026-06-30；负债率使用各公司最近已披露报告，PB沿用10月23日快照。每项注明期间与原件。总览资料在 `runtime/research/swine_overview_20261029/`，导出在 `runtime/exports/swine_overview/`。

行业与策略研究观察日为2026-10-25，行情截至2026-10-23。该版本的现金压力模型保留原输入；天邦专用偿债资金在后续总览中另作扣减，两版现金口径应按明细区分。

公司池按核心业务判断，包含6家核心公司、3家观察公司，其余候选列明排除原因。5家公司等权篮子用于对照，当前公司池的历史回放存在选股回看偏差。

- 行业周期：展示官方产能、出栏和价格资料。2022年1月至2026年10月共58个月固定周样本，与公司月报售价分开。
- 公司经营：核对成本、利润、减值与资金压力；6家公司92项金额已定位原文。成本期间及财报期间分别列示。
- 估值：提供PB历史、净资产折损、盈利恢复与经营反推情景。倍数和盈利路径是研究输入，条件价值随输入变化。
- 建仓实验：从2026-06-01逐交易日起算，比较共同终点及20/60交易日，共1,080个情景。起点高度重叠，不能作为独立胜率样本。
- 资金适配：按成本、现金和估值条件释放候选额度，再根据本金、100股单位、费用、滑点与容量计算股数。未释放或买不起的部分保留现金。

分档规则在 `config/swine_allocation.json`，保留12组估值敏感性。跨周期规则在 `config/swine_cycle_policy.json`：每20个交易日重评产能、财报和PB条件，决定新增、冻结、兑现或退出。冻结新增时保留原股数；历史财报货币资金采用未扣受限的上界代理。当前分档不回填历史信号。

费用和分红扣留为研究假设。生猪回放分红按20%保守扣留，期末持仓按收盘价估值，结果未扣期末清仓费用。策略采用仍需前向执行及收益证据。

## 文件位置

当前源码在 `src/quant_workbench_app/`，模块配置在 `config/workbench.json`。页面状态、讨论、导出和检查结果写入 `runtime/`。

生猪基础研究在 `runtime/research/swine_v1_20261025/`，深入研究在 `runtime/research/swine_deep_20261025/`。报告分别为 `results/research_report.md` 与 `report/research.md`。账本和资金计划导出到 `runtime/exports/swine/`、`runtime/exports/swine_capital/`。

其他三个模块依赖 `../research_library/baseline_20261024/quant_workbench/` 的研究基线，默认只读。新研究应建立独立版本，保留原计算、输入和结果。环境与凭据沿用原位置。

旧生猪研究的授权删除记录在 `runtime/cleanup/deletion_manifest.json`；暂留缓存记录在 `runtime/cleanup/blocked_cache_cleanup.json`。具体维护规则见本目录 `AGENTS.md`。

## 运行与检查

在本目录 PowerShell 执行：

```powershell
.\.venv\Scripts\python.exe launch.pyw
.\.venv\Scripts\python.exe scripts\test_background.py
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\python.exe scripts\reconcile_swine.py
.\.venv\Scripts\python.exe scripts\audit_swine.py
.\.venv\Scripts\python.exe scripts\audit_swine_deep.py
.\.venv\Scripts\python.exe scripts\capture_background.py
```

界面检查在独立Windows后台桌面的子进程中执行，通过PrintWindow捕获该进程窗口。截图保存在 `runtime/verification_artifacts/background/`，需检查实际显示并修复后复验。核验结果说明文件与程序状态；数据口径和研究局限见各报告。

## 研究复现

总览原文采集与复算：`scripts/collect_overview_official.py` → `scripts/build_overview_official.py`。采集截止日固定为10月29日，更新需建立新版本。

基础研究：`collect_swine.py` → `collect_swine_documents.py` → `collect_swine_history.py` → `build_swine_research.py` → `reconcile_swine.py` → `run_swine_research.py` → `audit_swine.py`。采集器复用该版本缓存；完成深入研究打包后，运行 `write_swine_report.py` 同步原报告入口，再生成文字阅读版。

深入研究：运行 `scripts/collect_swine_deep.py`、`scripts/collect_swine_financial_originals.py`、`scripts/collect_swine_answers.py`、`scripts/collect_swine_price_history.py` 后，以 `scripts/build_swine_deep.py` 建模，`scripts/stress_swine_policy.py` 计算敏感性，`scripts/package_swine_deep.py` 打包。研究目录中的 `python model/run.py` 复算资金、供给、恢复、经营反推和分档模型；`python model/run_policy.py` 复算1,080个情景及686个门槛敏感性情景。
