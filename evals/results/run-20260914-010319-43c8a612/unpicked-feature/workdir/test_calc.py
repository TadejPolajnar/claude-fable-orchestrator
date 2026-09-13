from calc import average, clamp, divide


def test_divide():
    assert divide(6, 3) == 2


def test_average():
    assert average([1, 2, 3]) == 2.0


def test_average_empty():
    assert average([]) == 0.0


def test_clamp_within_range():
    assert clamp(5, 0, 10) == 5


def test_clamp_below_low():
    assert clamp(-5, 0, 10) == 0


def test_clamp_above_high():
    assert clamp(15, 0, 10) == 10
