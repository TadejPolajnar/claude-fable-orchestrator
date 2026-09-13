from catalog import price_of
from pricing import apply_discount


class Cart:
    def __init__(self):
        self._lines = {}

    def add(self, sku, quantity=1):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        price_of(sku)
        self._lines[sku] = self._lines.get(sku, 0) + quantity

    def remove(self, sku):
        self._lines.pop(sku, None)

    def line_count(self):
        return len(self._lines)

    def total_cents(self):
        total = 0
        for sku, quantity in self._lines.items():
            total += apply_discount(price_of(sku), quantity)
        return total
