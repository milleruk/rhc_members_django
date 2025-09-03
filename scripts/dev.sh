# scripts/dev.sh
#!/usr/bin/env bash
set -eu

SESSION="rhcdev"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_ACTIVATE="$PROJECT_DIR/venv/bin/activate"

tmux has-session -t "$SESSION" 2>/dev/null && tmux kill-session -t "$SESSION" || true

# Pane 0: Django server
tmux new-session -d -s "$SESSION" "bash -lc 'cd \"$PROJECT_DIR\" && source \"$VENV_ACTIVATE\" && exec python manage.py runserver 0.0.0.0:6767'"

# Pane 1: Celery worker
tmux split-window -h "bash -lc 'cd \"$PROJECT_DIR\" && source \"$VENV_ACTIVATE\" && exec celery -A hockey_club.celery:app worker -l info'"

# Pane 2: Celery beat (DB scheduler)
tmux split-window -v -t 0 "bash -lc 'cd \"$PROJECT_DIR\" && source \"$VENV_ACTIVATE\" && exec celery -A hockey_club.celery:app beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler'"

tmux select-layout tiled

# Hook: if client detaches, kill the session immediately
tmux set-hook -t "$SESSION" client-detached "kill-session -t $SESSION"

# Helper message
tmux display-message -t "$SESSION" "Detach with Ctrl+b d — this will KILL the rhcdev session" &

tmux attach -t "$SESSION"
