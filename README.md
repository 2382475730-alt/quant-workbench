# 猪逻辑公园

原生 Tk 桌面工作台，双击 `LaunchWorkbench.bat` 启动。四个模块为生猪养殖研究、单股研究、指数增强和小资金配置。

本次更新加入生猪产能、调控区间、价格与六家公司比较，展示可动用现金、资产负债率及PB；母猪存栏采用柱状图。四个模块统一加深日期和说明，涨跌按红涨绿跌显示，超限提示使用琥珀色，并调整小窗口下的换行和图表空间。

总览数据观察日为2026-10-29，各指标列明期间；历史模型和报告沿用各自数据日期。18份报告及说明提供文字修订版，保留原数字、表格、代码与来源。

## GitHub中的内容

- 当前源码、配置、脚本、测试、依赖锁文件和说明。
- 研究基线源码保留原相对路径。原始数据与资料通过私有Release附件恢复。
- 基础数据：[snapshot-20261025](https://github.com/2382475730-alt/quant-workbench/releases/tag/snapshot-20261025)。
- 本次增量：[update-20261101](https://github.com/2382475730-alt/quant-workbench/releases/tag/update-20261101)，包含总览官方资料、报告阅读版及后台界面核验记录。

凭据、`.env`、虚拟环境、个人界面状态、讨论笔记和浏览器缓存不上传。数据包恢复前核对SHA256，已有文件不同则停止，保留本地修改。

## 新电脑恢复与运行

需要Windows、带Tk的Python 3.11及以上（推荐3.13）、Git与GitHub CLI。私有仓库使用自己的GitHub账号登录：

```powershell
gh auth login
gh repo clone 2382475730-alt/quant-workbench
cd quant-workbench
gh release download snapshot-20261025 --repo 2382475730-alt/quant-workbench --dir .snapshot/base
py -3.13 quant_workbench/scripts/restore_github_snapshot.py .snapshot/base
gh release download update-20261101 --repo 2382475730-alt/quant-workbench --dir .snapshot/update-20261101
py -3.13 quant_workbench/scripts/restore_github_snapshot.py .snapshot/update-20261101 --manifest quant_workbench/docs/github/update-20261101-manifest.json
py -3.13 -m venv quant_workbench/.venv
quant_workbench/.venv/Scripts/python.exe -m pip install -e "./quant_workbench[dev,reports]"
.\LaunchWorkbench.bat
```

使用uv时，可用 `uv sync --project quant_workbench --extra dev --extra reports --locked` 代替创建环境和安装依赖。既有工作区沿用原环境；已恢复基础数据时，只需下载并恢复增量包。

历史快照可离线读取。重新采集行情时，再按 `.env.example` 配置本地数据源凭据。报告HTML使用相对链接，可随仓库移动。

## 检查与复现

进入 `quant_workbench` 后执行：

```powershell
.\.venv\Scripts\python.exe scripts\test_background.py
.\.venv\Scripts\python.exe scripts\capture_background.py
.\.venv\Scripts\python.exe scripts\verify.py
```

界面检查在独立Windows后台桌面运行，覆盖四模块、六家公司及标准和小窗口。界面验收记录包含119个窗口状态，文件核验与策略收益检验分别记录。

运行、数据重建与研究假设见[项目说明](quant_workbench/README.md)；快照恢复见[数据说明](quant_workbench/docs/github/README.md)。
