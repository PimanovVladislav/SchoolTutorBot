from __future__ import annotations


def plan_topic_insert(
    existing_orders: list[int], requested: int | None
) -> tuple[int, list[int]]:
    """Номер новой темы и новые номера уже существующих.

    Если номер не задан — тема в конец. Если номер занят, новая тема
    занимает его, а эта и все последующие сдвигаются на +1.
    """
    next_last = (max(existing_orders) if existing_orders else 0) + 1
    if requested is None:
        return next_last, list(existing_orders)
    try:
        number = int(requested)
    except (TypeError, ValueError):
        return next_last, list(existing_orders)
    if number < 1:
        number = 1
    if number > next_last:
        return next_last, list(existing_orders)
    shifted = [order + 1 if order >= number else order for order in existing_orders]
    return number, shifted
