from tutor_bot.services.grades import (
    assessment_size,
    better_grade,
    exam_rules_text,
    grade_bands,
    is_passed,
    pass_minimum,
    score_to_grade,
)


def test_bands_for_ten_tasks():
    assert assessment_size(10, 10) == 10
    assert pass_minimum(10) == 5
    assert grade_bands(10) == {
        "3": (5, 6),
        "4": (7, 8),
        "5": (9, 10),
    }


def test_score_to_grade():
    assert score_to_grade(4, 10) == "не сдано"
    assert score_to_grade(5, 10) == "3"
    assert score_to_grade(6, 10) == "3"
    assert score_to_grade(7, 10) == "4"
    assert score_to_grade(8, 10) == "4"
    assert score_to_grade(9, 10) == "5"
    assert score_to_grade(10, 10) == "5"
    assert score_to_grade(10, 10, max_streak=2) == "5"
    assert score_to_grade(10, 10, max_streak=3) == "5+"


def test_pass_and_best():
    assert is_passed("3")
    assert is_passed("5+")
    assert not is_passed("не сдано")
    assert not is_passed(None)
    assert better_grade("3", "5") == "5"
    assert better_grade("5+", "5") == "5+"


def test_exam_rules_text_example():
    text = exam_rules_text("Сложение обыкновенных дробей", 10, 24)
    assert 'Проверочная работа по теме «Сложение обыкновенных дробей»' in text
    assert "Работа состоит из 10 заданий" in text
    assert "Время на выполнение: 1 день" in text
    assert "как минимум 5 заданий" in text
    assert 'Оценка «3»: 5–6 верных ответов' in text
    assert 'Оценка «4»: 7–8 верных ответов' in text
    assert 'Оценка «5»: 9–10 верных ответов' in text
    assert "трижды на максимальный балл" in text


def test_assessment_size_caps_by_available():
    assert assessment_size(10, 4) == 4
    assert assessment_size(None, 7) == 7
    assert assessment_size(10, 0) == 0
