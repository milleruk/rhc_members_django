#!/usr/bin/env bash
set -eu

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

while true; do
  clear
  echo "=== RHC_members Dev Menu ==="
  echo "1) Run commit script"
  echo "2) Run dev environment (tmux: Django + Celery)"
  echo "3) Stop dev environment"
  echo "4) Run tests"
  echo "5) Make & apply migrations"
  echo "6) Open Django shell"
  echo "7) Collect static files"
  echo "8) Exit"
  echo
  read -rp "Choose an option: " choice

  case "$choice" in
    1)
      "$PROJECT_DIR/scripts/commit.sh"
      ;;
    2)
      "$PROJECT_DIR/scripts/dev.sh"
      ;;
    3)
      tmux kill-session -t rhcdev 2>/dev/null || echo "No dev session running."
      ;;
    4)
      source "$PROJECT_DIR/venv/bin/activate"
      cd "$PROJECT_DIR"
      python manage.py test
      ;;
    5)
      source "$PROJECT_DIR/venv/bin/activate"
      cd "$PROJECT_DIR"
      python manage.py makemigrations
      python manage.py migrate
      ;;
    6)
      source "$PROJECT_DIR/venv/bin/activate"
      cd "$PROJECT_DIR"
      python manage.py shell
      ;;
    7)
      source "$PROJECT_DIR/venv/bin/activate"
      cd "$PROJECT_DIR"
      python manage.py collectstatic --noinput
      ;;
    8)
      echo "Goodbye 👋"
      exit 0
      ;;
    *)
      echo "Invalid choice."
      sleep 1
      ;;
  esac
done
