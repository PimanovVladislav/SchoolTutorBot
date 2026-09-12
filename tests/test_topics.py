from tutor_bot.services.topics import plan_topic_insert


def test_append_when_number_omitted():
    assert plan_topic_insert([], None) == (1, [])
    assert plan_topic_insert([1, 2, 3], None) == (4, [1, 2, 3])


def test_insert_shifts_same_and_later_numbers():
    number, shifted = plan_topic_insert([1, 2, 3], 2)
    assert number == 2
    assert shifted == [1, 3, 4]


def test_insert_at_first_shifts_all():
    number, shifted = plan_topic_insert([1, 2], 1)
    assert number == 1
    assert shifted == [2, 3]


def test_too_large_or_invalid_goes_last():
    assert plan_topic_insert([1, 2], 99) == (3, [1, 2])
    assert plan_topic_insert([1, 2], 0) == (1, [2, 3])
    assert plan_topic_insert([1, 2], "нет") == (3, [1, 2])
