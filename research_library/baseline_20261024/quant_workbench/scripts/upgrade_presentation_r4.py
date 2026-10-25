"""Update only unfrozen presentation artifacts for the completed r4 repair."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]


def update(relative, replacements):
    path = root/relative
    text = path.read_text(encoding='utf-8')
    for old, new in replacements:
        text = text.replace(old, new)
    path.write_text(text, encoding='utf-8')


update('scripts/write_enhancement_report.py', [
    ('当前工程版本v1r3', '当前工程版本v1r4'),
    ('本轮v1/v1r2失败结果保留', '本轮v1/v1r2/v1r3失败结果保留'),
    ('且早期区间未能启动', '旧版早期区间曾未能启动，修订版仍保留首次失败'),
    ('18项', '24项'), ('81项', '108项'), ('810个', '1080个'),
    ('三个工程版本', '四个工程版本'), ('三个冻结版本', '四个冻结版本'),
    ('v1r3整数订单缓冲', 'v1r4沿用整数订单缓冲'),
    ('区间/方案v1r3', '区间/方案v1r4'),
    ('防御备选2017年启动失败仍未消失：', '前三版防御备选2017年启动失败的链条是：'),
    ('2017年启动失败仍未消失', '2017年启动失败在前三版保留'),
    ('本地2016年风险窗口', 'v1r4按首次实际持仓关闭豁免，失败后仍允许依法重试，之后清仓不能重获豁免。本地2016年风险窗口'),
    ('all_81_experiments.csv', 'all_108_experiments.csv'),
    ("['enhancement_v1','enhancement_v1r2','enhancement_v1r3']", "['enhancement_v1','enhancement_v1r2','enhancement_v1r3','enhancement_v1r4']"),
    ('len(all_runs)==81', 'len(all_runs)==108'),
    ("artifacts/enhancement_v1r3/runs/{phase}/momentum_constrained_base", "artifacts/enhancement_v1r4/runs/{phase}/momentum_constrained_base"),
    ("config/enhancement_v1r3.json", "config/enhancement_v1r4.json"),
    ('防御方案存在无法启动的历史区间', '前三版防御方案存在未启动区间，v1r4修复重试状态但仍保留首次失败'),
    ('`frozen_reference_audit.json`还', '`turnover_reconciliation.json`按首次实际成交日独立复核建仓豁免：r4原结果的换手审计仍使用区间起始日，延后建仓会误报首次换手；当前展示纠正此统计标志，原结果/净值/成交不改写。`frozen_reference_audit.json`还'),
])
update('scripts/enhancement_sources.py', [('v1r3', 'v1r4'), ('三个冻结版本及81项', '四个冻结版本及108项'), ('全部81项', '全部108项'), ('"totalRows": 10', '"totalRows": 12')])
update('research/quant_agent_design.md', [
    ('三个版本的冻结输入、81个实验清单、810个结果文件', '四个版本的冻结输入、108个实验清单、1080个结果文件'),
    ('三个工程版本共18个基础比较', '四个工程版本共24个基础比较'),
    ('防御备选的早期启动失败仍保留。', '防御备选的早期启动失败仍保留。v1r4又修正首次实际建仓状态，避免失败后被换手预算锁死；不改变已有持仓的换手规则。'),
])
update('research/quant_agent_system_prompt.md', [
    ('v1/v1r2/v1r3共81项', 'v1/v1r2/v1r3/v1r4共108项'),
    ('当前实现v1r3', '当前实现v1r4'), ('三个enhancement协议', '四个enhancement协议'),
])
update('README.md', [
    ('三个工程版本共81项', '四个工程版本共108项'), ('指数增强v1r3主方案', '指数增强v1r4主方案'),
    ('防御备选早期无法建仓的零收益是失败结果，不是有效避险。', '前三版防御备选早期无法建仓的零收益是失败结果；v1r4修复首次实际建仓前的重试状态，保留首次失败，不能把旧版零收益叫有效避险。'),
    ('三版计算代码', '四版计算代码'),
    ('、`enhancement_v1r3_protocol.md`。', '、`enhancement_v1r3_protocol.md`、`enhancement_v1r4_protocol.md`。'),
    ('10行全收益', '12行全收益'),
])
