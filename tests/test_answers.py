from tutor_bot.services.answers import check_answer


def test_fraction_equivalence():
    assert check_answer("fraction", "3/4", "6/8")
    assert check_answer("fraction", "1/2", "0.5")
    assert check_answer("number", "1", "1.0")


def test_numbers_order_independent():
    assert check_answer("numbers", "2;3", "3 и 2")
    assert check_answer("numbers", "-2;5", "5; -2")
    assert not check_answer("numbers", "2;3", "2")


def test_negative_and_text():
    assert check_answer("number", "-3", "-3")
    assert check_answer("text", "нет корней", "Нет корней")
    assert not check_answer("number", "4", "5")
