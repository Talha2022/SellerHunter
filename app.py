import html
import importlib
import streamlit as st
from config import get_settings
from database.db import Database
import services.keepa_client as _keepa_client
importlib.reload(_keepa_client)
from services.keepa_client import KeepaClient
from services.seller_discovery import discover, SORTS
from services.seller_enrichment import normalize
import services.product_filter as _product_filter
importlib.reload(_product_filter)
from services.product_filter import extract_product, filter_reason, dedupe_brands
from exporters.excel_exporter import export
from utils.logger import get_logger

st.set_page_config(page_title="Amazon Seller Finder", page_icon="📊", layout="wide")
st.title("Amazon US Low-Feedback Seller Finder")
st.caption("One-time discovery · Keepa-indexed data · Strict feedback threshold: 0–49")

try:
    cfg = get_settings()
except Exception as exc:
    st.error(str(exc))
    st.info("Copy .env.example to .env and enter your Keepa API key.")
    st.stop()

logger = get_logger(cfg.log_dir)
db = Database(cfg.db_path)
counts = db.counts()
a, b, c, e = st.columns(4)
a.metric("Seller IDs stored", counts["discovered"])
b.metric("Qualified US sellers", counts["qualified"])
c.metric("Pending enrichment", counts["pending"])
e.metric("Skipped (non-US / no address)", counts.get("non_us", 0))

tokens_left = None
try:
    _api = KeepaClient(cfg.api_key, cfg.domain)
    _tok = _api.token_status()
    _api.close()
    tokens_left = _tok.get("tokensLeft")
    st.info(f"Keepa tokens left: **{tokens_left}** · refill: {_tok.get('refillRate')}/min")
except Exception:
    pass

st.subheader("1. Discover sellers")
st.caption("Cost: ~10 tokens + 1 per 100 IDs (Keepa returns at least 50 per request).")
d1, d2, d3, d4 = st.columns(4)
sample = d1.number_input("Seller IDs to store", 1, 10000, 100)
min_rating = d2.number_input("Min feedback (0 = brand-new sellers)", 0, 49, 0)
max_rating = d3.number_input("Max feedback", 0, 49, 49)
page = d4.number_input("Result page (increment on next search)", 0, 199, 0)
sort = st.selectbox("Order", list(SORTS))
us_only = st.checkbox("US business address only (addressCountry = US)", value=True)
if st.button("Discover seller IDs", type="primary"):
    api = KeepaClient(cfg.api_key, cfg.domain)
    try:
        with st.spinner("Querying Keepa Seller Finder..."):
            ids, total = discover(api, int(sample), int(min_rating), int(max_rating), sort,
                                  us_only=us_only, page=int(page))
            added, skipped = db.add_ids(ids[:int(sample)])
        st.success(f"Added {added} new seller IDs ({skipped} duplicates skipped). Provider-reported total: {total}.")
    except Exception as exc:
        logger.exception("Discovery failed")
        st.error(str(exc))
    finally:
        api.close()

st.subheader("2. Enrich seller profiles")
pending = db.pending_ids()
st.write(f"Pending profiles: **{len(pending)}**")
st.caption("Cost: 1 token per seller profile. Enrichment stops automatically when tokens run out.")
default_limit = len(pending)
if tokens_left is not None:
    default_limit = min(default_limit, max(0, tokens_left - 1))  # keep 1 token in reserve
limit = st.number_input("Maximum profiles to enrich now", 1, 10000, max(1, default_limit))
if tokens_left is not None and int(limit) > tokens_left:
    st.warning(f"You only have {tokens_left} tokens; enrichment will stop when they run out.")
if st.button("Enrich pending profiles"):
    api = KeepaClient(cfg.api_key, cfg.domain)
    selected = pending[:int(limit)]
    batches = [selected[i:i+cfg.batch_size] for i in range(0, len(selected), cfg.batch_size)]
    progress = st.progress(0)
    errors = saved = 0
    stopped = None
    try:
        left = api.token_status().get("tokensLeft", 0)
        for n, batch in enumerate(batches, 1):
            if left < len(batch):
                stopped = f"Stopped: only {left} tokens left, next batch needs {len(batch)}."
                break
            try:
                response = api.seller_information(batch)
                left = response.get("tokensLeft", left - len(batch))
                sellers = response.get("sellers") or {}
                items = sellers.values() if isinstance(sellers, dict) else sellers
                for item in items:
                    try:
                        db.save_seller(normalize(item))
                        saved += 1
                    except Exception:
                        errors += 1
                        logger.exception("Seller normalization failed")
            except Exception as exc:
                logger.exception("Seller batch failed")
                if "tokens" in str(exc).lower():
                    stopped = f"Stopped: {exc}"
                    break
                errors += len(batch)
            progress.progress(n / max(1, len(batches)))
        st.success(f"Enriched {saved} sellers. Errors: {errors}. Tokens left: {left}.")
        if stopped:
            st.warning(stopped + " Remaining sellers stay pending — run again after tokens refill.")
    finally:
        api.close()

st.subheader("3. Qualified sellers")
qualified = db.rows()
incomplete = db.rows(incomplete=True)
st.metric("Verified US sellers with 0–49 feedback", len(qualified))
st.caption("Only sellers whose Amazon business address is in the United States are listed.")
def render_table(rows, cols):
    # Plain HTML table: st.dataframe needs pyarrow, whose DLL is blocked by Windows Application Control here.
    def cell(key, value):
        if value in (None, ""):
            return "<td>—</td>"
        text = html.escape(str(value))
        if key == "profile_url":
            return f'<td><a href="{text}" target="_blank">Open</a></td>'
        if key == "asin":
            return f'<td><a href="https://www.amazon.com/dp/{text}" target="_blank">{text}</a></td>'
        return f"<td>{text}</td>"
    head = "".join(f"<th>{label}</th>" for label, _ in cols)
    body = "".join("<tr>" + "".join(cell(k, r.get(k)) for _, k in cols) + "</tr>" for r in rows)
    st.markdown(
        "<style>.sellers{width:100%;border-collapse:collapse;font-size:14px}"
        ".sellers th,.sellers td{border:1px solid #444;padding:6px 8px;text-align:left;vertical-align:top}"
        ".sellers th{background:#1F4E78;color:#fff}</style>"
        f'<div style="overflow-x:auto"><table class="sellers"><tr>{head}</tr>{body}</table></div>',
        unsafe_allow_html=True)


if qualified:
    render_table(qualified, [
        ("Seller ID", "seller_id"), ("Seller Name", "seller_name"), ("Feedback", "lifetime_feedback"),
        ("Business Name", "business_name"), ("Address", "business_address"), ("Country", "country"),
        ("Phone", "phone_number"), ("Profile", "profile_url"), ("Status", "verification_status"),
    ])
else:
    st.info("No verified qualifying sellers yet.")

st.subheader("4. Seller active listings & product filter")
st.caption("Cost: ~10 tokens per seller storefront + 1 token per ASIN checked. Products sold by Amazon are rejected.")
unique_brand = st.checkbox("One product per brand overall (skip brands already found by any seller)", value=True)
exact_fba = st.checkbox("Fetch exact FBA seller count (costs +6 extra tokens per ASIN; otherwise uses total offers when FBA is -2)", value=False)
show_debug = st.checkbox("Show debug details (raw Keepa data & filter decisions)", value=True)
if qualified:
    seller_labels = {f"{r.get('seller_name') or r['seller_id']} ({r['seller_id']})": r["seller_id"] for r in qualified}
    chosen = st.multiselect("Select qualified US seller(s)", list(seller_labels),
                            default=list(seller_labels)[:1])
    p1, p2, p3, p4, p5 = st.columns(5)
    max_asins = p1.number_input("Max ASINs per seller", 1, 500, 20)
    min_fba = p2.number_input("Min FBA sellers", 1, 100, 2)
    min_sales = p3.number_input("Min past-month sales", 0, 100000, 50)
    min_price = p4.number_input("Min price ($)", 0.0, 10000.0, 10.0)
    max_price = p5.number_input("Max price ($)", 0.0, 10000.0, 200.0)
    if st.button("Fetch & filter seller products") and chosen:
        api = KeepaClient(cfg.api_key, cfg.domain)
        matched, checked, stopped = [], 0, None
        debug_storefronts, debug_rows = [], []
        try:
            left = api.token_status().get("tokensLeft", 0)
            seen_brands = db.existing_brands() if unique_brand else set()
            for label in chosen:
                sid = seller_labels[label]
                if left < 10:
                    stopped = f"Stopped before {sid}: only {left} tokens left (storefront needs 10)."
                    break
                sf = api.seller_storefront(sid)
                left = sf.get("tokensLeft", left - 10)
                seller_obj = (sf.get("sellers") or {}).get(sid) or {}
                raw_asins = list(dict.fromkeys(seller_obj.get("asinList") or []))
                asins = raw_asins[:int(max_asins)]
                logger.info("Storefront %s: total asinList=%d, checking=%d, sample=%s",
                            sid, len(raw_asins), len(asins), asins[:5])
                debug_storefronts.append({
                    "seller_id": sid,
                    "total_asins_in_keepa": len(raw_asins),
                    "asins_checked": len(asins),
                    "asin_sample": ", ".join(asins[:10]) or "None",
                })
                seller_matches = []
                for i in range(0, len(asins), 100):
                    batch = asins[i:i + 100]
                    cost_per_asin = 7 if exact_fba else 1
                    if left < cost_per_asin:
                        stopped = f"Stopped during {sid}: out of tokens ({left} left, needs {cost_per_asin}/ASIN)."
                        break
                    max_batch = left // cost_per_asin
                    if len(batch) > max_batch:
                        batch = batch[:max_batch]
                    resp = api.products(batch, offers=20 if exact_fba else None)
                    left = resp.get("tokensLeft", left - len(batch))
                    checked += len(batch)
                    for prod in resp.get("products") or []:
                        row = extract_product(prod, sid)
                        reason = filter_reason(row, int(min_fba), int(min_sales), float(min_price), float(max_price))
                        if row["asin"] and reason is None:
                            seller_matches.append(row)
                            decision = "PASS"
                        else:
                            decision = reason or "Skipped: missing ASIN"
                        row_dbg = dict(row)
                        row_dbg["sold_by_amazon"] = "Yes" if row["sold_by_amazon"] else "No"
                        row_dbg["availabilityAmazon"] = prod.get("availabilityAmazon")
                        row_dbg["decision"] = decision
                        debug_rows.append(row_dbg)
                        logger.info("Product %s (%s): brand=%s fba=%s sales=%s price=%s amz=%s -> %s",
                                    row["asin"], sid, row["brand"], row["fba_sellers"],
                                    row["monthly_sold"], row["price"], row_dbg["sold_by_amazon"], decision)
                    if len(batch) < len(asins[i:i + 100]):
                        stopped = f"Stopped during {sid}: tokens ran low ({left} left)."
                        break
                if unique_brand:
                    kept = dedupe_brands(seller_matches, seen_brands)
                    kept_asins = {r["asin"] for r in kept}
                    for r_dbg in debug_rows:
                        if r_dbg["seller_id"] == sid and r_dbg["decision"] == "PASS" and r_dbg["asin"] not in kept_asins:
                            r_dbg["decision"] = "Skipped: duplicate brand"
                    seller_matches = kept
                    seen_brands.update((r["brand"] or "").strip().lower() for r in seller_matches if r.get("brand"))
                db.save_products(seller_matches)
                matched.extend(seller_matches)
                if stopped:
                    break
            st.success(f"Checked {checked} ASINs · saved {len(matched)} matching products · tokens left: {left}.")
            if stopped:
                st.warning(stopped)
            if show_debug:
                with st.expander("Debug: Storefront & Product Filter Details", expanded=True):
                    if debug_storefronts:
                        st.markdown("**Storefront responses**")
                        render_table(debug_storefronts, [
                            ("Seller ID", "seller_id"), ("Keepa asinList Total", "total_asins_in_keepa"),
                            ("ASINs Checked", "asins_checked"), ("First 10 ASINs", "asin_sample"),
                        ])
                    if debug_rows:
                        st.markdown("**Every checked ASIN & filter decision**")
                        render_table(debug_rows, [
                            ("Seller ID", "seller_id"), ("ASIN", "asin"), ("Brand", "brand"),
                            ("Category", "category"), ("Sold by Amazon", "sold_by_amazon"),
                            ("availAmz", "availabilityAmazon"), ("FBA Sellers", "fba_sellers"),
                            ("Total Offers", "total_offers"), ("Monthly Sales", "monthly_sold"),
                            ("Price ($)", "price"), ("Decision", "decision"),
                        ])
                    elif not debug_storefronts:
                        st.info("No storefront data returned.")
        except Exception as exc:
            logger.exception("Product fetch failed")
            st.error(str(exc))
        finally:
            api.close()
else:
    st.info("Qualify at least one US seller in steps 1–2 first.")

products = db.product_rows(unique_brands=unique_brand)
if products:
    render_table(products, [
        ("Seller", "seller_name"), ("ASIN", "asin"), ("Brand Name", "brand"),
        ("Category", "category"), ("Past Month Sales", "monthly_sold"),
        ("FBA Sellers", "fba_sellers"), ("Price ($)", "price"),
    ])

st.subheader("5. Excel export")
if st.button("Generate Excel workbook"):
    path = export(qualified, incomplete, db.counts(), cfg.export_dir, products=products)
    with open(path, "rb") as file:
        st.download_button("Download Excel workbook", file, file_name=path.name,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
