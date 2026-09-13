ITEMS = [
    {"sku": "SKU-001", "name": "Widget", "price_cents": 999},
    {"sku": "SKU-002", "name": "Gadget", "price_cents": 2499},
    {"sku": "SKU-003", "name": "Cable", "price_cents": 499},
    {"sku": "SKU-004", "name": "Stand", "price_cents": 1499},
]


def list_items():
    return list(ITEMS)


def find_item(sku):
    for item in ITEMS:
        if item["sku"] == sku:
            return item
    return None


def price_of(sku):
    item = find_item(sku)
    if item is None:
        raise KeyError(sku)
    return item["price_cents"]
