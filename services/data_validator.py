def validate(record):
    problems = []
    for key in ("seller_id", "seller_name", "profile_url"):
        if not record.get(key):
            problems.append(f"Missing {key}")
    if record.get("feedback_verified") and not (0 <= record["lifetime_feedback"] < 50):
        problems.append("Feedback count outside 0-49")
    for key in ("business_name", "business_address", "phone_number"):
        if not record.get(key):
            problems.append(f"{key} unavailable")
    return problems
