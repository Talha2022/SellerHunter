from datetime import datetime, timezone
from services.seller_filter import lifetime_feedback, qualifies

def first(*values):
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return None

def address_text(value):
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        fields = ["name","addressLine1","addressLine2","addressLine3","city","state","postalCode","country"]
        return ", ".join(str(value[k]).strip() for k in fields if value.get(k)) or None
    if isinstance(value, (list, tuple)):
        return ", ".join(str(x).strip() for x in value if x) or None
    return None

def address_country(value):
    # Keepa address is a list whose last element is the 2-letter country code, e.g. [..., "CA", "92602", "US"]
    if isinstance(value, dict):
        code = value.get("country") or value.get("countryCode")
    elif isinstance(value, (list, tuple)) and value:
        code = value[-1]
    else:
        return None
    code = str(code or "").strip().upper()
    return code if len(code) == 2 and code.isalpha() else None

def status_for(feedback, country):
    if feedback is None:
        return "unverified"
    if not qualifies(feedback):
        return "not_qualified"
    if country is None:
        return "no_address"
    return "qualified" if country == "US" else "non_us"

def normalize(seller):
    sid = first(seller.get("sellerId"), seller.get("seller_id"))
    if not sid:
        raise ValueError("Seller object has no sellerId")
    feedback = lifetime_feedback(seller)
    business = seller.get("business") or seller.get("businessInfo") or {}
    if not isinstance(business, dict):
        business = {}
    address = business.get("address") or business.get("businessAddress") or seller.get("address")
    phone = first(business.get("phoneNumber"), business.get("phone"), seller.get("phoneNumber"))
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "seller_id": sid,
        "seller_name": first(seller.get("sellerName"), seller.get("name")),
        "lifetime_feedback": feedback,
        "feedback_verified": int(feedback is not None),
        "business_name": first(business.get("company"), business.get("businessName"), business.get("legalName"), seller.get("businessName")),
        "business_address": address_text(address),
        "phone_number": phone,
        "profile_url": f"https://www.amazon.com/sp?seller={sid}",
        "marketplace": "Amazon.com",
        "source_provider": "Keepa",
        "discovered_at": stamp,
        "enriched_at": stamp,
        "verification_status": status_for(feedback, address_country(address)),
        "country": address_country(address),
        "last_error": None
    }
