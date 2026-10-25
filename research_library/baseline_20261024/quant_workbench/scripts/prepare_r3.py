"""One-time, explicit version fork; refuses to replace existing version files."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
p = root / 'src/quant_workbench'

def save(path, text):
    with path.open('x', encoding='utf-8') as handle:
        handle.write(text)

s = (p/'enhancement_optimizer_r2.py').read_text(encoding='utf-8')
s = s.replace('Bounds, LinearConstraint, minimize', 'Bounds, LinearConstraint, milp, minimize')
s = s.replace('self.audit = []', 'self.audit = []\n        self.last_share_target = None')
s = s.replace('s, data = self.settings, self.inputs', 's, data = self.settings, self.inputs\n        self.last_share_target = None')
s = s.replace('        return {c: float(max(0, w))', '        self.last_share_target = projection.get("reference_shares")\n        return {c: float(max(0, w))')
s = s[:s.index('\ndef project_lots(')]
save(p/'enhancement_optimizer_r3.py', s)
s = (p/'enhancement_research_r2.py').read_text(encoding='utf-8').replace('enhancement_v1r2', 'enhancement_v1r3').replace('enhancement_optimizer_r2', 'enhancement_optimizer_r3').replace('enhancement_research_r2', 'enhancement_research_r3').replace('enhancement_engine', 'enhancement_engine_r3').replace('twelve', 'eighteen').replace('2*12', '2*18')
save(p/'enhancement_research_r3.py', s)
s = (p/'enhancement_engine.py').read_text(encoding='utf-8')
s = s.replace('scheduled[pos + execution_delay] = (str(pd.Timestamp(key).date()), weights)', 'scheduled[pos + execution_delay] = (str(pd.Timestamp(key).date()), weights, None)')
s = s.replace('scheduled[pos] = (str(initial_date.date()), target)', 'scheduled[pos] = (str(initial_date.date()), target, getattr(decision_factory, "last_share_target", None))')
s = s.replace('decision_date, target = scheduled[day]', 'decision_date, target, share_target = scheduled[day]')
s = s.replace('desired = quantity(codes[j], equity_open * weight / price) if weight else 0', 'desired = (int(share_target.get(codes[j], 0)) if share_target is not None\n                           else quantity(codes[j], equity_open * weight / price) if weight else 0)')
s = s.replace('scheduled[day + execution_delay] = (str(timestamp.date()), target)', 'scheduled[day + execution_delay] = (str(timestamp.date()), target, getattr(decision_factory, "last_share_target", None))')
s = s.replace('ETF ticks/fees and causal state feedback', 'frozen closing-share instructions, ETF ticks/fees and causal state feedback')
save(p/'enhancement_engine_r3.py', s)
c = json.loads((root/'config/enhancement_v1r2.json').read_text())
c['version'] = 'enhancement_v1r3'
save(root/'config/enhancement_v1r3.json', json.dumps(c, indent=2))
