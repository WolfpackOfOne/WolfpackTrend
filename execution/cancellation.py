"""Order cancellation decision molecule.

Contains signal-aware and legacy cancellation logic.
"""
from core.formatting import extract_week_id_from_tag


def should_cancel_signal_aware(order_week_id, current_week_id):
    """
    Determine if an order should be cancelled based on week_id comparison.

    Only cancels if order is from a PREVIOUS cycle (older date).
    YYYY-MM-DD format allows lexicographic comparison.

    Returns:
        bool: True if order should be cancelled
    """
    if not order_week_id or not current_week_id:
        return False
    return order_week_id < current_week_id


def should_cancel_legacy(check_count, max_checks):
    """
    Determine if an order should be cancelled using legacy check-count logic.

    Returns:
        bool: True if order should be cancelled
    """
    return check_count >= max_checks
