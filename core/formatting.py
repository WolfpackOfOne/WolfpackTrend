"""Formatting and parsing utilities.

Rules:
- Pure functions only
- No QC imports
- Deterministic output for same inputs
"""
import re


def build_csv(data, columns):
    """
    Build CSV string from list of dictionaries.

    Preserves existing column order and formatting semantics.
    """
    lines = [','.join(columns)]
    for row in data:
        values = [str(row.get(col, '')) for col in columns]
        lines.append(','.join(values))
    return '\n'.join(lines)


def build_order_tag(tier, signal_strength, week_id, scale_day):
    """
    Build order tag string with execution metadata.

    Tag format is parse-compatible with existing logs:
        tier=<tier>;signal=<signal>;week_id=<week_id>;scale_day=<scale_day>
    """
    return (
        f"tier={tier};"
        f"signal={signal_strength:.4f};"
        f"week_id={week_id};"
        f"scale_day={scale_day}"
    )


def extract_week_id_from_tag(tag):
    """
    Extract week_id from order tag string.

    Args:
        tag: Order tag in format 'tier=moderate;week_id=2024-01-02;...'

    Returns:
        str: Week ID (YYYY-MM-DD format) or None if not found
    """
    if not tag:
        return None

    match = re.search(r'week_id=([^;]+)', tag)
    if match:
        week_id = match.group(1).strip()
        return week_id if week_id else None
    return None
