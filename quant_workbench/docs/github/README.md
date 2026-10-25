# GitHub数据快照

源码在Git中，大型数据在同一私有仓库的`snapshot-20261025` Release。`snapshot-manifest.json`记录每个附件及其每个成员的大小、相对路径和SHA256。附件可分开下载，恢复前必须全部齐备。

快照包括当前保留的research_library、新生猪研究、删除审计和验证产物。排除凭据、Python/Node环境、编译和工具缓存、日志、用户导出、探索记录和UI状态。原始研究快照保持原样，里面的绝对路径或旧删除核验记录属于创建时证据，不代表迁移到新电脑后那些绝对路径仍可访问。

在仓库根目录执行：

```powershell
gh release download snapshot-20261025 --repo 2382475730-alt/quant-workbench --dir .snapshot
py -3.13 quant_workbench/scripts/restore_github_snapshot.py .snapshot --check-only
py -3.13 quant_workbench/scripts/restore_github_snapshot.py .snapshot
```

校验模式会核对全部成员内容、路径边界及已存在文件。正式恢复只写缺失文件，拒绝覆盖不同内容。原目录的`.env`和`.venv`都不会被恢复或更改。

重新发布快照前，可运行`prepare_github_snapshot.py`在本地检查候选文件并生成附件；检测到已配置凭据或常见密钥特征时会停止，日志只显示路径、不显示值。Git数据快照在发布时冻结；后续研究应使用新版本标签，不能用旧清单证明新文件已核对。
