# StudySphere: Django Rebuild Guide

A learning project: rebuild the StudySphere backend, originally Express + MongoDB, in
**Django + Django REST Framework (DRF) + PostgreSQL**, and keep the React frontend
unchanged.

The original MERN repo (`D:\Tech\edtech-full-new`) stays untouched. It is the spec. When
you're unsure what an endpoint should do, read its Express version in
[reference/server/](reference/server/), or run both backends and compare.

Related docs:

- [DJANGO_LEARNING_PATH.md](DJANGO_LEARNING_PATH.md): what to learn before, during and after
  this rebuild, and why Django comes before FastAPI
- [POSTGRES_PRACTICE.md](POSTGRES_PRACTICE.md): SQL exercises to do after each build step

1. [Repo layout](#1-repo-layout)
2. [Why rebuild the same app](#2-why-rebuild-the-same-app)
3. [Stack: Express → Django](#3-stack-express--django)
4. [Getting started](#4-getting-started)
5. [The API contract](#5-the-api-contract)
6. [Data model: Mongo → Postgres](#6-data-model-mongo--postgres)
7. [Behaviour to carry over](#7-behaviour-to-carry-over)
8. [Gotchas](#8-gotchas)
9. [Build order](#9-build-order)

---

## 1. Repo layout

```
edtech-full-python/
├── DJANGO_REBUILD_GUIDE.md   ← this file: what to build
├── DJANGO_LEARNING_PATH.md   ← what to learn, and in what order
├── POSTGRES_PRACTICE.md      ← SQL exercises for each build step
├── docker-compose.yml        ← Postgres for local development
├── .env.example              ← its credentials; copy to .env (gitignored)
├── frontend/                 ← React app, copied from the MERN repo
│   └── .env                  ← VITE_BASE_URL=http://localhost:8000/api/v1
├── backend/                  ← the Django project (you create it in step 1)
│   └── .env.example          ← SECRET_KEY, DATABASE_URL; copy to .env (gitignored)
└── reference/                ← read-only copy of the original, to port from
    ├── server/               ← the Express API (no node_modules, no .env)
    ├── docs/                 ← MERN-era plans: PLATFORM_PLAN*, SMS_OTP_PLAN
    └── README.md
```

How the frontend copy differs from the original:

- `npm run dev` starts Vite only. It used to start the Express server too.
- `concurrently` is removed, and so are the `server` ignore entries in ESLint and Prettier.
- `VITE_BASE_URL` points at Django's port, 8000.

Everything else is identical. The copy installs, type-checks, lints and builds.

`reference/` is gitignored. It's a local scratch copy, since the original repo already holds
its history. If you clone this repo elsewhere, read the Express code in the original repo
instead. Delete `reference/` once the port is done.

---

## 2. Why rebuild the same app

- **You already know the spec.** You know every endpoint, the edge cases, and the defects
  fixed in PR #31 of the original repo (payment, auth, course access). Your Django version
  is done when it gets those right too.
- **The frontend already exists.** It reads its API address from `VITE_BASE_URL`
  ([frontend/src/lib/axiosClient.ts](frontend/src/lib/axiosClient.ts)), so you can test end
  to end from the first endpoint.
- **The data model shows what Postgres does better.** The Mongoose models keep reference
  arrays on both sides of a relationship and sync them by hand. Translating them is most of
  the learning.

| Now (Mongo) | In Django/Postgres |
|---|---|
| `User.courses[]` and `Course.studentsEnrolled[]`, kept in sync by hand | One `Enrollment(user, course)` table with a unique constraint |
| `Category.courses[]` and `Course.category` | A single foreign key on `Course` |
| `Course.courseContent[]` → `Section.subSection[]` (ordered arrays) | Foreign keys plus an `order` field |
| Non-atomic payment enrollment | `transaction.atomic()`; the unique constraint blocks double enrollment |
| `.populate()` chains | `select_related` / `prefetch_related`, and spotting N+1 queries |
| No schema changes to manage | Migrations |

---

## 3. Stack: Express → Django

| Concern | Express (now) | Django (target) |
|---|---|---|
| Framework | Express 4 | Django + DRF |
| Database | MongoDB via Mongoose | PostgreSQL via the Django ORM (`psycopg` driver) |
| Schema changes | none | `makemigrations` / `migrate` |
| Auth | JWT in an httpOnly `token` cookie (`jsonwebtoken`) | The same cookie, via `PyJWT` and a custom DRF authentication class |
| Password hashing | `bcrypt` | Django's built-in hashers (`make_password` / `check_password`) |
| CORS | `cors` | `django-cors-headers` |
| CSRF defence | `verifyOrigin` middleware | The same check, ported as Django middleware ([Gotcha 5](#8-gotchas)) |
| Rate limiting | `express-rate-limit` | DRF throttling or `django-ratelimit` |
| File uploads | `express-fileupload` → Cloudinary | `request.FILES` → the `cloudinary` Python SDK |
| Email | `nodemailer`, HTML built in JS strings | `django.core.mail` + Django templates |
| Payments | `razorpay` (Node) | `razorpay` (Python) |
| Scheduled job | `node-cron`, in-process | A management command run by an external scheduler |
| Admin UI | none | Django admin, for free |
| Config | `dotenv` | `django-environ` |

---

## 4. Getting started

### Postgres in Docker

`docker-compose.yml` at the repo root reads its credentials from a root `.env` file, which
Docker Compose loads automatically:

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

`127.0.0.1:` keeps the database reachable from your machine only. Without it, Docker listens on
every network interface, so other devices on the same Wi-Fi could reach it.

`.env.example` is committed and `.env` is gitignored. Create your copy, set a real
`POSTGRES_PASSWORD` in it, then start Postgres:

```powershell
Copy-Item .env.example .env
docker compose up -d
```

Everyday commands:

| Command | What it does |
|---|---|
| `docker compose up -d` | Start Postgres in the background |
| `docker compose ps` | Check that it's running |
| `docker compose logs db` | Show Postgres's logs, e.g. when it won't start |
| `docker compose down` | Stop it. Your data stays in the `pgdata` volume. |
| `docker compose down -v` | Stop it **and delete the `pgdata` volume**. Every table and row is gone. |

**When you need `docker compose down -v`:**

- **You changed `POSTGRES_DB`, `POSTGRES_USER` or `POSTGRES_PASSWORD` in `.env`.** Postgres
  applies them only when it creates the database, which happens the first time the volume is
  empty. Later changes are ignored, and Django fails to log in with the new password. Run
  `docker compose down -v`, then `docker compose up -d`.
- **You want a clean slate,** for example when migrations get into a mess while you're
  learning.

After either one, run `python manage.py migrate` and `python manage.py createsuperuser` again.

If `up` fails with "port is already allocated", another Postgres is using 5432. Check with
`docker ps`, and either stop it or change the host side of the mapping (e.g.
`127.0.0.1:5434:5432`) along with the port in `DATABASE_URL`.

### The Django project

```powershell
mkdir backend; cd backend          # run everything below from backend\, not the repo root
python -m venv --upgrade-deps .venv
.venv\Scripts\Activate.ps1
python -m pip install django djangorestframework "psycopg[binary]" django-cors-headers PyJWT django-environ cloudinary razorpay
python -m pip freeze | Out-File -Encoding utf8 requirements.txt      # python -m pip freeze > requirements.txt

python -m django startproject config .
python manage.py startapp core       # base model, envelope, auth class, middleware, contact form
python manage.py startapp accounts   # User, Profile, OTP, UserDeletionLog → /auth, /profile
python manage.py startapp courses    # Category, Course, Section, SubSection, Enrollment, progress, reviews
python manage.py startapp payments   # Razorpay
```

Run pip and Django as `python -m pip` and `python -m django`, not `pip` and `django-admin`.
On Windows 11 with Smart App Control on, the unsigned `.exe` launchers in `.venv\Scripts` get
blocked ("An Application Control policy has blocked this file"), but the signed `python.exe`
doesn't. `--upgrade-deps` gives the new venv the latest pip, so you don't get the "new release
of pip is available" notice.

Write `requirements.txt` with `Out-File -Encoding utf8`, not `>`. In Windows PowerShell, `>`
saves the file as UTF-16, which git treats as binary. Re-run that line whenever you install a
new package.

**Move `SECRET_KEY` out of `settings.py` before your first commit.** `startproject`
hard-codes one there, and anything you commit stays in git history even after you delete it.
In `backend\`, create `.env.example` in VS Code with one line, `SECRET_KEY=` (the name, no
value), and commit it. Then make your private copy and generate a key:

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"   # paste it after SECRET_KEY= in .env
```

Don't write these files with `Out-File`. Windows PowerShell puts a byte order mark (BOM) at the
start of UTF-8 files, and django-environ then skips the first line, so `SECRET_KEY` goes
missing.

Read the key at the top of `config/settings.py`:

```python
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
```

If the key is missing, `env("SECRET_KEY")` stops Django with `ImproperlyConfigured` instead of
letting it run without one. In production, set a fresh key in the host's environment variables.
Never reuse the one from your local `.env`.

Point Django at the same database. Add
`DATABASE_URL=postgres://studysphere:<your-password>@localhost:5432/studysphere` to
`backend/.env` (and `DATABASE_URL=` to `.env.example`), using the values from the root `.env`.
Read it with the same `env` object: `DATABASES = {"default": env.db()}`.

**Don't run `migrate` until the custom User model exists** ([Gotcha 1](#8-gotchas)).

### The frontend

```powershell
cd frontend
npm install
npm run dev   # http://localhost:5173, calling http://localhost:8000/api/v1
```

### Compare against the original

Start the Express server from the original repo (`cd D:\Tech\edtech-full-new\server; npm run dev`,
port 4000). Then switch `VITE_BASE_URL` in `frontend/.env` between `:4000` and `:8000`, and
restart Vite after each change because it reads `.env` only at startup. When a page works on
Express but breaks on Django, compare the two responses in the browser's Network tab.

---

## 5. The API contract

Everything lives under `/api/v1`. Paths are camelCase, case-sensitive and have **no trailing
slash**. Match them exactly.

### Response envelope

```json
{ "success": true, "message": "Course created successfully", "data": {} }
```

`data` appears only when there is a payload. Errors look like
`{ "success": false, "message": "..." }`, with a matching status code. The frontend checks
`success` before reading `data`.

The exact shape of every endpoint's response is in [frontend/src/types/](frontend/src/types/).
Shapes differ by endpoint. For example, `getAllCourses` returns a six-field projection, and
most endpoints send `instructor` as an id rather than an object. Read the type before
writing the serializer.

### Field conventions

- **`_id`, not `id`**, on every object, as a string. The frontend uses `_id` in 88 places.
- **camelCase names**: `courseName`, `studentsEnrolled`, `additionalDetails`. One oddity:
  CourseProgress uses `courseID` and `userId`.
- **References are an id or a nested object, depending on the endpoint.** This mirrors
  Mongo's `populate`. Check the type each time.
- **Computed fields.** `totalDuration` is added by `getCourseDetails`,
  `getFullCourseDetails`, `getInstructorCourses` and `getEnrolledCourses`.
  `getEnrolledCourses` also adds `progressPercentage`.
- Dates are ISO strings. Users carry `createdAt` and `updatedAt`.

### Status codes the frontend reacts to

- **401** on any path except `/auth/login`: the frontend clears its auth state and sends the
  user to `/login` if they're on a protected page. "Not logged in" and "token expired" must
  be 401, never 403.
- **403**: wrong role ("This is protected route for Instructor only").
- **429**: rate limited.

### Endpoints

Who can call it: **Public** (no login), **Auth** (any logged-in user), or
**Student / Instructor / Admin** (that `accountType` only).

**`/api/v1/auth`**, from [reference/server/routes/User.js](reference/server/routes/User.js)

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/login` | Public | Sets the `token` cookie. Cancels a pending account deletion. 5 failed tries per 15 min. |
| POST | `/logout` | Public | Clears the cookie |
| POST | `/signup` | Public | Needs a valid OTP |
| POST | `/sendotp` | Public | 3 per hour per IP + email |
| POST | `/changepassword` | Auth | |
| POST | `/reset-password-token` | Public | Emails a reset link. 3 per hour per IP + email. |
| POST | `/reset-password` | Public | |

**`/api/v1/profile`**, from [reference/server/routes/Profile.js](reference/server/routes/Profile.js)

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/getUserDetails` | Auth | Called on every page load to restore the session |
| PUT | `/updateProfile` | Auth | |
| PUT | `/updateDisplayPicture` | Auth | multipart, file field `displayPicture` |
| GET | `/getEnrolledCourses` | Auth | Adds `totalDuration` and `progressPercentage` to each course |
| GET | `/instructorDashboard` | Instructor | Per course: `totalStudentsEnrolled`, `totalAmountGenerated` (students × price) |
| DELETE | `/deleteProfile` | Auth | Soft delete. Hard delete follows after 3 days. |

**`/api/v1/course`**, from [reference/server/routes/Course.js](reference/server/routes/Course.js)

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/showAllCategories` | Public | |
| POST | `/getCategoryPageDetails` | Public | Returns `selectedCategory`, `differentCategory`, `mostSellingCourses` |
| POST | `/createCategory` | Admin | |
| GET | `/getAllCourses` | Public | |
| POST | `/getCourseDetails` | Public | `courseId` in the body |
| POST | `/getFullCourseDetails` | Auth | Also returns the viewer's `completedVideos` |
| GET | `/getInstructorCourses` | Instructor | |
| POST | `/createCourse` | Instructor | multipart: file `thumbnailImage`; `tag` and `instructions` are JSON strings |
| POST | `/editCourse` | Instructor | multipart, partial update |
| DELETE | `/deleteCourse` | Instructor | `courseId` in the JSON body |
| POST | `/addSection` | Instructor | |
| POST | `/updateSection` | Instructor | |
| POST | `/deleteSection` | Instructor | |
| POST | `/addSubSection` | Instructor | multipart, file field `video` |
| POST | `/updateSubSection` | Instructor | multipart, `video` optional |
| POST | `/deleteSubSection` | Instructor | |
| POST | `/updateCourseProgress` | Student | Marks one subsection complete |
| POST | `/createRating` | Student | Enrolled students only, once per course |
| GET | `/getAverageRating` | Public | |
| GET | `/getReviews` | Public | Populates the author and the course name |

**`/api/v1/payment`**, from [reference/server/routes/Payments.js](reference/server/routes/Payments.js)

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/capturePayment` | Student | Takes a `courses` array (cart). The amount comes from DB prices. |
| POST | `/verifyPayment` | Student | Checks the signature, then enrolls |
| POST | `/sendPaymentSuccessEmail` | Student | |

**`/api/v1/reach`**

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/contact` | Public | Replies **200 even on failure**. The frontend reads `success`. |

Express also serves `GET /`, which returns `{ success: true, message: "Your server is up and running." }`,
and `GET /robots.txt`.

---

## 6. Data model: Mongo → Postgres

The originals are in [reference/server/models/](reference/server/models/).

### Field types

| Mongoose | Django |
|---|---|
| `String` | `CharField(max_length=…)` or `TextField` |
| `Number` | `IntegerField` / `PositiveIntegerField` (see [Gotcha 8](#8-gotchas) before using `DecimalField`) |
| `Boolean` | `BooleanField` |
| `Date` | `DateTimeField` |
| `enum: [...]` | `models.TextChoices` |
| `[String]` | `ArrayField(models.CharField(...))` from `django.contrib.postgres` (Postgres-only) |
| `ObjectId` ref | `ForeignKey` or `OneToOneField` |
| `[ObjectId]` ref | The reverse side of a `ForeignKey`, or a `ManyToManyField` |
| `unique: true` | `unique=True` or `Meta.constraints = [UniqueConstraint(...)]` |
| `index: true` | `db_index=True` or `Meta.indexes` |
| `{ timestamps: true }` | `created_at` with `auto_now_add=True`, `updated_at` with `auto_now=True` |
| TTL index (`expires`) | No equivalent. Treat old rows as expired when you read them, and delete them in a job. |

### Primary keys

Give every model a UUID primary key through a shared abstract base model in `core`:

```python
id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
```

UUIDs are strings, like Mongo ObjectIds, which the frontend expects. Route params are always
strings, so comparing them to an integer `_id` fails silently. Sequential integer ids also
let anyone enumerate `/courses/1`, `/courses/2` and so on.

### Models

| Mongoose model | Django model | What changes |
|---|---|---|
| `User` | `accounts.User`, custom: `AbstractBaseUser` + `PermissionsMixin`, `USERNAME_FIELD = "email"` | `courses[]` becomes `Enrollment`. `courseProgress[]` becomes a reverse FK. `additionalDetails` becomes the `Profile` one-to-one. Keep `accountType`, `isDeleted`, `deletionScheduledAt`, `resetPasswordTokenHash`, `resetPasswordExpires`. |
| `Profile` | `accounts.Profile`, `user = OneToOneField(User)` | Serialize it as `additionalDetails`. `contactNumber` is a Number in Mongo. A `CharField` is more correct (leading zeros, `+91`), but the frontend type expects `number \| null`, so pick one and keep the contract. |
| `OTP` | `accounts.OTP` | No TTL index. Rows older than 5 minutes count as expired; the nightly job deletes them. |
| `UserDeletionLog` | `accounts.UserDeletionLog` | `user_id` must be a **plain `UUIDField`, not a ForeignKey**. The user row is gone by the time anyone reads the log, so a FK would block the delete or cascade the log away with it. |
| `Category` | `courses.Category` | `courses[]` goes away. It's the reverse of `Course.category`. |
| `Course` | `courses.Course` | `instructor` FK. `category` FK, nullable. `tag` and `instructions` become `ArrayField`s. `status` becomes `TextChoices`. `courseContent[]`, `ratingAndReviews[]` and `studentsEnrolled[]` all become reverse relations. |
| `Section` | `courses.Section` | Gains a `course` FK and an `order` field. Mongo stored the order as the array position. |
| `SubSection` | `courses.SubSection` | Gains a `section` FK and an `order` field. |
| none | `courses.Enrollment` | **New.** `user` FK, `course` FK, `enrolled_at`, and `UniqueConstraint(user, course)`. Replaces both `User.courses[]` and `Course.studentsEnrolled[]`. You can also expose it as `ManyToManyField(through="Enrollment")`. |
| `CourseProgress` | `courses.CourseProgress` | `user` FK, `course` FK, `completed_videos = ManyToManyField(SubSection)`, `UniqueConstraint(user, course)` |
| `RatingAndReview` | `courses.RatingAndReview` | `UniqueConstraint(user, course)` enforces one review per student. Add a `CheckConstraint` keeping `rating` between 1 and 5. |

---

## 7. Behaviour to carry over

These are the rules the Express code enforces today. Several came from the PR #31 fixes.
Each one deserves a test.

**Session**, in [reference/server/config/authCookie.js](reference/server/config/authCookie.js)

- The cookie is named `token`: httpOnly, path `/`, lasting 2 hours. In dev: `SameSite=Lax`,
  not secure. In production: `SameSite=None; Secure`, because the frontend and the API are
  on different sites.
- JWT lifetime equals cookie lifetime (2 hours). They used to drift apart, which caused
  unexplained 401s.
- The JWT payload is `{ email, id, accountType }`. Role checks re-read the user from the
  database instead of trusting `accountType` in the token.
- There is no refresh endpoint. A 401 ends the session.

**OTP and password reset**

- The OTP is stored hashed, never in plaintext. It expires after 5 minutes. After 5 wrong
  attempts the user must request a new one. See
  [reference/server/models/OTP.js](reference/server/models/OTP.js).
- Only the SHA-256 hash of the reset token is stored on the user, and it expires after 5
  minutes. See [reference/server/controllers/ResetPassword.js](reference/server/controllers/ResetPassword.js).
- Emails are trimmed and lowercased everywhere, and `User.email` is unique.

**Rate limits**, in [reference/server/middlewares/rateLimit.js](reference/server/middlewares/rateLimit.js)

- Login allows 5 failed attempts per 15 minutes per IP. Successful logins don't count.
- `sendotp` and `reset-password-token` allow 3 per hour, keyed on IP + target email.
- Behind a proxy, trust exactly one hop of `X-Forwarded-For` (Express sets
  `trust proxy = 1`). Trusting more lets clients spoof their IP and dodge the limits.

**Accounts**

- Signup accepts only `Student` or `Instructor` as `accountType`. If it accepted `Admin` from
  the client, anyone could make themselves an admin. See
  [reference/server/utils/validateAuth.js](reference/server/utils/validateAuth.js).
- Deletion is soft: `isDeleted = true` and `deletionScheduledAt = now + 3 days`. Logging in
  before then cancels it.
- A nightly job at 01:00 hard-deletes accounts that are due and writes a `UserDeletionLog`
  row for each. See [reference/server/jobs/deleteInactiveUsers.js](reference/server/jobs/deleteInactiveUsers.js).

**Payments**, in [reference/server/controllers/Payments.js](reference/server/controllers/Payments.js)

- The order amount is the sum of the courses' **database** prices, in paise (rupees × 100).
  Never use an amount sent by the client.
- Reject the order if the student is already enrolled in any course in the cart.
- Verify the Razorpay signature (HMAC-SHA256) on the server before enrolling.
- Enrollment must be atomic and idempotent. Wrap it in `transaction.atomic()` and let the
  `Enrollment` unique constraint make a replayed verify a no-op.

**Misc**

- The contact form replies 200 even when it fails.
- Every response carries `X-Robots-Tag: noindex, nofollow`, and `/robots.txt` disallows
  everything. The API should never be indexed.

---

## 8. Gotchas

1. **Create the custom User model before the first `migrate`.** Set
   `AUTH_USER_MODEL = "accounts.User"` before you ever run `migrate`. Changing it later means
   wiping the database.

2. **Trailing slashes.** Django's convention is `login/`, but the frontend calls `/auth/login`.
   Write paths without the slash (`path("login", views.login)`), and use
   `DefaultRouter(trailing_slash=False)` if you use routers. Otherwise `APPEND_SLASH` tries to
   redirect, which can't keep a POST body (Django raises an error in DEBUG).

3. **DRF answers 403 where you need 401.** If your authentication class has no
   `authenticate_header()`, DRF turns "not authenticated" into a 403, and the frontend only
   logs out on 401:

   ```python
   # core/authentication.py
   import jwt
   from django.conf import settings
   from rest_framework.authentication import BaseAuthentication
   from rest_framework.exceptions import AuthenticationFailed

   from accounts.models import User


   class CookieJWTAuthentication(BaseAuthentication):
       def authenticate(self, request):
           token = request.COOKIES.get("token")
           if not token:
               return None  # anonymous; IsAuthenticated then rejects with 401
           try:
               payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
           except jwt.PyJWTError:
               raise AuthenticationFailed("Token is invalid")
           user = User.objects.filter(pk=payload["id"]).first()
           if user is None:
               raise AuthenticationFailed("Token is invalid")
           return user, payload

       def authenticate_header(self, request):
           # Any value here makes DRF reply 401 instead of 403.
           return 'Cookie realm="api"'
   ```

   Role checks become permission classes (`IsStudent`, `IsInstructor`, `IsAdmin`) that read
   `request.user.account_type`.

4. **DRF's error shape.** DRF returns `{"detail": "..."}`, and validation errors as
   `{"email": ["..."]}`. Point `REST_FRAMEWORK["EXCEPTION_HANDLER"]` at a function that calls
   DRF's default handler and rewrites the body as `{ success: false, message }`. For success
   responses, use a small helper such as `ok(data, message)`.

5. **CSRF.** DRF views are CSRF-exempt unless you use `SessionAuthentication`, so with cookie
   JWT auth nothing checks CSRF. Port
   [reference/server/middlewares/verifyOrigin.js](reference/server/middlewares/verifyOrigin.js)
   as Django middleware: for any method other than GET, HEAD or OPTIONS, reject the request
   when it has an `Origin` (or `Referer`) header that isn't in `CORS_ALLOWED_ORIGINS`.

6. **CORS with cookies.**

   ```python
   CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]  # exact origins, never "*"
   CORS_ALLOW_CREDENTIALS = True
   ```

   Put `corsheaders.middleware.CorsMiddleware` near the top of `MIDDLEWARE`, above
   `CommonMiddleware`. In dev, set the cookie with
   `response.set_cookie("token", jwt, max_age=7200, httponly=True, samesite="Lax", secure=False)`.

7. **`tag` and `instructions` arrive as JSON strings.** The course form sends
   `multipart/form-data` with `tag` and `instructions` set to `JSON.stringify(...)` strings.
   Call `json.loads` on them in the serializer, for example in `validate_tag`.

8. **`DecimalField` serializes as a string.** DRF renders `Decimal("499.00")` as `"499.00"`,
   but the frontend expects `price` to be a number. Store whole rupees in an `IntegerField`,
   or set `COERCE_DECIMAL_TO_STRING = False`.

9. **`_id` and camelCase.** Keep model fields snake_case (`course_name`) and map them in
   serializers: `courseName = serializers.CharField(source="course_name")`. Rename `id` to
   `_id` once, in a base serializer's `to_representation`. Packages like
   `djangorestframework-camel-case` automate camelCase, but check what they do to `_id` and
   `courseID` first.

10. **N+1 queries.** A nested serializer (course → sections → subsections) runs one query per
    row unless the view uses `select_related` (FK, one-to-one) and `prefetch_related`
    (reverse, many-to-many). Install `django-debug-toolbar`, or use `assertNumQueries` in
    tests, to see what's happening.

11. **Uploads.** You don't need temp-file middleware. Pass `request.FILES["video"]` to
    `cloudinary.uploader.upload(file, resource_type="auto")`, which is what Express does
    today. Django spills large uploads to disk on its own.

12. **The nightly job.** Django has no in-process cron. Write a management command
    (`python manage.py delete_inactive_users`) and schedule it from outside: Windows Task
    Scheduler locally, cron on a VM, Cloud Scheduler in production. Celery beat is the
    heavier option once you add a task queue.

---

## 9. Build order

Each step leaves something working you can click through in the frontend. After each step, do
the matching exercises in [POSTGRES_PRACTICE.md](POSTGRES_PRACTICE.md).

| # | Step | Endpoints | Done when | You learn |
|---|---|---|---|---|
| 1 | Foundation | none | You can create a category, and a course with sections and subsections, in `/admin`, and see the rows in `psql` | Models, migrations, constraints, the admin |
| 2 | Plumbing | `GET /`, `/robots.txt` | The envelope, error handler, cookie auth class, CORS, origin middleware and robots header are all in place | DRF settings, middleware |
| 3 | Public reads | `showAllCategories`, `getCategoryPageDetails`, `getAllCourses`, `getCourseDetails`, `getReviews`, `getAverageRating` | The home, catalog and course pages render from Postgres | Serializers, `select_related` / `prefetch_related`, `Avg` |
| 4 | Auth | All of `/auth`, plus `getUserDetails` | Sign up with an OTP, log in, reload and stay logged in, log out. A 6th wrong password gets a 429. | The custom user, hashing, cookies, PyJWT, email, throttling |
| 5 | Instructor | Course, section and subsection CRUD, `getInstructorCourses`, `getFullCourseDetails`, `deleteCourse`, `updateProfile`, `updateDisplayPicture`, `instructorDashboard` | You can build and publish a course in the UI, with a thumbnail and videos | Multipart, Cloudinary, permissions, `annotate` with `Count` and `F` |
| 6 | Student | `getEnrolledCourses`, `updateCourseProgress`, `createRating`, `deleteProfile`, plus the nightly command | Watch lectures, see progress persist, leave one review | Many-to-many, unique constraints, management commands |
| 7 | Payments and contact | `capturePayment`, `verifyPayment`, `sendPaymentSuccessEmail`, `contact` | A test-mode purchase enrolls exactly once, even when verify is replayed | `transaction.atomic`, idempotency, HMAC |

Until payments exist (step 7), enroll yourself through the admin by adding an `Enrollment`
row.

**Tests.** Add `pytest` and `pytest-django` in step 1 and write tests as you go. At a minimum,
turn every rule in [section 7](#7-behaviour-to-carry-over) into a test. Those rules are the
bugs the Express version already hit.

**Stretch goal.** Write a management command that imports the real data from MongoDB
(`mongoexport` JSON → Postgres), mapping ObjectIds to UUIDs and the two-sided arrays to
`Enrollment` rows. It teaches `bulk_create` and data migration, the part of a real stack
switch that tutorials skip. To learn the psycopg driver as well, write it as a plain script
instead; [POSTGRES_PRACTICE.md](POSTGRES_PRACTICE.md#psycopg-directly-the-data-import) shows
how.
