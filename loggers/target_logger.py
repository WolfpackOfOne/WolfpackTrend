"""Daily per-symbol target state logging."""
from core.formatting import build_csv


TARGET_COLUMNS = [
    'date', 'week_id', 'symbol', 'start_w', 'weekly_target_w',
    'scheduled_fraction', 'scheduled_w', 'actual_w', 'scale_day'
]


class TargetLogger:
    def __init__(self):
        self.targets = []

    def log(self, algorithm, pcm, current_date):
        if pcm is None or not hasattr(pcm, 'get_daily_target_state'):
            return

        rows = pcm.get_daily_target_state(algorithm)
        if not rows:
            return

        for row in rows:
            self.targets.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'week_id': row.get('week_id', ''),
                'symbol': row.get('symbol', ''),
                'start_w': row.get('start_w', ''),
                'weekly_target_w': row.get('weekly_target_w', ''),
                'scheduled_fraction': row.get('scheduled_fraction', ''),
                'scheduled_w': row.get('scheduled_w', ''),
                'actual_w': row.get('actual_w', ''),
                'scale_day': row.get('scale_day', '')
            })

    def save(self, algorithm):
        if self.targets:
            csv_content = build_csv(self.targets, TARGET_COLUMNS)
            algorithm.ObjectStore.Save("wolfpack/targets.csv", csv_content)
        return len(self.targets)
