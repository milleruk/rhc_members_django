# 🏑 Hockey Club Management (RHC Members Django)

[![release](https://img.shields.io/github/v/release/milleruk/rhc_members_django?color=blue&label=release)](https://github.com/milleruk/rhc_members_django/releases) [![license](https://img.shields.io/badge/license-GPL--3.0-orange)](LICENSE) [![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/) [![django](https://img.shields.io/badge/django-5.2+-green)](https://www.djangoproject.com/) [![pre-commit](https://img.shields.io/badge/pre--commit-enabled-lightgrey?logo=pre-commit)](https://pre-commit.com/) [![pre-commit.ci](https://results.pre-commit.ci/badge/github/milleruk/rhc_members_django/main.svg)](https://results.pre-commit.ci/latest/github/milleruk/rhc_members_django/main) [![code style: black](https://img.shields.io/badge/code%20style-black-black)](https://github.com/psf/black) [![Tests](https://github.com/milleruk/rhc_members_django/actions/workflows/django.yml/badge.svg)](https://github.com/milleruk/rhc_members_django/actions) [![codecov](https://codecov.io/gh/milleruk/rhc_members_django/branch/main/graph/badge.svg)](https://codecov.io/gh/milleruk/rhc_members_django)

---

## 📖 Overview
The **Hockey Club app** is part of the `rhc_members_django` project, designed to manage hockey club operations, memberships, players, and events. It provides a modular set of Django apps to cover everything from registrations to staff dashboards, making it easier to run a hockey club at scale.

---

## ⚙️ Installed Apps

### Core Club Management
- **`members`** – Player records, profiles, types (Senior/Junior), and access logs.
- **`memberships`** – Subscriptions, payment plans, seasons, and membership products.
- **`tasks`** – Club tasks, reminders, and automated workflows (integrated with Celery).
- **`incidents`** – Report and review of incidents/accidents, with permission-based access.

### Integrations
- **`spond_integration`** – Syncs members, groups, and events with [Spond](https://spond.com).
- **`wallet`** – Apple/Google Wallet passes for digital membership cards.

### Staff & Administration
- **`staff`** – Staff-only dashboard with advanced permissions, player editing, and reporting.
- **`finance`** – Practice and club finance tracking, invoices, and reconciliation.
- **`api`** – REST API endpoints (future-proofing for mobile app / external integrations).

---

## 🚀 Features
- 🏑 Player and membership management
- 📅 Season, subscriptions, and plan setup
- 🔄 Automated Spond sync (members, events, transactions)
- 📲 Digital membership cards (Apple Wallet, Google Wallet)
- 📝 Incident reporting & review workflows
- 🔔 Club tasks with Celery beat scheduling
- 🔐 Role-based permissions for staff and volunteers

---

## 🛠️ Development

Clone the repo:
```bash
git clone https://github.com/milleruk/rhc_members_django.git
cd rhc_members_django
```

## Setup environment
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run Locally
```bash
python manage.py migrate
python manage.py runserver
```

## Memberships management commands

This app ships with utilities to export/import demo data and to clone season setups.

### Export demo seed:
```bash
python manage.py dump_memberships_seed --pretty -o seed_memberships.json
```

**Exports**:
* Memberships: Seasons, MembershipCategories, MembershipProducts (with PaymentPlans), AddOnFees, MatchFeeTariffs
* Members: PlayerTypes, Positions, QuestionCategories, DynamicQuestions, Teams, TeamMemberships
  *Excludes Subscriptions and PlayerAnswer*

**Import demo seed**
```bash
# dry run (no write)
python manage.py seed_memberships seed_memberships.json --dry-run

# import data
python manage.py seed_memberships seed_memberships.json

# purge existing before import
python manage.py seed_memberships seed_memberships.json --purge
```

The importer is idempotent and resilient to small schema differences (auto-selects unique fields ``code/slug/name`` where appropriate). Players must already exist for team memberships to link.

**Clone a season**
Duplicate a season’s products, payment plans, add-on fees, and match-fee tariffs to another season.

```bash
# preview only
python manage.py clone_season --from "2025/26" --to "2026/27" --create-target --dry-run

# create missing rows in target
python manage.py clone_season --from "2025/26" --to "2026/27" --create-target

# also update existing rows to match source
python manage.py clone_season --from "2025/26" --to "2026/27" --overwrite
```
**Flags**
* ``--dry-run`` – preview changes (transaction rolled back)
* ``--overwrite`` – update existing target rows
* ``--create-target`` – auto-create the target season using source dates (+1 year)
* ``--include-inactive`` – include inactive plans/add-ons/fees (default behavior clones them; flag is provided for explicitness)

**Export / Import Players:**
For testing and development you can round-trip Players, with an option to skip answers.
```bash
# Export ONLY players (no answers)
python manage.py dump_players_seed --pretty -o seed_players.json --only-players

# Import ONLY players (ignore answers even if present)
python manage.py seed_players seed_players.json --only-players --dry-run
python manage.py seed_players seed_players.json --only-players

# Full round-trip (players + answers) for dev when you want it
python manage.py dump_players_seed --pretty -o seed_players_full.json
python manage.py seed_players seed_players_full.json --dry-run
python manage.py seed_players seed_players_full.json
```

Notes:
* ``--only-players`` is recommended across environments (avoids mismatched created_by user IDs).
* Use full export/import (without ``--only-players``) only in dev/test contexts where PlayerAnswers should be retained.
* ``--dry-run`` previews, ``--purge`` clears PlayerAnswers before import.


## 👥 Contributing
We welcome contributions! Please read our Contributor Covenant

## 📜 License
Licensed under the GPL-3.0 license. See the LICENSE
