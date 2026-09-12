from tutor_bot.keyboards import (
    fit_button_text,
    learn_status_note,
    parse_exam_task_button,
    topics_catalog_html,
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


def _inline_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_reply_menu_has_back_and_home():
    from tutor_bot.keyboards import BTN_BACK, BTN_HOME, exam_reply_keyboard, main_menu

    texts = [button.text for row in main_menu().keyboard for button in row]
    assert BTN_BACK in texts
    assert BTN_HOME in texts
    answers = [
        type("Row", (), {"sort_order": 1, "submitted": None})(),
    ]
    exam_texts = [
        button.text
        for row in exam_reply_keyboard(answers).keyboard
        for button in row
    ]
    assert BTN_BACK in exam_texts
    assert BTN_HOME in exam_texts


def test_inline_screens_have_no_back_home():
    from types import SimpleNamespace

    from tutor_bot.keyboards import (
        BTN_BACK,
        BTN_HOME,
        exam_result_keyboard,
        exam_start_keyboard,
        learn_start_keyboard,
        settings_keyboard,
        theory_keyboard,
    )

    answers = [
        SimpleNamespace(sort_order=1, is_correct=True, submitted="1"),
    ]
    markups = [
        theory_keyboard(),
        learn_start_keyboard(1, 1),
        exam_start_keyboard(1),
        settings_keyboard(),
        exam_result_keyboard(1, answers),
    ]
    for markup in markups:
        texts = _inline_texts(markup)
        assert BTN_BACK not in texts
        assert BTN_HOME not in texts
