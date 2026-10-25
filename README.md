# 量化研究工作台

原生 Tk 桌面工作台，日常入口为 `LaunchWorkbench.bat`。四个平级模块：**生猪养殖研究、单股研究、指数增强、小资金配置**。

生猪研究已在2026-10-25从零重建。首页先展示关键图表与六家公司对比，进一步查看行业周期、成本、利润质量、现金承受力、估值条件、分档权重和资金适配。公司池按核心业务判断，不机械采用90%收入占比；牧原纳入。

## GitHub 中的内容

- 当前应用源码、配置、脚本、测试、依赖锁文件和文档。
- 其他三个模块仍需使用的资料库源码，保持原相对路径，不改写冻结研究。
- [生猪研究说明](quant_workbench/docs/github/swine_research_20261025.md)与[数据快照清单](quant_workbench/docs/github/snapshot-manifest.json)。
- 大型研究数据、原始资料与验证产物放在本仓库的私有 [snapshot-20261025 Release](https://github.com/2382475730-alt/quant-workbench/releases/tag/snapshot-20261025)，不把数GB数据塞进Git提交。

凭据、`.env`、虚拟环境、工具缓存、日志以及个人界面状态不上传。此前已按授权删除的旧养殖研究不会随快照恢复；仅保留删除清单与其他模块仍需的资料。

## 新电脑恢复与运行

需要Windows、Python 3.11及以上（推荐3.13，包含Tk）、Git和GitHub CLI。此仓库为私有，先用自己的GitHub账号登录 `gh auth login`。

```powershell
gh repo clone 2382475730-alt/quant-workbench
cd quant-workbench
gh release download snapshot-20261025 --repo 2382475730-alt/quant-workbench --dir .snapshot
py -3.13 quant_workbench/scripts/restore_github_snapshot.py .snapshot
py -3.13 -m venv quant_workbench/.venv
quant_workbench/.venv/Scripts/python.exe -m pip install -e "./quant_workbench[dev]"
.\LaunchWorkbench.bat
```

如使用uv，可用 `uv sync --project quant_workbench --extra dev --locked` 代替创建环境和安装步骤。恢复脚本核对压缩包及逐文件SHA256；本地文件若不同则停止，不覆盖修改。`--check-only`只验证，不写入。既有工作区无需重建环境。

历史快照可离线查看，不需要凭据。重新采集行情时才按 `.env.example` 在本地配置自己的数据源凭据。

## 检查与研究边界

实际验证请进入 `quant_workbench`，运行：

```powershell
.\.venv\Scripts\python.exe scripts\test_background.py
.\.venv\Scripts\python.exe scripts\capture_background.py
```

后台检查使用独立Windows桌面，不切换当前桌面或注入键鼠。快照交付记录包含63项测试、82个窗口状态、1,080个移动起点情景及686个规则敏感性情景；这些检查不证明投资有效性。跨周期策略仍为明确假设下的研究草案，观察窗口没有跨越完整猪周期。

更详细的运行、数据重建与资料边界见 [当前项目说明](quant_workbench/README.md) 和 [GitHub数据恢复说明](quant_workbench/docs/github/README.md)。
