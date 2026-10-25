"""Create and execute the offline review notebook from frozen evidence."""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient
from nbconvert import HTMLExporter

root = Path(__file__).resolve().parents[1]
out = root/'reports/small_capital_v1'
cells = []
def md(text):
    cells.append(nbf.v4.new_markdown_cell(text))
def code(text):
    cells.append(nbf.v4.new_code_cell(text))

md('''# 10万元小资金组合：可执行复核

读者：需要复查数据、整数持仓和收费后客户价值的研究者。结论：减少订单可验证，尚未证明稳定的收费收益优势。

全部历史已见，当前为研究原型，前向数据0天。本笔记只读取本地冻结输入和结果，不连接网络、券商或客户。
从上到下执行；`review.py`独立重建148个新账户的份额流水，并重新运行四个近期基准实验，与冻结表逐项比较。
完整151项包括3个旧v1r4缩小重跑，均核对哈希、财富平衡及成交时序。
''')
code('''from pathlib import Path
import json, runpy
import pandas as pd
from IPython.display import display, Image
from quant_workbench.small_capital_v1.data import ROOT, BASE
OUT = ROOT/'reports/small_capital_v1'
checks = runpy.run_path(str(OUT/'review.py'))['review']()
checks''')
md('''## 1. 全部尝试与冻结
固定协议在research/small_capital_v1/protocol.md；原始来源与版本回执在同目录sources/。
151项是主比较、压力、规模、收费及追加资金的完整登记范围，不是151个独立发现。
此前研究的选择偏差不能由滚动回溯或重采样消除。''')
code('''registry = pd.read_csv(OUT/'experiment_registry.csv')
all_results = pd.read_csv(OUT/'all_experiments.csv')
assert len(registry) == len(all_results) == 151
assert set(registry.status) == {'complete'}
display(registry.groupby(['strategy','status']).size().to_frame('experiments'))
freeze = json.loads((BASE/'freeze.json').read_text(encoding='utf-8'))
print('规则冻结时间:', freeze['created_at'], '输入文件数:', len(freeze['hashes']))''')
md('''## 2. 公平主比较
每个区间独立10万元启动，无外部现金流，扣交易成本未扣服务费。固定ETF为66.5%沪深300、28.5%中证500、5%现金；A风险预算与C不交易区间共用70/30内部比例。
三张图的纵轴按各期数据独立缩放，不能凭线条高度比较跨期风险；以表中回撤和波动核对。''')
code('''main = all_results.loc[(all_results.scenario=='base') & (all_results.initial==100000) & (all_results.annual_fee==0) & (all_results.monthly_contribution==0)]
display(main[['phase','strategy','total_return','cagr','max_drawdown','volatility','average_exposure','trade_count','fees','slippage']])
display(Image(filename=str(OUT/'historical_comparison.png')))''')
md('''## 3. 整数持仓不是已成交
参考日期2026-10-23；当前现金10万元，无持仓。实际佣金及权限尚未核验。证券份额、目标权重、现金预留和下一日价格风险分别显示。''')
code('''example = json.loads((BASE/'example_plan.json').read_text(encoding='utf-8'))
display(pd.DataFrame(example['rows']))
display({k:example[k] for k in ['fill_status','available_cash_reference','estimated_fees','estimated_slippage','predicted_vol','permissions']})
assert all(r['target_shares'] % 100 == 0 for r in example['rows'])
display(pd.read_csv(OUT/'current_industry_proxy.csv'))''')
md('''## 4. 风险漂移与压力
18%是含估计误差缓冲的目标预算，不是最大损失或已保证波动。月末决策无法保证月中不超限。涨跌停、现金或流动性约束可能阻止降仓。
双倍成本、延迟、漏执行、部分执行和三阶段建仓是条件情景，不能解释成未来盈利概率。''')
code('''display(pd.DataFrame(json.loads((BASE/'risk_drift.json').read_text())))
stress = all_results.loc[(all_results.strategy=='band') & (all_results.initial==100000) & (all_results.annual_fee==0) & (all_results.monthly_contribution==0)]
display(stress.pivot(index='scenario',columns='phase',values='total_return'))
display(pd.DataFrame(json.loads((BASE/'uncertainty.json').read_text())))''')
md('''## 5. 收费后价值与外部现金流
年费0/300/600/1200元是研究假设，首日及每周年首交易日从现金收全年费用，最后不足一年仍全额。与免费简单ETF比较。
追加资金在每月首个交易日交易前入账，不能直接用期末财富除初始本金报告收益；下表total_return为时间加权收益。''')
code('''fees = pd.read_csv(OUT/'client_value_fees.csv')
display(fees.loc[fees.strategy=='band'])
display(Image(filename=str(OUT/'service_fee_value.png')))
display(all_results.loc[all_results.monthly_contribution>0, ['strategy','external_contributions','ending_equity','net_investment_profit','total_return']])''')
md('''## 6. 结论与继续状态
- 10万元宜先研究1—2只宽基ETF；直接持股B仅完成交易单位可行性审计，没有策略收益结论。
- C主要改善调仓次数与部分风险；相对A节省的费用不能支持假设年费，所有主比较不确定性区间均含零。
- 5万元以下、未登记本金节点、特殊权限、新证券及不同风险预算均需重新研究。单边上涨、风险突变或执行偏差可使方案落后。
- 前向模拟尚未开始。商业使用前还缺适当性、机构和人员资质、商业数据许可、可靠执行能力和真实客户净价值证据。
- UI默认页已实际打开核对；用户按Esc停止后未继续交互，不能声称其余标签已完成人工操作验证。

复核和软件测试通过只证明实现与账本一致，不能替代产品有效性。详见report.md、theory.md、compliance.md和agent_guide.md。''')
nb = nbf.v4.new_notebook(cells=cells, metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}})
NotebookClient(nb, timeout=180, kernel_name='python3', resources={'metadata':{'path':str(root)}}).execute()
nbf.write(nb, out/'review.ipynb')
body, _ = HTMLExporter().from_notebook_node(nb)
(out/'review.html').write_text(body, encoding='utf-8')
print('Executed', len([c for c in nb.cells if c.cell_type=='code']), 'cells; saved ipynb/html')
