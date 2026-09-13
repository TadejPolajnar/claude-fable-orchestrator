import math

from calc import average


def median(numbers):
    if not numbers:
        return 0.0
    ordered = sorted(numbers)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return average([ordered[middle - 1], ordered[middle]])


def pstdev(numbers):
    if not numbers:
        return 0.0
    mean = average(numbers)
    squared = [(n - mean) ** 2 for n in numbers]
    return math.sqrt(average(squared))
