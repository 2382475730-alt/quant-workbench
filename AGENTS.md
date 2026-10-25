# 工作区维护规则

- 活动项目是 `quant_workbench/`。日常入口为根目录 `LaunchWorkbench.bat`。
- 产品为原生 Tk 桌面，四个平级模块：养殖个股组合、单股研究、指数增强、小资金配置。
- 当前界面代码位于 `quant_workbench/src/quant_workbench_app/`；模块登记位于 `quant_workbench/config/workbench.json`。
- `research_library/baseline_20261024/` 是保持原相对路径的研究基线。默认只读，不为了整理页面修改、覆盖或重新封存旧计算、输入、实验和报告。
- 新页面状态、探索记录、导出、检查结果写入 `quant_workbench/runtime/`。新的研究版本应在资料库新目录创建，使用独立协议与结果，不能覆盖基线。
- `.env` 和旧 `.venv` 保留原位置。不要输出凭据，也不要凭空迁移或重建已有环境。
- 文件迁移需记录原位置、新位置和校验；哈希通过只说明完整性，不说明投资有效性。
- 验证命令详见 `quant_workbench/README.md`。界面修改需检查四个模块及六家公司，验证口径、状态、导出路径和实际窗口显示。
