# members/some_logic.py (where you already know it's complete)
from tasks.events import emit


def on_player_profile_completed(player, actor=None):
    emit("profile.completed", subject=player, actor=actor)
