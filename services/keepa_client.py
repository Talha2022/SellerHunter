import httpx

class KeepaClient:
    BASE = "https://api.keepa.com"

    def __init__(self, key, domain=1):
        self.key = key
        self.domain = domain
        self.http = httpx.Client(timeout=60, headers={"User-Agent": "SellerResearchTool/1.0"})

    def close(self):
        self.http.close()

    def request(self, method, endpoint, params=None, body=None):
        query = {"key": self.key, "domain": self.domain}
        if params:
            query.update(params)
        response = self.http.request(method, f"{self.BASE}/{endpoint}", params=query, json=body)
        try:
            result = response.json()
        except ValueError:
            result = {}
        if response.status_code == 429:
            raise RuntimeError(
                f"Not enough Keepa tokens (tokens left: {result.get('tokensLeft', '?')}, "
                f"refill rate: {result.get('refillRate', '?')}/min). Wait and retry.")
        error = result.get("error")
        if error:
            message = error.get("message", error) if isinstance(error, dict) else error
            raise RuntimeError(f"Keepa error ({response.status_code}): {message}")
        response.raise_for_status()
        return result

    def token_status(self):
        # Free call: current token balance
        return self.http.get(f"{self.BASE}/token", params={"key": self.key}).json()

    def seller_finder(self, selection):
        return self.request("POST", "sellerquery", body=selection)

    def seller_information(self, ids):
        if len(ids) > 100:
            raise ValueError("Seller Information batches must be at most 100 IDs.")
        return self.request("GET", "seller", params={"seller": ",".join(map(str, ids))})

    def seller_storefront(self, seller_id):
        # Storefront ASIN list requires a single seller ID and costs ~10 tokens when available
        return self.request("GET", "seller", params={"seller": str(seller_id), "storefront": 1})

    def products(self, asins, offers=None):
        if len(asins) > 100:
            raise ValueError("Product batches must be at most 100 ASINs.")
        params = {"asin": ",".join(map(str, asins)), "stats": 1}
        if offers:
            params["offers"] = int(offers)
        return self.request("GET", "product", params=params)
