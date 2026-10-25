# 量化研究工作台

从根目录 `LaunchWorkbench.bat` 启动原生 Tk 工作台。四个入口平级：生猪养殖研究、单股研究、指数增强、小资金配置。

## 生猪养殖研究

本轮从零采集数据，首页先展示关键图表与六家公司对比，行业周期、公司经营与估值可逐层展开，其后是建仓实验、资金适配、证据与讨论。研究观察日2026-10-25，行情截止2026-10-23。财务页逐公司列示报告期及公告日，月报与定期报告分开。

公司池按核心业务判断，不机械要求90%养殖收入。牧原纳入，配套饲料与屠宰允许；非核心业务说明。核心6家不等于推荐持仓，5家公司等权篮子仅用于比较，当前选股回放存在回看偏差。

用户愿意跨周期持有，重点看盈利恢复与估值。研究检查应围绕单位成本、产能传导、现金流、净资产及估值所隐含的盈利展开。短期跌价不是自动退出信号。趋势减仓保留为对照；跨周期草案按公告可得的产能、资金与估值规则分批、冻结新增、兑现或退出，并保存逐次决策依据。它仍是事后规则的情景回放。

- 行业周期：官方产能、出栏、价格证据，标明日期；2022年1月至2026年10月58个月固定周采样展示生猪、仔猪及饲料周期，明确不是月均价。公司月报售价另列，不与全国市场口径强行拼接。
- 公司经营：22家候选的纳入、观察、排除理由；深入研究将原文金额核对扩展到6家92项，检查科目上下文和负号；分开看成本、利润减值和资金压力。对账不是审计意见。
- 估值：PB历史、净资产折损敏感性及市值隐含正常化盈利。倍数是研究假设，未建立完整DCF，不将敏感性称为目标价。
- 建仓实验：2026-06-01起逐交易日起算，共同终点及20/60交易日分别比较，共1,080个情景。重叠起点不是独立胜率样本。
- 资金适配：默认承接当前成本、现金及估值分档草案，候选额度和估值释放分别显示；未释放部分留现金。权重与本金分离，执行层考虑100股单位、费用、滑点和容量。当前分档不回填历史，历史跨周期规则与等权仍可切换。

## 资料与删除边界

当前源码在 `src/quant_workbench_app/`，模块配置在 `config/workbench.json`。新生猪资料位于 `runtime/research/swine_v1_20261025/`，导出位于 `runtime/exports/swine/` 与 `runtime/exports/swine_capital/`，讨论及探索在runtime下。

用户明确授权彻底删除旧养殖大类及生猪研究，覆盖该范围的默认基线只读规则。逐文件删除审计位于 `runtime/cleanup/deletion_manifest.json`，只保留路径、大小、哈希及授权信息，不保留旧研究内容。核验器将授权删除单独核对，不将其伪装成基线未改变。

其他三模块继续依赖 `../research_library/baseline_20261024/quant_workbench/` 中的保留资料，共享行情、环境与凭据保持原位置。不能把整份资料库当缓存删除。迁移历史记录只用于完整性审计，现行研究范围与执行规则以本目录AGENTS.md为准。

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

后台截图脚本创建独立Windows桌面，子进程在其中绘制窗口，通过PrintWindow捕获该窗口。不切换活动桌面，不注入键鼠，不读取用户桌面。截图保存在 `runtime/verification_artifacts/background/`。首版实现、截图生成、单项测试通过均不等于完成；必须查看截图、修复缺陷、复验。

基础数据重建顺序：`collect_swine.py` → `collect_swine_documents.py` → `collect_swine_history.py` → `build_swine_research.py` → `reconcile_swine.py` → `run_swine_research.py` → `audit_swine.py`。采集器默认复用本次独立版本中的缓存；更新数据应建立新版本，不将旧缓存当实时数据。研究报告须完成下述深入研究打包后，再运行`write_swine_report.py`同步工作台报告入口。

完整研究说明在 `runtime/research/swine_v1_20261025/results/research_report.md`，也可在“证据与讨论”页打开。用户已明确旧编译测试和工具缓存暂不处理，不再作为完成门槛；残留清单记录在 `runtime/cleanup/blocked_cache_cleanup.json`。

费用是研究假设；分红按20%保守扣留，不声称重现实际差别税。期末持仓按收盘估值，未清仓；结果不含清仓费用。文件完整性、账本对账与程序测试通过均不证明投资有效性。

## 深入研究与复现

当前完整研究位于 `runtime/research/swine_deep_20261025/report/research.md`，包括原始来源、事实、假设、研究判断、缺口和可复算模型。运行 `scripts/collect_swine_deep.py`、`scripts/collect_swine_financial_originals.py`、`scripts/collect_swine_answers.py`、`scripts/collect_swine_price_history.py` 后，以 `scripts/build_swine_deep.py` 建模，`scripts/stress_swine_policy.py` 计算规则与执行敏感性，`scripts/package_swine_deep.py` 生成资料包。研究目录中的 `python model/run.py` 可独立重算资金、供给、恢复、经营反推和分档模型，`python model/run_policy.py` 用复制的完整输入重新运行1,080个情景和686个门槛敏感性情景。

当前分档规则位于`config/swine_allocation.json`：成本、现金及经营现金减资本开支的压力共同决定候选档位，条件价值覆盖决定额度释放，12组估值假设敏感性保留。默认假设和分档不是个股买卖结论；全部权重均可追到证据与输入。新UI状态为swine_v3，旧v2保留可兼容研究输入，同时按用户新偏好将资金默认口径迁移到当前分档草案。

跨周期规则见 `config/swine_cycle_policy.json`。冻结新增保留实际股数，不会因股价下跌机械补足原权重；低估与去化条件仍成立时，允许向阶段目标再平衡。历史财报货币资金是未扣受限的上界代理，当前经营页另展示已核实受限扣减。
