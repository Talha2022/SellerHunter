from datetime import datetime, timezone


def _valid_int(value):
    try:
        v = int(value)
        return v if v >= 0 else None
    except (TypeError, ValueError):
        return None


def sold_by_amazon(product):
    # availabilityAmazon != -1 or stats.current[0] > 0 means Amazon has an offer
    avail = product.get("availabilityAmazon")
    if avail is not None and avail != -1:
        return True
    current = (product.get("stats") or {}).get("current") or []
    amazon_price = current[0] if len(current) > 0 else None
    return amazon_price is not None and amazon_price > 0


def current_price_usd(product):
    stats = product.get("stats") or {}
    current = stats.get("current") or []
    candidates = [
        stats.get("buyBoxPrice"),
        current[10] if len(current) > 10 else None,  # New FBA
        current[1] if len(current) > 1 else None,    # New
    ]
    for cents in candidates:
        val = _valid_int(cents)
        if val is not None and val > 0:
            return round(val / 100.0, 2)
    return None


def category_name(product):
    tree = product.get("categoryTree") or []
    names = [str(node["name"]).strip() for node in tree if isinstance(node, dict) and node.get("name")]
    if names:
        return " > ".join(names)
    root = product.get("rootCategory")
    return str(root) if root else None


def extract_product(product, seller_id):
    stats = product.get("stats") or {}
    brand = (product.get("brand") or "").strip() or None
    return {
        "seller_id": str(seller_id),
        "asin": str(product.get("asin") or "").strip(),
        "brand": brand,
        "category": category_name(product),
        "monthly_sold": _valid_int(product.get("monthlySold")),
        "fba_sellers": _valid_int(stats.get("offerCountFBA")),
        "total_offers": _valid_int(stats.get("totalOfferCount")),
        "price": current_price_usd(product),
        "sold_by_amazon": int(sold_by_amazon(product)),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def filter_reason(row, min_fba=1, min_monthly_sales=0, min_price=0.0, max_price=10000.0):
    if row["sold_by_amazon"]:
        return "Rejected: sold by Amazon"
    if row["fba_sellers"] is None:
        return "Rejected: FBA seller count unavailable (keep exact FBA enabled)"
    if row["fba_sellers"] < min_fba:
        return f"Rejected: FBA sellers ({row['fba_sellers']}) < {min_fba}"
    if min_monthly_sales > 0 and (row["monthly_sold"] is None or row["monthly_sold"] < min_monthly_sales):
        return f"Rejected: past-month sales ({row['monthly_sold']}) < {min_monthly_sales}"
    if row["price"] is None or not (min_price <= row["price"] <= max_price):
        return f"Rejected: price (${row['price']}) not in ${min_price:.2f}–${max_price:.2f}"
    return None


def matches_filters(row, min_fba=1, min_monthly_sales=0, min_price=0.0, max_price=10000.0):
    return filter_reason(row, min_fba, min_monthly_sales, min_price, max_price) is None


def dedupe_brands(rows, existing_brands=None):
    # Skip any brand already seen (within this batch or across earlier sellers)
    seen = {b.strip().lower() for b in (existing_brands or ()) if b and b.strip()}
    kept = []
    for row in rows:
        brand = (row.get("brand") or "").strip().lower()
        if brand:
            if brand in seen:
                continue
            seen.add(brand)
        kept.append(row)
    return kept
