from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_middle_name = State()
    waiting_for_birth_date = State()
    waiting_for_weight = State()

class AdminStates(StatesGroup):
    waiting_for_edit_first_name = State()
    waiting_for_edit_last_name = State()
    waiting_for_edit_middle_name = State()
    waiting_for_edit_birth_date = State()
    waiting_for_edit_weight = State()

class UserProfileStates(StatesGroup):
    waiting_for_edit_first_name = State()
    waiting_for_edit_last_name = State()
    waiting_for_edit_middle_name = State()
    waiting_for_edit_birth_date = State()
    waiting_for_edit_weight = State()

class  WorkoutStates(StatesGroup):
    waiting_for_workout_link = State()
