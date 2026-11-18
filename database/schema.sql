CREATE TABLE IF NOT EXISTS sellers (
 seller_id TEXT PRIMARY KEY, seller_name TEXT, lifetime_feedback INTEGER,
 feedback_verified INTEGER NOT NULL DEFAULT 0, business_name TEXT,
 business_address TEXT, phone_number TEXT, profile_url TEXT,
 marketplace TEXT DEFAULT 'Amazon.com', source_provider TEXT DEFAULT 'Keepa',
 discovered_at TEXT NOT NULL, enriched_at TEXT, verification_status TEXT DEFAULT 'pending',
 last_error TEXT, country TEXT
);
CREATE TABLE IF NOT EXISTS products (
 seller_id TEXT NOT NULL, asin TEXT NOT NULL, brand TEXT, category TEXT,
 monthly_sold INTEGER, fba_sellers INTEGER, price REAL,
 sold_by_amazon INTEGER NOT NULL DEFAULT 0, fetched_at TEXT NOT NULL,
 PRIMARY KEY (seller_id, asin)
);
