from service import BuyerService

_service = None


def service():
    global _service
    if _service is None:
        _service = BuyerService(backend="neural", rerank=True)
    return _service


def get_product_details(product_id):
    return service().details(product_id)


def search_products(requirement):
    return service().search(requirement)
