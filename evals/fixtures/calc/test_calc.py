from calc import average, divide


def test_divide():
    assert divide(6, 3) == 2


def test_average():
    assert average([1, 2, 3]) == 2.0


def test_average_empty():
    assert average([]) == 0.0
