"""Keep the base research entry linked to the current deeper research package."""
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
source=PROJECT/'runtime/research/swine_deep_20261025/report/research.md'
target=PROJECT/'runtime/research/swine_v1_20261025/results/research_report.md'
if not source.is_file():
    raise RuntimeError('Run build_swine_deep.py and package_swine_deep.py first')
target.write_text(source.read_text(encoding='utf8'),encoding='utf8')
print('Updated base entry from current source-backed deep research')
