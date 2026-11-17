MIN_PER_PAGE = 50  # Keepa rejects perPage values below 50

# Sort options shown in the UI -> Keepa sort rule
SORTS = {
    "Recently active (mixed ratings)": ["lastRatingUpdate", "desc"],
    "Newest first (0 ratings first)": ["currentRatingCount", "asc"],
    "Highest ratings first": ["currentRatingCount", "desc"],
}


def discover(client, sample_size=100, min_rating=0, max_rating=49,
             sort="Recently active (mixed ratings)", us_only=True, page=0):
    # Keepa requires perPage >= 50 and (page + 1) * perPage <= 10000.
    # Cost: ~10 tokens + 1 per 100 IDs returned.
    per_page = max(MIN_PER_PAGE, min(int(sample_size), 10000))
    query = {
        "currentRatingCount_gte": int(min_rating),
        "currentRatingCount_lte": int(max_rating),
        "perPage": per_page,
        "page": max(0, int(page)),
    }
    if us_only:
        query["addressCountry"] = ["US"]
    if sort in SORTS:
        query["sort"] = [SORTS[sort]]
    payload = client.seller_finder(query)
    ids = payload.get("sellerIdList") or payload.get("sellerIds") or []
    total = int(payload.get("totalResults", len(ids)) or 0)
    unique_ids = list(dict.fromkeys(str(x) for x in ids if x))
    return unique_ids[:int(sample_size)], total
