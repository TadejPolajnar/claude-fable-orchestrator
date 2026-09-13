def divide(a, b):
    return a / b


def average(numbers):
    if not numbers:
        return 0.0
    total = 0
    for n in numbers:
        total += n
    return divide(total, len(numbers))
