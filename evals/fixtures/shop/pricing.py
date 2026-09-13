DISCOUNT_TIERS = [
    (10, 0.15),
    (5, 0.10),
    (3, 0.05),
]


def discount_rate(quantity):
    for threshold, rate in DISCOUNT_TIERS:
        if quantity >= threshold:
            return rate
    return 0.0


def apply_discount(unit_price_cents, quantity):
    rate = discount_rate(quantity)
    discounted_cents = round(unit_price_cents * (1 - rate))
    return discounted_cents * quantity
