# PostgreSQL Practice

The Django ORM writes SQL for you, which makes it easy to finish the rebuild without really
learning PostgreSQL. These exercises make you read and write the SQL yourself.

Each section matches a step in the build order of
[DJANGO_REBUILD_GUIDE.md](DJANGO_REBUILD_GUIDE.md#9-build-order). Do it right after that step.

Table and column names assume the models in the guide's section 6, with snake_case fields and
Django's default naming: `<app>_<model>` for tables (`courses_course`) and `<field>_id` for
foreign-key columns (`course_id`). Your names may differ, so check them with `\d`.

1. [Tools](#tools)
2. [After step 1: read the schema, then break it](#after-step-1-read-the-schema-then-break-it)
3. [After step 3: joins, GROUP BY and NULL](#after-step-3-joins-group-by-and-null)
4. [After step 3: indexes and EXPLAIN](#after-step-3-indexes-and-explain)
5. [After step 4: expression indexes and time](#after-step-4-expression-indexes-and-time)
6. [After step 5: aggregates and deferrable constraints](#after-step-5-aggregates-and-deferrable-constraints)
7. [After step 6: join fan-out and partial indexes](#after-step-6-join-fan-out-and-partial-indexes)
8. [After step 7: transactions and locks](#after-step-7-transactions-and-locks)
9. [psycopg directly: the data import](#psycopg-directly-the-data-import)
10. [Beyond the port: features only Postgres has](#beyond-the-port-features-only-postgres-has)

---

## Tools

### Open psql

```powershell
docker compose exec db psql -U studysphere -d studysphere
```

`python manage.py dbshell` does the same thing, but it needs the `psql` client installed on
Windows. The Docker route doesn't.

| Command | What it does |
|---|---|
| `\dt` | List tables |
| `\d courses_course` | Show one table's columns, indexes and constraints |
| `\di` | List indexes |
| `\x` | Toggle expanded output, for wide rows |
| `\timing` | Show how long each query takes |
| `\q` | Quit |

### See the SQL Django writes

```powershell
python manage.py sqlmigrate courses 0001   # the DDL a migration runs
```

```python
# python manage.py shell
from django.db import connection
from django.test.utils import CaptureQueriesContext
from courses.models import Course

qs = Course.objects.filter(status="Published")
print(qs.query)                   # the SELECT, approximately (parameters aren't quoted)
print(qs.explain(analyze=True))   # Postgres's plan, after actually running it

with CaptureQueriesContext(connection) as ctx:
    list(qs)
print(len(ctx.captured_queries), ctx.captured_queries[0]["sql"])
```

To log every query while the dev server runs, add this to settings. It only works with
`DEBUG = True`.

```python
LOGGING = {
    "version": 1,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django.db.backends": {"handlers": ["console"], "level": "DEBUG"}},
}
```

---

## After step 1: read the schema, then break it

1. Run `sqlmigrate` for each app and read the `CREATE TABLE` statements. Find:
   - where each `UniqueConstraint` and `CheckConstraint` ends up
   - the `CREATE INDEX` for every foreign key. PostgreSQL doesn't index foreign-key columns
     on its own; Django adds one per `ForeignKey`.
   - `DEFERRABLE INITIALLY DEFERRED` on the foreign keys. Postgres checks those at commit,
     not after each statement.
2. In psql, run `\d courses_enrollment` and match each line to your model.
3. Create a few rows in the admin, then break the constraints on purpose and read each error
   code:

   ```sql
   -- Duplicate an existing enrollment: unique_violation (23505)
   INSERT INTO courses_enrollment (id, user_id, course_id, enrolled_at)
   SELECT gen_random_uuid(), user_id, course_id, now()
   FROM courses_enrollment
   LIMIT 1;

   -- A 6-star rating: check_violation (23514)
   UPDATE courses_ratingandreview SET rating = 6
   WHERE id = (SELECT id FROM courses_ratingandreview LIMIT 1);
   ```

4. **Defaults live in Python.** The insert above passes `id` and `enrolled_at` itself,
   because Django's `default=` and `auto_now_add` run in Python, not in the table. A raw
   `INSERT` must supply every `NOT NULL` column. (`db_default=` puts a default in the
   database instead.)
5. **So do cascades.** With `on_delete=models.CASCADE`, Django deletes the child rows itself,
   in Python. Check whether `\d courses_section` shows `ON DELETE CASCADE` on its course
   foreign key. Then delete a course that has sections twice: once with `course.delete()` in
   the Django shell, and once with `DELETE FROM courses_course WHERE id = '...'` in psql.
   Explain the difference.

---

## After step 3: joins, GROUP BY and NULL

### Most-selling courses

Write it in SQL first:

```sql
SELECT c.id, c.course_name, COUNT(e.id) AS students
FROM courses_course c
LEFT JOIN courses_enrollment e ON e.course_id = c.id
WHERE c.status = 'Published'
GROUP BY c.id
ORDER BY students DESC
LIMIT 10;
```

Answer these:

- Why `LEFT JOIN`? What happens to courses with no students under a plain `JOIN`?
- Swap `COUNT(e.id)` for `COUNT(*)`. Why does a course with no students now show 1?
- Why can you select `c.course_name` while grouping only by `c.id`? (Postgres knows every
  column depends on the primary key.)

Then write the ORM version and compare its SQL with yours:

```python
from django.db.models import Count

qs = (
    Course.objects.filter(status="Published")
    .annotate(students=Count("enrollments"))
    .order_by("-students")[:10]
)
print(qs.query)
```

`enrollments` is the `related_name` on `Enrollment.course`; use whatever you named it.

### Average rating

```sql
SELECT ROUND(AVG(rating), 1)
FROM courses_ratingandreview
WHERE course_id = '<course-uuid>';
```

Run it for a course with no reviews. `AVG` over zero rows is `NULL`, not 0. The Express
version returns 0 in that case, so the frontend expects 0. In the ORM,
`Coalesce(Avg("rating"), 0.0)` does the same.

### N+1, counted

Serialize one course with its sections and subsections three ways, and count the queries with
`CaptureQueriesContext`:

1. `Course.objects.get(...)` with nested serializers: 1 query for the course, 1 for its
   sections, then 1 per section for its subsections.
2. `Course.objects.prefetch_related("sections__subsections").get(...)`: 3 queries in total.
3. One SQL query with two `LEFT JOIN`s that you write yourself.

Why does Django prefer option 2 over option 3? Look at how many rows option 3 returns: the
course's columns repeat once for every subsection.

---

## After step 3: indexes and EXPLAIN

With only a few rows, Postgres scans the whole table no matter what, so make the table big.
Create a few categories and one instructor in the admin first, then:

```sql
WITH cats AS (SELECT array_agg(id) AS ids FROM courses_category)
INSERT INTO courses_course
    (id, course_name, course_description, what_you_will_learn, instructor_id,
     category_id, price, thumbnail, tag, instructions, status, created_at)
SELECT gen_random_uuid(),
       'Seed course ' || g,
       'Seeded for EXPLAIN practice',
       '',
       (SELECT id FROM accounts_user WHERE account_type = 'Instructor' LIMIT 1),
       cats.ids[1 + g % array_length(cats.ids, 1)],
       (random() * 5000)::int,
       '',
       ARRAY['seed'],
       ARRAY[]::varchar[],
       CASE WHEN g % 4 = 0 THEN 'Draft' ELSE 'Published' END,
       now() - g * interval '1 minute'
FROM generate_series(1, 100000) AS g, cats;

ANALYZE courses_course;  -- refresh the planner's statistics
```

Adjust the column list to match `\d courses_course`. Every `NOT NULL` column without a database
default has to appear.

Now look at a catalog query's plan:

```sql
EXPLAIN ANALYZE
SELECT id, course_name, price
FROM courses_course
WHERE category_id = '<category-uuid>' AND status = 'Published'
ORDER BY created_at DESC
LIMIT 20;
```

Read the plan from the bottom up. Note the scan type (Seq Scan, Index Scan or Bitmap Heap
Scan), whether there's a Sort node, and the actual time. Then add a composite index that
matches the query:

```python
class Meta:
    indexes = [
        models.Index(fields=["category", "status", "-created_at"], name="course_catalog_idx"),
    ]
```

Run `makemigrations` and `migrate`, run `EXPLAIN ANALYZE` again, and compare. Then ask: would
the same index help if its columns were ordered `["created_at", "category", "status"]`? Try it.

Clean up when you're done:

```sql
DELETE FROM courses_course WHERE 'seed' = ANY(tag);
```

---

## After step 4: expression indexes and time

### Case-insensitive unique email

The app lowercases emails, but a database rule also catches any code path that forgets. Keep
`unique=True` on the field (Django requires it for `USERNAME_FIELD`) and add:

```python
from django.db.models.functions import Lower

class Meta:
    constraints = [
        models.UniqueConstraint(Lower("email"), name="user_email_ci_unique"),
    ]
```

`sqlmigrate` shows this is really a unique index on the expression `lower(email)`. Prove it in
psql by setting one user's email to the uppercase version of another user's:

```sql
UPDATE accounts_user
SET email = (SELECT upper(email) FROM accounts_user WHERE id = '<user-b>')
WHERE id = '<user-a>';
```

### What a stored password looks like

```sql
SELECT email, password FROM accounts_user LIMIT 3;
```

The format is `algorithm$iterations$salt$hash`. Why store the iteration count in the row? So
Django can raise it in a later version and re-hash each password at that user's next login.

### Time zones

With `USE_TZ = True` (the default), `DateTimeField` becomes `timestamp with time zone`.
Postgres stores the instant in UTC and displays it in the session's time zone:

```sql
SELECT created_at FROM accounts_otp LIMIT 1;
SET TIME ZONE 'Asia/Kolkata';
SELECT created_at FROM accounts_otp LIMIT 1;  -- same instant, different display
```

### Expiring OTPs without a TTL index

```sql
DELETE FROM accounts_otp
WHERE created_at < now() - interval '5 minutes'
RETURNING email, created_at;
```

`RETURNING` hands back the deleted rows, so the nightly job can log them in the same statement.
The ORM version,
`OTP.objects.filter(created_at__lt=timezone.now() - timedelta(minutes=5)).delete()`, returns
counts, not rows.

---

## After step 5: aggregates and deferrable constraints

### Instructor dashboard

```sql
SELECT c.id, c.course_name, c.price,
       COUNT(e.id)           AS total_students_enrolled,
       COUNT(e.id) * c.price AS total_amount_generated
FROM courses_course c
LEFT JOIN courses_enrollment e ON e.course_id = c.id
WHERE c.instructor_id = '<instructor-uuid>'
GROUP BY c.id;
```

```python
from django.db.models import Count, F

(
    Course.objects.filter(instructor=request.user)
    .annotate(total_students=Count("enrollments"))
    .annotate(total_amount=F("total_students") * F("price"))
)
```

Design question: Express computes revenue as students × the *current* price, which is wrong as
soon as an instructor changes a price. What would you store on `Enrollment`, or in a `Payment`
table, to report real revenue, and how would the query change? (Store `amount_paid`, then use
`SUM(e.amount_paid)`.)

### Reordering sections

Suppose `Section` has `UniqueConstraint(fields=["course", "order"])`. Swapping two sections'
`order` values then fails halfway, because the first `UPDATE` creates a duplicate. Try it in
psql inside `BEGIN; … COMMIT;`.

Then make the constraint deferrable, so Postgres checks it at commit instead:

```python
models.UniqueConstraint(
    fields=["course", "order"],
    name="section_order_unique",
    deferrable=models.Deferrable.DEFERRED,
)
```

Run the swap again, this time inside `transaction.atomic()`.

---

## After step 6: join fan-out and partial indexes

### Progress percentage

Count all lectures and completed lectures for each enrolled course in one query:

```sql
SELECT c.id, c.course_name,
       COUNT(DISTINCT ss.id)            AS total_lectures,
       COUNT(DISTINCT cv.subsection_id) AS completed
FROM courses_enrollment e
JOIN courses_course c           ON c.id = e.course_id
LEFT JOIN courses_section s     ON s.course_id = c.id
LEFT JOIN courses_subsection ss ON ss.section_id = s.id
LEFT JOIN courses_courseprogress cp
       ON cp.course_id = c.id AND cp.user_id = e.user_id
LEFT JOIN courses_courseprogress_completed_videos cv
       ON cv.courseprogress_id = cp.id
WHERE e.user_id = '<student-uuid>'
GROUP BY c.id;
```

Remove both `DISTINCT`s and watch the numbers inflate: every lecture row gets multiplied by
every completed row. That's join fan-out, and it's behind a lot of wrong dashboards.

Rewrite it with two scalar subqueries instead. Then write it in the ORM, once with
`Count(..., distinct=True)` and once with `Subquery` and `OuterRef`.

### A partial index for the nightly job

The deletion job looks for `is_deleted = true AND deletion_scheduled_at <= now()`, which
matches almost no rows. Index only those rows:

```python
models.Index(
    fields=["deletion_scheduled_at"],
    condition=models.Q(is_deleted=True),
    name="user_pending_deletion_idx",
)
```

Seed a large number of users the way you seeded courses, then compare the partial index's size
with a full index on the same column:

```sql
SELECT pg_size_pretty(pg_relation_size('user_pending_deletion_idx'));
```

---

## After step 7: transactions and locks

Open **two** psql sessions (two terminals, each running the `docker compose exec` command).
Look up a real student id and course id first.

### A unique constraint serializes concurrent inserts

1. Session A: `BEGIN;`
2. Session A:
   ```sql
   INSERT INTO courses_enrollment (id, user_id, course_id, enrolled_at)
   VALUES (gen_random_uuid(), '<student>', '<course>', now());
   ```
3. Session B: run the same `INSERT`. It **hangs**, waiting on A.
4. Session A: `COMMIT;`. Session B now fails with
   `duplicate key value violates unique constraint`.

Repeat, but end step 4 with `ROLLBACK;`. This time B's insert succeeds. That's why the
`Enrollment` constraint makes a replayed `verifyPayment` safe, even when two requests arrive at
the same moment.

### SELECT … FOR UPDATE

1. Session A: `BEGIN; SELECT * FROM courses_course WHERE id = '<course>' FOR UPDATE;`
2. Session B: `UPDATE courses_course SET price = price + 1 WHERE id = '<course>';` It hangs.
3. A third session shows who is waiting:
   ```sql
   SELECT pid, state, wait_event_type, left(query, 60) AS query
   FROM pg_stat_activity
   WHERE datname = 'studysphere';
   ```
4. Session A: `COMMIT;`. Session B finishes.

In Django this is `Course.objects.select_for_update().get(pk=...)`, which only works inside
`transaction.atomic()`.

### Isolation levels

`SHOW transaction_isolation;` reports `read committed`, Postgres's default. Each statement sees
the data committed before *that statement* started, not before the transaction started.

1. Session A: `BEGIN; SELECT price FROM courses_course WHERE id = '<course>';`
2. Session B: `UPDATE courses_course SET price = price + 100 WHERE id = '<course>';`
3. Session A: run the same `SELECT` again. It sees the new price. `COMMIT;`

Now repeat with Session A starting `BEGIN ISOLATION LEVEL REPEATABLE READ;`. A keeps seeing the
old price until it commits.

---

## psycopg directly: the data import

Django calls psycopg for you, so you'll rarely touch the driver. To learn it, do the guide's
stretch goal (importing the real Mongo data) as a plain Python script with psycopg, not as a
management command:

```python
import psycopg

DSN = "postgresql://studysphere:studysphere@localhost:5432/studysphere"

with psycopg.connect(DSN) as conn:  # commits on success, rolls back on an exception
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, course_name FROM courses_course WHERE price < %s",
            (1000,),
        )
        for course_id, name in cur.fetchall():
            print(course_id, name)
```

What to learn from it:

- **Parameters, never f-strings.** `%s` placeholders send the values separately from the SQL,
  which is what prevents SQL injection. Try
  `f"... WHERE course_name = '{name}'"` with a name containing `'` and watch it break.
- **Transactions.** The `with psycopg.connect(...)` block is one transaction. Raise an
  exception halfway through and check that nothing was written.
- **`COPY` for bulk loads.** It's far faster than inserting row by row:

  ```python
  with cur.copy("COPY courses_category (id, name, description) FROM STDIN") as copy:
      for cat in categories:
          copy.write_row((cat["id"], cat["name"], cat["description"]))
  ```

- **Stable ids.** Map each Mongo ObjectId to `uuid.uuid5(NAMESPACE, object_id)`, where
  `NAMESPACE` is a fixed UUID you pick. A re-run then produces the same ids, so it hits the
  primary key instead of creating duplicates. Pair that with
  `INSERT … ON CONFLICT DO NOTHING`, or truncate the tables before each run.

---

## Beyond the port: features only Postgres has

These are new features for StudySphere that the Mongo version doesn't have. Add
`django.contrib.postgres` to `INSTALLED_APPS` first.

### Course search with full-text search

```sql
SELECT course_name,
       ts_rank(to_tsvector('english', course_name || ' ' || course_description), q) AS rank
FROM courses_course, websearch_to_tsquery('english', 'react hooks') AS q
WHERE to_tsvector('english', course_name || ' ' || course_description) @@ q
ORDER BY rank DESC;
```

In Django, use `SearchVector`, `SearchQuery(..., search_type="websearch")` and `SearchRank`
from `django.contrib.postgres.search`. Add a `GinIndex` on the vector so searches don't scan
every row.

### Tag filtering with arrays

`Course.objects.filter(tag__contains=["python"])` becomes Postgres's `@>` operator. Add
`GinIndex(fields=["tag"])` (from `django.contrib.postgres.indexes`) and confirm with `EXPLAIN`
that Postgres uses it.

### Ranking courses within each category

```sql
SELECT category_id, course_name, students,
       RANK() OVER (PARTITION BY category_id ORDER BY students DESC) AS rank_in_category
FROM (
    SELECT c.category_id, c.course_name, COUNT(e.id) AS students
    FROM courses_course c
    LEFT JOIN courses_enrollment e ON e.course_id = c.id
    GROUP BY c.id
) AS per_course;
```

In Django:
`Window(expression=Rank(), partition_by=F("category"), order_by=F("students").desc())`.
