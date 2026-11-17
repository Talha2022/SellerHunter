import html
import streamlit as st
from config import get_settings
from database.db import Database
from services.keepa_client import KeepaClient
from services.seller_discovery import discover, SORTS
from services.seller_enrichment import normalize
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
d1, d2, d3 = st.columns(3)
sample = d1.number_input("Seller IDs to store", 1, 10000, 100)
min_rating = d2.number_input("Min feedback (0 = brand-new sellers)", 0, 49, 0)
max_rating = d3.number_input("Max feedback", 0, 49, 49)
sort = st.selectbox("Order", list(SORTS))
us_only = st.checkbox("US business address only (addressCountry = US)", value=True)
if st.button("Discover seller IDs", type="primary"):
    api = KeepaClient(cfg.api_key, cfg.domain)
    try:
        with st.spinner("Querying Keepa Seller Finder..."):
            ids, total = discover(api, int(sample), int(min_rating), int(max_rating), sort, us_only=us_only)
            db.add_ids(ids[:int(sample)])
        st.success(f"Stored {len(ids[:int(sample)])} IDs. Provider-reported total: {total}.")
        st.info("This starter retrieves page 0 only. Validate pagination and category coverage before a full run.")
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
if qualified:
    # Plain HTML table: st.dataframe needs pyarrow, whose DLL is blocked by Windows Application Control here.
    cols = [("Seller ID", "seller_id"), ("Seller Name", "seller_name"), ("Feedback", "lifetime_feedback"),
            ("Business Name", "business_name"), ("Address", "business_address"), ("Country", "country"),
            ("Phone", "phone_number"), ("Profile", "profile_url"), ("Status", "verification_status")]
    def cell(key, value):
        if value in (None, ""):
            return "<td>—</td>"
        text = html.escape(str(value))
        if key == "profile_url":
            return f'<td><a href="{text}" target="_blank">Open</a></td>'
        return f"<td>{text}</td>"
    head = "".join(f"<th>{label}</th>" for label, _ in cols)
    body = "".join("<tr>" + "".join(cell(k, r.get(k)) for _, k in cols) + "</tr>" for r in qualified)
    st.markdown(
        "<style>.sellers{width:100%;border-collapse:collapse;font-size:14px}"
        ".sellers th,.sellers td{border:1px solid #444;padding:6px 8px;text-align:left;vertical-align:top}"
        ".sellers th{background:#1F4E78;color:#fff}</style>"
        f'<div style="overflow-x:auto"><table class="sellers"><tr>{head}</tr>{body}</table></div>',
        unsafe_allow_html=True)
else:
    st.info("No verified qualifying sellers yet.")

st.subheader("4. Excel export")
if st.button("Generate Excel workbook"):
    path = export(qualified, incomplete, db.counts(), cfg.export_dir)
    with open(path, "rb") as file:
        st.download_button("Download Excel workbook", file, file_name=path.name,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
