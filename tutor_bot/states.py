from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    grade = State()


class Learn(StatesGroup):
    waiting_answer = State()
