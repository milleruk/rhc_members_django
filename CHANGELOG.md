# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

<!--
GitHub MD Syntax:
https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax

Highlighting:
https://docs.github.com/assets/cb-41128/mw-1440/images/help/writing/alerts-rendered.webp

> [!NOTE]
> Highlights information that users should take into account, even when skimming.

> [!IMPORTANT]
> Crucial information necessary for users to succeed.

> [!WARNING]
> Critical content demanding immediate user attention due to potential risks.
-->

## [In Development] - Unreleased


<!--

Unrelease notes

Adds a clean accent palette (easy to tweak via CSS variables).

Colourful tab pills, headers, chips, and boolean pills.

No item counts in group headers (as requested).

Chevron aligned right, collapses on mobile, expands on md+.

Keeps all your existing logic/permissions.

-->

## [0.3.0-beta] - 2025-09-05

### Added
- **New nav and sidebar indicators:**
  - Grey (secondary) badge for players without a current subscription in the active season
  - Blue (primary) badge for players with active subscriptions but no Spond link
  - Both include detailed dropdowns in the navbar and badge counts in the sidebar
- Expanded Membership Overview menu item to show missing subscription badge

### Changed
- Updated login and signup pages with redesigned layout, improved provider buttons, and clearer links
- Switched admin interface theme to **Django JET** for modernized UI
- Standardized dropdown width (`dropdown-menu-xl`) and improved readability in task/incident/subscription dropdowns

### Fixed
- Sidebar badge classes updated (`right badge`) for correct alignment



## [0.2.0-beta] - 2025-09-05

### Changed
- Sidebar navigation re-ordered for better usability:
  - General (Dashboard, Add Player, My Subscriptions, My Tasks)
  - Staff Tools (Staff Dashboard, Manage Players, Membership Overview, Manage Subscriptions, Incidents, Task management)
  - External (Spond Players, Spond Events)
  - Resources (Club Policies, Club Documents, Useful Links)
  - Administration (Site Admin)
- Renamed several menu items for clarity:
  - "All Subscriptions" → "Manage Subscriptions"
  - "Player List" → "Manage Players"
  - "Memberships" → "Membership Overview"
  - "My Memberships" → "My Subscriptions"
- Unified badge styles and colours across nav + sidebar:
  - Tasks = Yellow (warning)
  - Incidents = Red (danger)
  - Pending Subscriptions = Blue (info)


## [0.1.0-beta] - 2025-09-04

### Highlights
- 🎉 First **beta release** — feature-complete and considered ready for wider testing.
- All core modules (members, memberships, tasks, incidents, staff) are functional and integrated.
- Permissions and MFA checks in place for staff-only areas.
- Social login added (GitHub, Google, Instagram; Apple & Facebook marked as in-development).
- Celery beat switched to DatabaseScheduler for runtime schedule updates.
- Membership card generator and Apple Wallet pkpass working end-to-end.

### Improvements
- Player dashboard polished: delete, edit, and add flows fully working.
- Membership and subscription flows tidied for production readiness.
- Staff area has dedicated test suite scaffolding in place.
- UI tweaks: breadcrumbs, quick links, clearer login/signup extras.

### Fixes
- Multiple `NoReverseMatch` and `TemplateSyntaxError` issues resolved.
- Integrity error on task creation fixed, with improved dropdown styling.
- Incident workflow bugs squashed; tasks auto-generate and cascade delete with incidents.

---


## [0.0.9-alpha] - 2025-09-04

### Features
- Incident reporting module with automatic task generation and review workflow.
- Permissions for incidents: access app, submit, assign, complete review, delete, and view sensitive reports.
- MFA enforcement mixin for staff area (`RequireMFAMixin`).
- Social login providers added (GitHub, Google, Facebook, Apple, Instagram) – Facebook and Apple marked as “in development”.
- Extra links added to login and signup pages (Forgot password, Resend confirmation, Register new account).
- Test suite started for `staff` app.
- Developer helper scripts (`dev.sh`, `commit.sh`, `devmenu.sh`) and alias (`rhcdev`).
- **Dashboard KPIs**:
  - Active subscriptions count across all players for the signed-in user.
  - Pending Spond responses count (`status="unknown"` for future events).
- **Player Detail**:
  - Active subscriptions card (visible to all staff who can view the player).
  - Desktop: full-width bar; Mobile: standalone card placed after Answers.
  - Answers shown first on mobile for quick access.

### Fixes
- Player delete button now works correctly from dashboard.
- `NoReverseMatch` errors in tasks view resolved.
- `Player.full_name` attribute error in wallet pkpass generation fixed.
- Integrity error on task creation form fixed, dropdown styling improved.
- TemplateSyntaxError issues in incidents templates resolved.
- Spond pending counter now correctly filters for `status="unknown"` and future events.
- Active subscriptions widget now respects player visibility, not gated to superusers.

### DevOps
- Celery beat switched to DatabaseScheduler for runtime schedule updates.
- GitHub Actions CI updated with linting (flake8, black, isort).
- Dockerfile reduced from ~80 lines to ~40.

### UI/UX
- Player detail and dashboard templates modernised with accent theme, rounded cards, and consistent spacing.
- Membership dashboard cards redesigned with clearer headers and grouped actions.
- Profile answers edit page updated to match theme, with non-collapsible headers.
- Club notices and quick links restored to dashboard sidebar with new styling.
- Imports in views tidied up for readability.
- Mobile tweaks: fixed spacing/overflow issues, improved button group wrapping.


---

## [0.0.8-alpha] - 2025-09-02

### Features
- Membership card generator (Apple Wallet pkpass + digital card output).

### UI/UX
- Staff functions moved into a dedicated `staff` app for tidier separation.
- Player views in `members` app updated for more user-friendly experience.

---

## [0.0.7-alpha] - 2025-09-01

### Features
- Task module implemented with reminders.
- Celery workers and beat schedule created for automated emails.

### UI/UX
- Navigation templates and menus reworked.
- Breadcrumbs and version numbers added to templates.

### DevOps
- Main `urls.py` restructured.

---

## [0.0.6-alpha] - 2025-08-31

### Features
- Captains’ team view fixed with new M2M team membership model.

### DevOps
- Settings moved to `.env` files.
- Restricted Spond link visibility to full admins.

---

## [0.0.5-alpha] - 2025-08-30

### Features
- Spond transactions integration.

---

## [0.0.4-alpha] - 2025-08-29

### Features
- Spond events sync (shows events and players on dashboard).

### UI/UX
- Membership model updated.
- Membership forms updated to group dynamic questions by category and display order.

---

## [0.0.3-alpha] - 2025-08-28

### Features
- Initial Spond events sync.

### UI/UX
- Locked down team assignment so only certain roles can edit and assign.

---

## [0.0.2-alpha] - 2025-08-28

### Features
- Team view filter (with unassigned list).
- Initial Spond integration.

### UI/UX
- Locked down team assignment so only certain roles can edit and assign.

---

## [0.0.1-alpha] - 2025-08-27

### Features
- First release for alpha testing.
