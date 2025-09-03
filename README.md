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

## 👥 Contributing
We welcome contributions! Please read our Contributor Covenant

## 📜 License
Licensed under the GPL-3.0 license. See the LICENSE
