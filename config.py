# config.py
# -------------------------------------------------------
# Team Configuration
# -------------------------------------------------------
# Each team sets this to their team name. This controls
# where backtest CSVs are saved in ObjectStore and where
# research notebooks read from.
#
# Valid values:
#   "production"  - Master/instructor version
#   "team_1"      - Team 1
#   "team_2"      - Team 2
#   "team_3"      - Team 3
#   "team_4"      - Team 4
#   "team_5"      - Team 5
#   "team_6"      - Team 6
#   "team_7"      - Team 7
# -------------------------------------------------------
TEAM_ID = "production"

# -------------------------------------------------------
# Shared signal parameters (single source of truth)
# -------------------------------------------------------
# Keep alpha model and research notebooks aligned by
# importing these values instead of hard-coding them.
ALPHA_SIGNAL_WEIGHTS = (0.2, 0.5, 0.3)  # short / medium / long
ALPHA_SIGNAL_TEMPERATURE = 3.0
ALPHA_MIN_MAGNITUDE = 0.05
