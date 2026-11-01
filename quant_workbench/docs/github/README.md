# GitHub数据快照

源码保存在Git中。数据分为基础快照 `snapshot-20261025` 和增量包 `update-20261101`，都位于同一私有仓库的Release附件。基础清单为 `snapshot-manifest.json`，增量清单为 `update-20261101-manifest.json`，逐项记录相对路径、大小和SHA256。

基础快照包含保留的研究资料库、10月25日生猪研究、删除审计与当时的核验产物。增量包增加10月29日总览官方资料、10月31日报告阅读版与11月1日界面验收记录，保留旧快照。

## 恢复

在仓库根目录执行，首次恢复先基础、后增量：

```powershell
gh release download snapshot-20261025 --repo 2382475730-alt/quant-workbench --dir .snapshot/base
py -3.13 quant_workbench/scripts/restore_github_snapshot.py .snapshot/base
gh release download update-20261101 --repo 2382475730-alt/quant-workbench --dir .snapshot/update-20261101
py -3.13 quant_workbench/scripts/restore_github_snapshot.py .snapshot/update-20261101 --manifest quant_workbench/docs/github/update-20261101-manifest.json
```

添加 `--check-only` 可只核验、不写入。恢复前检查压缩包、全部成员、路径边界和已存在文件；正式恢复只写缺失文件，遇到不同内容则停止，不覆盖本地修改。增量包中的核验记录位于独立的 `runtime/verification_artifacts/releases/update-20261101/`。

数据包排除凭据、Python/Node环境、工具和浏览器缓存、日志、导出、讨论笔记及个人UI状态。历史资料中的绝对路径属于创建时记录；当前报告阅读版采用相对链接，界面按本地项目位置查找原件。

## 准备增量包

在 `quant_workbench` 目录运行 `scripts/prepare_github_update.py`，输出到 `runtime/github_delivery/update-20261101/`。脚本仅收集明确列出的新资料、阅读版及验收记录，并检查常见密钥和本地已配置凭据；检查结果不记录凭据值。

基础快照继续使用原清单。新的研究版本应建立新标签，避免覆盖已发布附件。
