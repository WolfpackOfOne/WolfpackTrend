"""Daily portfolio snapshot logging."""
from core.formatting import build_csv


SNAPSHOT_COLUMNS = [
    'date', 'nav', 'cash', 'gross_exposure', 'net_exposure',
    'long_exposure', 'short_exposure', 'daily_pnl', 'cumulative_pnl',
    'daily_slippage', 'num_positions', 'estimated_vol'
]


class SnapshotLogger:
    def __init__(self, team_id="production"):
        self.team_id = team_id
        self.snapshots = []

    def log(self, row):
        self.snapshots.append(row)

    def save(self, algorithm):
        if self.snapshots:
            csv_content = build_csv(self.snapshots, SNAPSHOT_COLUMNS)
            algorithm.ObjectStore.Save(f"{self.team_id}/daily_snapshots.csv", csv_content)
        return len(self.snapshots)
