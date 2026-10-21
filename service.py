"""Search and product lookup, with explicit handling of unknown attributes."""

import math
import re
from catalog import DEMO_PATH, build_product_text, load_products


def terms(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    return set(words + [part[i:i + 2] for part in chinese
                        for i in range(max(1, len(part) - 1))])


def field(product, key):
    if product.get(key) is not None:
        return product[key]
    for name, value in product.get("details", {}).items():
        if name.casefold() == key.casefold():
            return value
    return None


def matches(product, filters):
    for key, expected in filters.items():
        if expected is None:
            continue
        if key in ("max_price", "max_height_cm"):
            value = product.get("price" if key == "max_price" else "height_cm")

            if key == "max_price" and product.get("price_basis") != "per_item":
                return False
            try:
                amount = float(value)
                if not math.isfinite(amount) or amount < 0 or amount > expected:
                    return False
            except (TypeError, ValueError):
                return False
        elif str(field(product, key) or "").casefold() != str(expected).casefold():
            return False
    return True


def validate_filters(filters):
    allowed = {"color", "form", "currency", "max_price", "max_height_cm"}
    if filters.keys() - allowed:
        raise ValueError("Unsupported filter.")
    for key in ("max_price", "max_height_cm"):
        value = filters.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or value < 0):
            raise ValueError(f"{key} must be a finite, non-negative number.")
    if filters.get("max_price") is not None and not filters.get("currency"):
        raise ValueError("A price limit requires --currency; currencies are not converted.")


class BuyerService:
    def __init__(self, catalog_path=None, demo=False, backend="lexical", rerank=False):
        if backend not in ("lexical", "neural"):
            raise ValueError("Unknown search backend.")
        self.products = load_products(catalog_path or (DEMO_PATH if demo else None))
        self.backend = backend
        self.use_reranker = rerank
        self._retriever = None
        self._reranker = None

    def details(self, product_id):
        for product in self.products:
            if product["parent_asin"] == product_id:
                return {"found": True, **self.present(product)}
        return {"found": False, "product_id": product_id, "message": "Product not found."}

    @staticmethod
    def present(product):
        synthetic = product.get("source") == "synthetic_demo"
        return {
            "product_id": product["parent_asin"], "title": product["title"],
            "features": product.get("features") or [],
            "description": product.get("description") or [],
            "details": product.get("details") or {},
            "source": "synthetic_demo" if synthetic else "catalogue",
            "price": product.get("price"),
            "currency": product.get("currency") if synthetic else "USD",
            "price_note": "Synthetic GBP per-item price; not a supplier quote." if synthetic else
                          "Historical USD catalogue price; pack size may vary. Not a current or per-item quote.",
        }

    def search(self, requirement, top_k=3, **filters):
        if not isinstance(requirement, str) or not requirement.strip():
            raise ValueError("Search requirement cannot be empty.")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k must be a positive integer.")
        validate_filters(filters)
        eligible = [p for p in self.products if matches(p, filters)]
        if not eligible:
            return []
        if self.backend == "neural":
            from retrieve import ProductRetriever
            if self._retriever is None:
                self._retriever = ProductRetriever(products=self.products)
            ids = {p["parent_asin"] for p in eligible}
            candidates = [item for item in self._retriever.retrieve(requirement, len(self.products))
                          if item["product"]["parent_asin"] in ids][:max(20, top_k)]
        else:
            query = terms(requirement)
            candidates = []
            for product in eligible:
                tokens = terms(build_product_text(product))
                score = len(query & tokens) / max(1, len(query | tokens))
                if score:
                    candidates.append({"product": product, "retrieval_score": score})
            candidates.sort(key=lambda item: (-item["retrieval_score"], item["product"]["parent_asin"]))
        if self.use_reranker and candidates:
            from rerank import ProductReranker
            if self._reranker is None:
                self._reranker = ProductReranker()
            candidates = self._reranker.rerank(requirement, candidates[:max(20, top_k)], top_k)
        return [{**self.present(item["product"]), "retrieval_score": item["retrieval_score"],
                 **({"rerank_score": item["rerank_score"]} if "rerank_score" in item else {})}
                for item in candidates[:top_k]]
