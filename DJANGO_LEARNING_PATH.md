# Python & Django Learning Path

What to learn before, during and after the Django rebuild, and how it lines up with what
companies that run Python backends expect.

Companion files:

- [DJANGO_REBUILD_GUIDE.md](DJANGO_REBUILD_GUIDE.md): what to build
- [POSTGRES_PRACTICE.md](POSTGRES_PRACTICE.md): SQL exercises for each build step

1. [Where this leads](#1-where-this-leads)
2. [Stage 1: Python fundamentals](#2-stage-1-python-fundamentals)
3. [Stage 2: Django and DRF basics](#3-stage-2-django-and-drf-basics)
4. [Stage 3: The rebuild](#4-stage-3-the-rebuild)
5. [Stage 4: After the rebuild](#5-stage-4-after-the-rebuild)
6. [Interview topics this covers](#6-interview-topics-this-covers)

---

## 1. Where this leads

Most company Python backends run on one of two frameworks:

| | Django + DRF | FastAPI |
|---|---|---|
| Typical use | Full products with users, an admin, CRUD and payments: e-commerce, SaaS, edtech, fintech back offices | API-only services, microservices, ML model serving, LLM and AI apps |
| ORM | Django ORM, built in | SQLAlchemy 2.0, with Alembic for migrations |
| Validation | DRF serializers | Pydantic |
| Style | Batteries included; conventions decide a lot for you | Minimal; you choose and wire up the pieces |
| Sync / async | Mostly sync, with async support | Async-first |

Flask still runs in plenty of older codebases, but new projects rarely choose it.

The same supporting stack shows up around either framework: PostgreSQL, Redis, Celery for
background jobs, Docker, pytest, type hints, ruff for linting and formatting, GitHub Actions
for CI, and a cloud provider (most often AWS).

### The plan: Django first, then FastAPI

Learn Django in depth through the rebuild, then build one small FastAPI service.

Why Django first:

- **It shows you a complete, well-built backend.** Django ships the ORM, migrations, auth, the
  admin, middleware and security defaults, all set up the standard way. FastAPI leaves those
  choices to you (which ORM, which auth library, how to lay out the project), and while you're
  new to Python you can't yet tell the good choices from the bad ones.
- **It matches the goal.** Learning Python, the Django ORM and PostgreSQL is exactly what the
  rebuild exercises.
- **It fits the app.** StudySphere has users, auth, an admin, CRUD and payments, which is what
  Django is built for. Rebuilding it in FastAPI would mean weeks assembling pieces Django gives
  you for free.
- **FastAPI comes quickly afterwards.** Most concepts carry over: serializers become Pydantic
  models, the Django ORM becomes SQLAlchemy, and middleware stays middleware. Expect a few
  weeks, not a fresh start.
- **You end up with both.** Django for full products and FastAPI for API and AI services
  covers most Python backend job listings.

When FastAPI first would be the better call:

- You're aiming specifically at AI/ML companies, or a job you're targeting asks for FastAPI.
- You want to stay closer to raw SQL. SQLAlchemy's query style maps onto SQL more directly than
  the Django ORM does, though [POSTGRES_PRACTICE.md](POSTGRES_PRACTICE.md) closes most of that
  gap on the Django side.

Whichever you use, interviews test SQL, API design and Python itself more than framework
details, and those carry across.

### The order

1. Python fundamentals, plus four warm-up ports of the Express utils
   ([Stage 1](#2-stage-1-python-fundamentals))
2. The Django and DRF tutorials ([Stage 2](#3-stage-2-django-and-drf-basics))
3. The StudySphere rebuild, with the Postgres exercises after each step
   ([Stage 3](#4-stage-3-the-rebuild))
4. Celery, Docker, CI and deployment ([Stage 4](#5-stage-4-after-the-rebuild))
5. One small FastAPI service, such as an AI quiz generator
   ([Stage 4](#5-stage-4-after-the-rebuild))

---

## 2. Stage 1: Python fundamentals

Skip whatever you already know. Main source: the official tutorial,
<https://docs.python.org/3/tutorial/> (sections 3–9).

| Topic | Where the rebuild uses it |
|---|---|
| Lists, dicts, sets, tuples; mutability | Request data, serializer output |
| Comprehensions, unpacking, f-strings | Everywhere |
| Functions: default arguments (and the mutable-default trap), `*args` / `**kwargs`, keyword-only arguments | Django's APIs are keyword-heavy: `filter(status=...)`, `serializer.save(**extra)` |
| Classes: inheritance, `super()`, `@property`, `@classmethod`, `__str__` | Models, serializers, views and permissions are all classes you subclass |
| Decorators | `@api_view`, `@permission_classes`, `@transaction.atomic` |
| Context managers (`with`) | `with transaction.atomic():`, psycopg connections |
| Exceptions: `try` / `except` / `else` / `finally`, custom exceptions | DRF exceptions, the error-envelope handler |
| Iterators and generators | QuerySets are lazy in the same way |
| Modules, packages, imports | Each Django app is a package |
| Type hints, `dataclasses` | Common in company codebases; FastAPI depends on them |
| `datetime` with time zones | OTP expiry, the soft-delete schedule |
| `hashlib`, `hmac`, `secrets`, `uuid`, `json` | Reset-token hashing, the Razorpay signature, OTP generation, primary keys, the JSON-string form fields |
| `venv` and `pip` | Project setup |

### Warm-up: port four Express utils

These are small and real, and you'll reuse the results in the rebuild. Write each one as a plain
Python module with pytest tests, before you touch Django.

1. [reference/server/utils/secToDuration.js](reference/server/utils/secToDuration.js) becomes
   `convert_seconds_to_duration(total_seconds: int) -> str`. Test it with
   `@pytest.mark.parametrize`: `0 → "0s"`, `61 → "1m 1s"`, `3600 → "1h 0m"`,
   `3725 → "1h 2m"`.
2. [reference/server/utils/courseDuration.js](reference/server/utils/courseDuration.js) becomes
   `calculate_total_duration(sections)`, which sums `timeDuration` across nested sections. Write
   it with nested loops first, then as a single `sum()` over a generator.
3. [reference/server/utils/hashToken.js](reference/server/utils/hashToken.js) becomes
   `hashlib.sha256(...).hexdigest()` plus `hmac.compare_digest`. Node's `timingSafeEqual`
   throws on a length mismatch, but Python's version just returns `False`, so you don't need
   the length guard.
4. [reference/server/utils/validateAuth.js](reference/server/utils/validateAuth.js) becomes a
   set of validators that return `str | None`. Keep the rule that signup accepts only `Student`
   and `Instructor`. If a client could send `accountType: "Admin"`, anyone could make
   themselves an admin.

**You're ready for Django when** you can write and test those four without constantly looking
things up.

---

## 3. Stage 2: Django and DRF basics

Do these in a throwaway project, not in this repo.

1. **The official Django tutorial, parts 1–5:**
   <https://docs.djangoproject.com/en/stable/intro/tutorial01/>. Parts 3 and 4 lean on HTML
   templates. The rebuild doesn't use those because React renders the UI, so skim them.
2. **The DRF quickstart and tutorial parts 1–4:**
   <https://www.django-rest-framework.org/tutorial/quickstart/>. They cover serialization,
   requests and responses, class-based views, and authentication and permissions. Parts 5–6
   (hyperlinked APIs, viewsets and routers) are optional for this project.
3. **The ORM topic guides** on making queries and aggregation:
   <https://docs.djangoproject.com/en/stable/topics/db/queries/> and
   <https://docs.djangoproject.com/en/stable/topics/db/aggregation/>.

**You're ready for the rebuild when** you can explain:

- project vs app, and what `INSTALLED_APPS` and `MIDDLEWARE` do
- model → migration → table, and what `sqlmigrate` shows you
- why a QuerySet doesn't touch the database until you iterate over it
- `F` vs `Q`, and `select_related` vs `prefetch_related`
- `Serializer` vs `ModelSerializer`, and where validation belongs
- authentication vs permissions vs throttling in DRF

**One choice the frontend makes for you.** Its URLs are RPC-style
(`POST /course/createCourse`, `POST /course/getCourseDetails`), not REST resources
(`/courses/{id}/`). DRF's ViewSets and routers generate REST resources, so they don't fit
here. Use `APIView` subclasses or `@api_view` functions, and write each path in `urls.py`
yourself. Still learn ViewSets in a side exercise, because most company Django codebases use
them.

---

## 4. Stage 3: The rebuild

Follow the build order in [DJANGO_REBUILD_GUIDE.md](DJANGO_REBUILD_GUIDE.md#9-build-order),
doing the matching exercises in [POSTGRES_PRACTICE.md](POSTGRES_PRACTICE.md) after each step.

Set up the tooling companies use in step 1, so it's a habit before the code grows:

- **ruff** for linting and formatting. It replaces flake8, isort and black.
- **pytest + pytest-django**, with a test for every rule in section 7 of the guide.
- **pre-commit**, to run ruff before every commit.
- Optional: **uv** instead of `pip` + `venv` (faster, with a lockfile), and **mypy** or
  **pyright** with `django-stubs` for type checking.

With git flow: one `feature/*` branch per build step, merged into `develop` once its "done
when" check passes.

---

## 5. Stage 4: After the rebuild

Roughly in order of how often companies expect them:

1. **Background jobs with Celery + Redis.** Move email sending (OTP, enrollment, payment) off
   the request path. Celery is the standard in Django shops.
2. **Docker.** A `Dockerfile` for Django served by gunicorn, and a `docker-compose.yml` with
   Postgres and Redis.
3. **CI.** GitHub Actions running ruff and pytest against a Postgres service container on every
   PR.
4. **Deployment.** Render, Railway or Google Cloud Run, with managed Postgres.
5. **Observability.** Sentry for errors, plus structured logging.
6. **A FastAPI service.** Build one of the AI features from the original plan (a quiz generator,
   or a study assistant over course content; see Phase 14 in
   [reference/docs/PLATFORM_PLAN_COMPREHENSIVE.md](reference/docs/PLATFORM_PLAN_COMPREHENSIVE.md))
   as its own small service, using FastAPI, Pydantic, SQLAlchemy 2.0 and Alembic. You'll learn
   async, dependency injection and an explicit ORM, which is the other half of the Python job
   market. Tutorials: <https://fastapi.tiangolo.com/tutorial/> and
   <https://docs.sqlalchemy.org/en/20/tutorial/>.

---

## 6. Interview topics this covers

| Area | Typical questions | Where you meet it |
|---|---|---|
| Python | Mutability, decorators, generators, the GIL; threads vs async vs processes | Stage 1; Stage 4 (FastAPI's async) |
| Django | Request lifecycle, middleware order, N+1 queries and their fixes, the custom user model, migrations, signals and why to avoid them | Rebuild steps 1–5 |
| SQL / Postgres | Joins, GROUP BY, indexes (composite, partial), EXPLAIN, transactions, isolation, locking | [POSTGRES_PRACTICE.md](POSTGRES_PRACTICE.md) |
| API design | REST vs RPC, status codes, pagination, idempotency, rate limiting | Rebuild steps 3, 4 and 7 |
| Security | Sessions vs JWT, cookies, CSRF, CORS, password hashing, IDOR (accessing another user's records by changing an id) | Rebuild steps 2 and 4 |
| System design | Caching, queues, background jobs, scaling reads | Stage 4 |
