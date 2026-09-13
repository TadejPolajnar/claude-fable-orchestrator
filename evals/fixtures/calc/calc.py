def divide(a, b):
    return a / b


def average(numbers):
    total = 0
    for n in numbers:
        total += n
    return divide(total, len(numbers))
