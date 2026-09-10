from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    grade = State()


class Learn(StatesGroup):
    waiting_answer = State()


class Admin(StatesGroup):
    subject_title = State()
    grade_number = State()
    topic_title = State()
    topic_summary = State()
    topic_theory = State()
    topic_assessment = State()
    problem_prompt = State()
    problem_answer = State()
    problem_hint = State()
    problem_solution = State()
    extra_theory = State()
    extra_hint = State()
    extra_solution = State()
    grant_target = State()
    grant_days = State()
