from stats import median, pstdev


def test_median_odd():
    assert median([3, 1, 2]) == 2


def test_median_even():
    assert median([4, 1, 3, 2]) == 2.5


def test_median_empty():
    assert median([]) == 0.0


def test_pstdev():
    assert pstdev([2, 4, 4, 4, 5, 5, 7, 9]) == 2.0


def test_pstdev_empty():
    assert pstdev([]) == 0.0


def test_median_duplicates():
    assert median([2, 2, 2, 3]) == 2.0


def test_median_negative():
    assert median([-5, -1, -3]) == -3


def test_median_single():
    assert median([5]) == 5


def test_pstdev_identical():
    assert pstdev([7, 7, 7]) == 0.0


def test_pstdev_single():
    assert pstdev([5]) == 0.0
