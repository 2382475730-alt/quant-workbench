"""Create the final, separately sealed startup-state repair."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
src = root/'src/quant_workbench'


def save(path, text):
    with path.open('x', encoding='utf-8') as handle:
        handle.write(text)


s = (src/'enhancement_optimizer_r3.py').read_text(encoding='utf-8')
s = s.replace('class DecisionMaker:', '''class StartupBudget:
    """The initial turnover exemption ends after the first actual investment."""
    def __init__(self):
        self.ever_invested = False

    def exempt(self, actual):
        self.ever_invested |= any(weight > 1e-9 for weight in actual.values())
        return not self.ever_invested


class DecisionMaker:''')
s = s.replace('self.audit = []', 'self.audit = []\n        self.startup = StartupBudget()')
s = s.replace('s, data = self.settings, self.inputs', 's, data = self.settings, self.inputs\n        initial = self.startup.exempt(actual)')
save(src/'enhancement_optimizer_r4.py', s)
s = (src/'enhancement_research_r3.py').read_text(encoding='utf-8')
s = s.replace('enhancement_v1r3', 'enhancement_v1r4').replace('enhancement_optimizer_r3', 'enhancement_optimizer_r4').replace('enhancement_research_r3', 'enhancement_research_r4').replace('eighteen', 'twenty-four').replace('2*18', '2*24')
save(src/'enhancement_research_r4.py', s)
config = json.loads((root/'config/enhancement_v1r3.json').read_text())
config['version'] = 'enhancement_v1r4'
save(root/'config/enhancement_v1r4.json', json.dumps(config, indent=2))
