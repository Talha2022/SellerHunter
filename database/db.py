import sqlite3
from datetime import datetime, timezone

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

# Qualified = verified 0-49 feedback AND business address in the United States
QUALIFIED = "feedback_verified=1 AND lifetime_feedback BETWEEN 0 AND 49 AND country='US'"

class Database:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        schema = (path.parent.parent / "database" / "schema.sql").read_text(encoding="utf-8")
        with self.connect() as c:
            c.executescript(schema)
            cols = {r["name"] for r in c.execute("PRAGMA table_info(sellers)")}
            if "country" not in cols:  # migrate older databases
                c.execute("ALTER TABLE sellers ADD COLUMN country TEXT")
            # Backfill country from the stored address ("..., 92602, US") for rows saved before the column existed
            for r in c.execute("SELECT seller_id, business_address FROM sellers "
                               "WHERE country IS NULL AND business_address IS NOT NULL").fetchall():
                code = r["business_address"].rsplit(",", 1)[-1].strip().upper()
                if len(code) == 2 and code.isalpha():
                    c.execute("UPDATE sellers SET country=?, verification_status=CASE "
                              "WHEN verification_status='qualified' AND ?<>'US' THEN 'non_us' "
                              "ELSE verification_status END WHERE seller_id=?",
                              (code, code, r["seller_id"]))

    def connect(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def add_ids(self, ids):
        unique = list(dict.fromkeys(str(x) for x in ids if x))
        with self.connect() as c:
            before = c.total_changes
            c.executemany("INSERT OR IGNORE INTO sellers(seller_id, discovered_at) VALUES (?,?)",
                          [(x, now()) for x in unique])
            added = c.total_changes - before
        return added, len(unique) - added

    def pending_ids(self):
        with self.connect() as c:
            return [r["seller_id"] for r in c.execute("SELECT seller_id FROM sellers WHERE enriched_at IS NULL")]

    def save_seller(self, s):
        keys = ["seller_id","seller_name","lifetime_feedback","feedback_verified","business_name",
                "business_address","phone_number","profile_url","marketplace","source_provider",
                "discovered_at","enriched_at","verification_status","last_error","country"]
        vals = [s.get(k) for k in keys]
        updates = ",".join(f"{k}=excluded.{k}" for k in keys if k != "seller_id")
        sql = f"INSERT INTO sellers ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)}) ON CONFLICT(seller_id) DO UPDATE SET {updates}"
        with self.connect() as c:
            c.execute(sql, vals)

    def rows(self, incomplete=False):
        sql = f"SELECT * FROM sellers WHERE {QUALIFIED}"
        if incomplete:
            sql += " AND (business_name IS NULL OR business_name='' OR business_address IS NULL OR business_address='' OR phone_number IS NULL OR phone_number='')"
        sql += " ORDER BY lifetime_feedback, seller_name"
        with self.connect() as c:
            return [dict(r) for r in c.execute(sql).fetchall()]

    def counts(self):
        with self.connect() as c:
            total = c.execute("SELECT COUNT(*) FROM sellers").fetchone()[0]
            good = c.execute(f"SELECT COUNT(*) FROM sellers WHERE {QUALIFIED}").fetchone()[0]
            pending = c.execute("SELECT COUNT(*) FROM sellers WHERE enriched_at IS NULL").fetchone()[0]
            non_us = c.execute("SELECT COUNT(*) FROM sellers WHERE enriched_at IS NOT NULL AND (country IS NULL OR country<>'US')").fetchone()[0]
            return {"discovered": total, "qualified": good, "pending": pending, "non_us": non_us}

    def save_products(self, rows):
        if not rows:
            return
        keys = ["seller_id", "asin", "brand", "category", "monthly_sold",
                "fba_sellers", "price", "sold_by_amazon", "fetched_at"]
        sql = f"INSERT OR REPLACE INTO products ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})"
        with self.connect() as c:
            c.executemany(sql, [[r.get(k) for k in keys] for r in rows])

    def existing_brands(self, min_fba=1, min_sales=0, min_price=0.0, max_price=10000.0):
        with self.connect() as c:
            rows = c.execute(
                "SELECT DISTINCT LOWER(TRIM(brand)) AS b FROM products "
                "WHERE sold_by_amazon = 0 AND brand IS NOT NULL AND TRIM(brand) <> '' "
                "AND fba_sellers IS NOT NULL AND fba_sellers >= ? "
                "AND (? <= 0 OR (monthly_sold IS NOT NULL AND monthly_sold >= ?)) "
                "AND price IS NOT NULL AND price BETWEEN ? AND ?",
                (int(min_fba), int(min_sales), int(min_sales), float(min_price), float(max_price)),
            ).fetchall()
            return {r["b"] for r in rows}

    def product_rows(self, unique_brands=True, min_fba=1, min_sales=0, min_price=0.0, max_price=10000.0):
        sql = ("SELECT p.*, s.seller_name FROM products p "
               "LEFT JOIN sellers s ON s.seller_id = p.seller_id "
               "WHERE p.sold_by_amazon = 0 "
               "AND p.fba_sellers IS NOT NULL AND p.fba_sellers >= ? "
               "AND (? <= 0 OR (p.monthly_sold IS NOT NULL AND p.monthly_sold >= ?)) "
               "AND p.price IS NOT NULL AND p.price BETWEEN ? AND ? "
               "ORDER BY p.fetched_at, p.seller_id, p.asin")
        params = (int(min_fba), int(min_sales), int(min_sales), float(min_price), float(max_price))
        with self.connect() as c:
            rows = [dict(r) for r in c.execute(sql, params).fetchall()]
        if not unique_brands:
            return rows
        seen, kept = set(), []
        for r in rows:
            brand = (r.get("brand") or "").strip().lower()
            if brand:
                if brand in seen:
                    continue
                seen.add(brand)
            kept.append(r)
        return kept
