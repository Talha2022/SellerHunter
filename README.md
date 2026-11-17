# Amazon US Low-Feedback Seller Finder

Python + Streamlit starter using Keepa Seller Finder and Seller Information.

## Limitations
- Covers Keepa-indexed sellers, not a guaranteed census of every Amazon US seller.
- Missing feedback counts are unverified, never assumed to be zero.
- Qualification is strictly 0–49 verified lifetime seller feedback ratings.
- Business name, address, and phone are included only when returned by the provider. Email collection is not implemented.
- Verify current Keepa request parameters, pagination, token costs, and terms before a full run.

## Windows setup
1. Install Python 3.12+.
2. In this directory run:
   `py -3.12 -m venv .venv`
   `.venv\Scripts\activate`
   `python -m pip install --upgrade pip`
   `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and add your Keepa API key.
4. Run `streamlit run app.py`.

Start with a small test. The included discovery code fetches only the first Seller Finder page; full pagination/segmentation must be implemented and validated before claiming exhaustive category coverage.

Docs: https://keepa.com/#!api
https://keepa.com/api-docs/seller-finder.html
https://keepa.com/api-docs/seller-object.html
