from types import SimpleNamespace

from tutor_bot.keyboards import (
    BTN_BACK,
    BTN_CONTINUE,
    BTN_EXAM_START,
    BTN_HOME,
    BTN_PROGRESS,
    BTN_SETTINGS,
    exam_reply_keyboard,
    exam_result_reply_keyboard,
    exam_start_reply_keyboard,
    fit_button_text,
    learn_reply_keyboard,
    learn_status_note,
    main_menu,
    parse_exam_result_button,
    parse_exam_task_button,
    parse_start_from_button,
    section_keyboard,
    settings_reply_keyboard,
    theory_reply_keyboard,
    topics_catalog_html,
    training_reply_keyboard,
)


def test_catalog_keeps_full_title():
    title = "Вычитание смешанных чисел с разными знаменателями"
    html = topics_catalog_html([(3, title, "ещё не начата")])
    assert title in html
    assert "<b>3.</b>" in html
    assert "ещё не начата" in html


def test_catalog_escapes_html():
    html = topics_catalog_html([(1, "Тема <опасная> & co", None)])
    assert "<опасная>" not in html
    assert "&lt;опасная&gt;" in html
    assert "&amp;" in html


def test_fit_button_text_respects_limit():
    assert fit_button_text("коротко") == "коротко"
    long = "а" * 80
    assert len(fit_button_text(long)) == 64
    assert fit_button_text(long).endswith("…")


def test_learn_status_note():
    assert learn_status_note(None) == "ещё не начата"
    assert learn_status_note("идёт") == "идёт проверочная"
    assert learn_status_note("5") == "последняя оценка: 5"


def test_parse_exam_task_button():
    assert parse_exam_task_button("1 · Нет ответа") == 1
    assert parse_exam_task_button("12 · ответ отправлен") == 12
    assert parse_exam_task_button("Назад") is None
    assert parse_exam_task_button("3") is None


def test_parse_start_from_button():
    assert parse_start_from_button("Начать с 3") == 3
    assert parse_start_from_button("Назад") is None


def test_parse_exam_result_button():
    assert parse_exam_result_button("1 · верно") == 1
    assert parse_exam_result_button("2 · неверно") == 2
    assert parse_exam_result_button("3 · нет ответа") == 3
    assert parse_exam_result_button("1 · Нет ответа") is None


def _reply_texts(markup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


def test_main_menu_has_home_actions_only():
    texts = _reply_texts(main_menu())
    assert texts == [BTN_CONTINUE, BTN_PROGRESS, BTN_SETTINGS]
    assert BTN_BACK not in texts
    assert BTN_HOME not in texts


def test_section_keyboard_has_back_and_home():
    texts = _reply_texts(section_keyboard([[BTN_EXAM_START]]))
    assert BTN_EXAM_START in texts
    assert BTN_BACK in texts
    assert BTN_HOME in texts
    assert BTN_CONTINUE not in texts


def test_exam_reply_has_nav():
    answers = [
        SimpleNamespace(sort_order=1, submitted=None),
    ]
    texts = _reply_texts(exam_reply_keyboard(answers))
    assert BTN_BACK in texts
    assert BTN_HOME in texts


def test_section_screens_use_reply_actions():
    answers = [
        SimpleNamespace(sort_order=1, is_correct=True, submitted="1"),
    ]
    markups = [
        learn_reply_keyboard(2),
        exam_start_reply_keyboard(),
        settings_reply_keyboard(),
        theory_reply_keyboard(),
        training_reply_keyboard(can_level_up=True, can_level_down=True),
        exam_result_reply_keyboard(answers),
    ]
    for markup in markups:
        texts = _reply_texts(markup)
        assert BTN_BACK in texts
        assert BTN_HOME in texts
        assert BTN_CONTINUE not in texts
