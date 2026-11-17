def lifetime_feedback(seller):
    values = seller.get("ratingCount")
    if not isinstance(values, (list, tuple)) or len(values) < 4:
        return None
    try:
        return int(values[3]) if values[3] is not None else None
    except (TypeError, ValueError):
        return None

def qualifies(count):
    return count is not None and 0 <= count < 50
