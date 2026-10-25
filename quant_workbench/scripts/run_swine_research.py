"""All eligible entry days, common end and equal holding periods; no best-day selection."""
import sys
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
from quant_workbench_app.swine_data import ROOT, dump
from quant_workbench_app.swine_engine import STRATEGIES, SwineModel, export_run


def main():
    model = SwineModel()
    rows = []
    for strategy in STRATEGIES:
        for start in model.entry_dates:
            index = model.dates.get_loc(start)
            for horizon in (0, 20, 60):
                if horizon and index+horizon-1 >= len(model.dates):
                    continue
                end = model.dates[index+horizon-1] if horizon else model.dates[-1]
                result = model.run(start, strategy, end=end, details=False)
                rows.append({**result['summary'], 'horizon': horizon})
        print(strategy, len(rows), 'cumulative scenarios', flush=True)
    dump(ROOT / 'results/rolling_entries.json', rows)
    pd.DataFrame([{k:v for k,v in r.items() if k not in ('codes','costs')} for r in rows]).to_csv(
        ROOT / 'results/rolling_entries.csv', index=False, encoding='utf-8-sig')
    summaries = []
    frame = pd.DataFrame(rows)
    for (strategy, horizon), group in frame.groupby(['strategy', 'horizon']):
        summaries.append({'strategy': strategy, 'horizon': int(horizon), 'count': len(group),
                          'positive_share': float((group['return'] > 0).mean()),
                          'median_return': float(group['return'].median()), 'worst_return': float(group['return'].min()),
                          'best_return': float(group['return'].max()), 'worst_drawdown': float(group.max_drawdown.min())})
    dump(ROOT / 'results/rolling_summary.json', summaries)
    for strategy in STRATEGIES:
        result = model.run('2026-06-01', strategy)
        folder = ROOT / 'results/initial_ledgers' / strategy
        export_run(result, folder, overwrite=True)
    print('completed', len(rows), 'scenarios')


if __name__ == '__main__':
    main()
