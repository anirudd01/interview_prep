# SQL — Query Answers

Companion to `questions/DSA_SQL.txt`, **Part C, query writing (51–70)**. Original numbering kept. DSA questions and the SQL reasoning/performance questions (71–87) are not included.

Dialect: **PostgreSQL**. Each answer states the table shape it assumes.

---

### 51. Count of orders per customer, including customers with zero orders.
```sql
-- customers(id, name), orders(id, customer_id, created_at, amount)
SELECT c.id, c.name, COUNT(o.id) AS order_count     -- COUNT(o.id), not COUNT(*), so zero-order customers get 0
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.name
ORDER BY order_count DESC;
```

### 52. Second highest salary. Then: Nth highest, handling ties.
```sql
-- employees(id, name, salary)

-- Second highest (distinct values; NULL if it doesn't exist)
SELECT MAX(salary) AS second_highest
FROM employees
WHERE salary < (SELECT MAX(salary) FROM employees);

-- Nth highest, ties handled with DENSE_RANK (N = 3 here); returns every employee on that salary
SELECT id, name, salary
FROM (
    SELECT id, name, salary,
           DENSE_RANK() OVER (ORDER BY salary DESC) AS rnk
    FROM employees
) t
WHERE rnk = 3;

-- Nth highest distinct salary value only
SELECT DISTINCT salary
FROM employees
ORDER BY salary DESC
OFFSET 3 - 1 LIMIT 1;
```

### 53. Find duplicate rows by (email) and keep only the newest.
```sql
-- users(id, email, created_at)

-- Find duplicates
SELECT email, COUNT(*) AS copies
FROM users
GROUP BY email
HAVING COUNT(*) > 1;

-- Delete all but the newest per email
DELETE FROM users
WHERE id IN (
    SELECT id
    FROM (
        SELECT id,
               ROW_NUMBER() OVER (PARTITION BY email ORDER BY created_at DESC, id DESC) AS rn
        FROM users
    ) t
    WHERE rn > 1
);

-- Afterwards, prevent it from happening again
CREATE UNIQUE INDEX CONCURRENTLY users_email_uq ON users (lower(email));
```

### 54. Total revenue per month for the last 12 months, with months having zero revenue shown as 0. (Generate_series.)
```sql
-- orders(id, created_at timestamptz, amount numeric)
WITH months AS (
    SELECT generate_series(
               date_trunc('month', now()) - interval '11 months',
               date_trunc('month', now()),
               interval '1 month'
           ) AS month
)
SELECT m.month::date AS month,
       COALESCE(SUM(o.amount), 0) AS revenue
FROM months m
LEFT JOIN orders o
       ON o.created_at >= m.month
      AND o.created_at <  m.month + interval '1 month'
GROUP BY m.month
ORDER BY m.month;
```

### 55. All users who signed up but never placed an order (3 ways: NOT IN, NOT EXISTS, LEFT JOIN NULL - and which is fastest and why).
```sql
-- users(id, ...), orders(id, user_id, ...)

-- 1. NOT IN  (DANGER: if any orders.user_id is NULL, this returns ZERO rows)
SELECT u.*
FROM users u
WHERE u.id NOT IN (SELECT o.user_id FROM orders o);

-- 2. NOT EXISTS  (preferred)
SELECT u.*
FROM users u
WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.id);

-- 3. LEFT JOIN ... IS NULL
SELECT u.*
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE o.id IS NULL;

-- Fastest: NOT EXISTS and LEFT JOIN/IS NULL both become an "anti-join" in Postgres (same plan, typically a
-- hash anti join, or a nested loop anti join using an index on orders(user_id)). NOT IN can't be turned into an
-- anti-join because of its NULL semantics; it uses a hashed subplan (or a per-row subplan when the subquery is
-- too big for work_mem, which is very slow) and is wrong if NULLs exist. Use NOT EXISTS, with an index on orders(user_id).
```

### 56. Running total of revenue per customer ordered by date. (Window function.)
```sql
-- orders(id, customer_id, created_at, amount)
SELECT customer_id,
       created_at,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY created_at, id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW   -- ROWS, so same-timestamp rows don't get summed together
       ) AS running_total
FROM orders
ORDER BY customer_id, created_at, id;
```

### 57. For each policy, get the most recent quote. (DISTINCT ON vs ROW_NUMBER.)
```sql
-- quotes(id, policy_id, created_at, premium)

-- Postgres-specific DISTINCT ON: simplest; keeps the first row per policy_id according to ORDER BY
SELECT DISTINCT ON (policy_id) *
FROM quotes
ORDER BY policy_id, created_at DESC, id DESC;

-- Portable ROW_NUMBER: works in any SQL database, and is easy to change to "top 3 per policy" (rn <= 3)
SELECT *
FROM (
    SELECT q.*,
           ROW_NUMBER() OVER (PARTITION BY policy_id ORDER BY created_at DESC, id DESC) AS rn
    FROM quotes q
) t
WHERE rn = 1;

-- Index that serves both
CREATE INDEX ON quotes (policy_id, created_at DESC, id DESC);

-- When there are many quotes per policy and a policies table exists, a LATERAL top-1 per policy is often fastest
SELECT p.id AS policy_id, q.*
FROM policies p
CROSS JOIN LATERAL (
    SELECT * FROM quotes q
    WHERE q.policy_id = p.id
    ORDER BY created_at DESC, id DESC
    LIMIT 1
) q;
```

### 58. Month-over-month growth percentage per product.
```sql
-- order_items(order_id, product_id, amount, created_at)
WITH monthly AS (
    SELECT product_id,
           date_trunc('month', created_at)::date AS month,
           SUM(amount) AS revenue
    FROM order_items
    GROUP BY product_id, date_trunc('month', created_at)
)
SELECT product_id,
       month,
       revenue,
       LAG(revenue) OVER (PARTITION BY product_id ORDER BY month) AS prev_revenue,
       ROUND(
           100.0 * (revenue - LAG(revenue) OVER (PARTITION BY product_id ORDER BY month))
                 / NULLIF(LAG(revenue) OVER (PARTITION BY product_id ORDER BY month), 0),
           2
       ) AS mom_growth_pct                                    -- NULLIF avoids division by zero
FROM monthly
ORDER BY product_id, month;
-- Note: if a product has a month with no sales, LAG compares with the last month that had sales.
-- To compare strictly with the previous calendar month, generate the months first (as in Q54) and LEFT JOIN.
```

### 59. 7-day rolling average of daily active users.
```sql
-- events(user_id, event_time)
WITH days AS (
    SELECT generate_series(
               (SELECT MIN(event_time)::date FROM events),
               current_date,
               interval '1 day'
           )::date AS day
),
daily AS (
    SELECT d.day, COUNT(DISTINCT e.user_id) AS dau
    FROM days d
    LEFT JOIN events e
           ON e.event_time >= d.day
          AND e.event_time <  d.day + 1
    GROUP BY d.day
)
SELECT day,
       dau,
       ROUND(AVG(dau) OVER (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS dau_7d_avg
FROM daily
ORDER BY day;
-- The days CTE ensures days with zero users count as 0; otherwise "6 PRECEDING rows" could span more than 7 days.
```

### 60. Find users who performed event A then event B within 30 minutes.
```sql
-- events(user_id, event_type, event_time)
SELECT DISTINCT a.user_id
FROM events a
JOIN events b
  ON b.user_id    = a.user_id
 AND b.event_type = 'B'
 AND b.event_time >  a.event_time
 AND b.event_time <= a.event_time + interval '30 minutes'
WHERE a.event_type = 'A';

-- Index that makes it fast
CREATE INDEX ON events (user_id, event_type, event_time);
```

### 61. Rank quotes within each broker by premium, dense_rank vs rank vs row_number - explain the difference with a tie.
```sql
-- quotes(id, broker_id, premium)
SELECT broker_id,
       id,
       premium,
       ROW_NUMBER() OVER w AS row_num,
       RANK()       OVER w AS rnk,
       DENSE_RANK() OVER w AS dense_rnk
FROM quotes
WINDOW w AS (PARTITION BY broker_id ORDER BY premium DESC)
ORDER BY broker_id, premium DESC;

-- Example for one broker, with a tie at 900:
-- premium | row_number | rank | dense_rank
--   1000  |     1      |  1   |     1
--    900  |     2      |  2   |     2
--    900  |     3      |  2   |     2      <- tie
--    800  |     4      |  4   |     3
-- ROW_NUMBER: always unique (the tie order is arbitrary unless you add a tiebreaker column like id).
-- RANK: ties share a rank, then it skips (2, 2, 4).
-- DENSE_RANK: ties share a rank, no gaps (2, 2, 3).
```

### 62. Sessionize an event stream: group events into sessions with a 30-minute inactivity gap. (LAG + cumulative sum.)
```sql
-- events(user_id, event_time, ...)
WITH flagged AS (
    SELECT *,
           CASE
               WHEN LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time) IS NULL
                 OR event_time - LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time) > interval '30 minutes'
               THEN 1 ELSE 0
           END AS is_new_session
    FROM events
),
sessioned AS (
    SELECT *,
           SUM(is_new_session) OVER (PARTITION BY user_id ORDER BY event_time
                                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_no
    FROM flagged
)
SELECT user_id,
       session_no,
       MIN(event_time) AS session_start,
       MAX(event_time) AS session_end,
       COUNT(*)        AS events_in_session
FROM sessioned
GROUP BY user_id, session_no
ORDER BY user_id, session_no;
```

### 63. Given a bitemporal table (valid_from, valid_to, recorded_at), get the value "as known on date X for effective date Y". (Insurance-relevant.)
```sql
-- rate_history(entity_id, value, valid_from, valid_to, recorded_at, superseded_at)
--   valid_from / valid_to       = business (effective) time, valid_to exclusive, NULL = open-ended
--   recorded_at / superseded_at = system (knowledge) time, superseded_at NULL = still current knowledge
-- :known_on = date X (what we knew at that moment), :effective = date Y (the date the value applies to)
SELECT entity_id, value
FROM rate_history
WHERE entity_id   = :entity_id
  AND valid_from <= :effective
  AND (valid_to IS NULL OR valid_to > :effective)
  AND recorded_at <= :known_on
  AND (superseded_at IS NULL OR superseded_at > :known_on);

-- If the table has only recorded_at (no superseded_at): pick the latest record known at X covering Y
SELECT DISTINCT ON (entity_id) entity_id, value
FROM rate_history
WHERE entity_id   = :entity_id
  AND valid_from <= :effective
  AND (valid_to IS NULL OR valid_to > :effective)
  AND recorded_at <= :known_on
ORDER BY entity_id, recorded_at DESC;
```

### 64. Pivot: revenue by product as columns, per month as rows.
```sql
-- order_items(product_id, amount, created_at); products known in advance
SELECT date_trunc('month', created_at)::date AS month,
       SUM(amount) FILTER (WHERE product_id = 'PROPERTY') AS property,
       SUM(amount) FILTER (WHERE product_id = 'MARINE')   AS marine,
       SUM(amount) FILTER (WHERE product_id = 'CASUALTY') AS casualty,
       SUM(amount)                                       AS total
FROM order_items
GROUP BY 1
ORDER BY 1;

-- Portable version (works outside Postgres): SUM(CASE WHEN product_id = 'PROPERTY' THEN amount ELSE 0 END)
-- Dynamic set of products: tablefunc's crosstab(), or pivot in the application / BI tool.
```

### 65. Query a JSONB column: find all records where metadata->tags contains 'urgent', and write the index that makes it fast.
```sql
-- tickets(id, metadata jsonb)   e.g. metadata = {"tags": ["urgent", "renewal"], ...}

-- Containment query (uses a GIN index)
SELECT *
FROM tickets
WHERE metadata @> '{"tags": ["urgent"]}';

-- Index: GIN with jsonb_path_ops (smaller and faster, supports @>)
CREATE INDEX CONCURRENTLY tickets_metadata_gin ON tickets USING gin (metadata jsonb_path_ops);

-- Alternative: index only the tags array, and query it the same way
CREATE INDEX CONCURRENTLY tickets_tags_gin ON tickets USING gin ((metadata -> 'tags'));
SELECT * FROM tickets WHERE metadata -> 'tags' @> '"urgent"';

-- Note: metadata->'tags' ? 'urgent' also works, but needs the default jsonb_ops GIN operator class.
```

### 66. Find gaps and islands: consecutive days a user was active.
```sql
-- activity(user_id, activity_date date)   -- possibly several rows per day
WITH days AS (
    SELECT DISTINCT user_id, activity_date
    FROM activity
),
grouped AS (
    SELECT user_id,
           activity_date,
           activity_date - (ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY activity_date))::int AS grp
           -- consecutive dates minus a consecutive row number give the same constant -> same island
    FROM days
)
SELECT user_id,
       MIN(activity_date) AS streak_start,
       MAX(activity_date) AS streak_end,
       COUNT(*)           AS streak_days
FROM grouped
GROUP BY user_id, grp
ORDER BY user_id, streak_start;

-- Longest streak per user: wrap the above and take MAX(streak_days) per user_id.
```

### 67. Recursive CTE: full org hierarchy under a manager, with depth.
```sql
-- employees(id, name, manager_id)
WITH RECURSIVE org AS (
    SELECT id, name, manager_id, 0 AS depth, ARRAY[id] AS path
    FROM employees
    WHERE id = :manager_id                      -- the starting manager

    UNION ALL

    SELECT e.id, e.name, e.manager_id, o.depth + 1, o.path || e.id
    FROM employees e
    JOIN org o ON e.manager_id = o.id
    WHERE NOT e.id = ANY(o.path)                -- guard against cycles in bad data
)
SELECT id, name, manager_id, depth
FROM org
WHERE depth > 0                                 -- exclude the manager themself
ORDER BY path;
```

### 68. Deduplicate 50M rows in place, keeping the earliest, without locking the table for more than a few seconds.
```sql
-- events(id bigint PK, dedupe_key text, created_at timestamptz, ...)

-- 1. Index the duplicate key once, without blocking writes
CREATE INDEX CONCURRENTLY events_dedupe_idx ON events (dedupe_key, created_at, id);

-- 2. Record which ids to delete (read-only work, no locks on the live rows)
CREATE TABLE events_to_delete AS
SELECT id
FROM (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY dedupe_key ORDER BY created_at, id) AS rn
    FROM events
) t
WHERE rn > 1;
CREATE INDEX ON events_to_delete (id);

-- 3. Delete in small batches: each batch is its own short transaction (run in a loop from a script/procedure
--    until 0 rows are deleted, with a short sleep between batches to limit replication lag and vacuum load)
WITH batch AS (
    DELETE FROM events_to_delete
    WHERE id IN (SELECT id FROM events_to_delete LIMIT 10000)
    RETURNING id
)
DELETE FROM events e
USING batch b
WHERE e.id = b.id;

-- 4. Stop new duplicates: build the unique index without blocking writes.
--    Run this only after step 3 has finished, and after cleaning any duplicates inserted during the run
--    (re-run steps 2-3 for rows created since step 2 started). If a duplicate still exists, the build fails and
--    leaves an INVALID index that you must drop before retrying.
CREATE UNIQUE INDEX CONCURRENTLY events_dedupe_key_uq ON events (dedupe_key);

-- 5. Reclaim space and refresh statistics
VACUUM (ANALYZE) events;
DROP TABLE events_to_delete;
DROP INDEX CONCURRENTLY events_dedupe_idx;   -- if no longer needed
```

### 69. Given a table of interval-based rates, find overlapping intervals per product.
```sql
-- rates(id, product_id, valid_from date, valid_to date)   -- valid_to exclusive, NULL = open-ended

-- Self-join: every overlapping pair (a.id < b.id lists each pair once)
SELECT a.product_id, a.id AS rate_a, b.id AS rate_b,
       a.valid_from AS a_from, a.valid_to AS a_to,
       b.valid_from AS b_from, b.valid_to AS b_to
FROM rates a
JOIN rates b
  ON a.product_id = b.product_id
 AND a.id < b.id
 AND a.valid_from < COALESCE(b.valid_to, 'infinity')
 AND b.valid_from < COALESCE(a.valid_to, 'infinity');

-- Same check written with range types
SELECT a.product_id, a.id, b.id
FROM rates a
JOIN rates b
  ON a.product_id = b.product_id
 AND a.id < b.id
 AND daterange(a.valid_from, a.valid_to) && daterange(b.valid_from, b.valid_to);

-- Prevent overlaps in future with an exclusion constraint
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE rates
  ADD CONSTRAINT rates_no_overlap
  EXCLUDE USING gist (product_id WITH =, daterange(valid_from, valid_to) WITH &&);
```

### 70. Compute funnel conversion across 5 steps in a single pass.
```sql
-- events(user_id, event_type, event_time)
-- Steps in order: visit -> signup -> quote_started -> quote_completed -> policy_bound
WITH per_user AS (
    SELECT user_id,
           MIN(event_time) FILTER (WHERE event_type = 'visit')           AS t1,
           MIN(event_time) FILTER (WHERE event_type = 'signup')          AS t2,
           MIN(event_time) FILTER (WHERE event_type = 'quote_started')   AS t3,
           MIN(event_time) FILTER (WHERE event_type = 'quote_completed') AS t4,
           MIN(event_time) FILTER (WHERE event_type = 'policy_bound')    AS t5
    FROM events
    WHERE event_type IN ('visit', 'signup', 'quote_started', 'quote_completed', 'policy_bound')
    GROUP BY user_id
),
steps AS (                       -- a step counts only if every earlier step happened, and before it
    SELECT user_id,
           t1 IS NOT NULL                                                     AS s1,
           t1 IS NOT NULL AND t2 > t1                                         AS s2,
           t1 IS NOT NULL AND t2 > t1 AND t3 > t2                             AS s3,
           t1 IS NOT NULL AND t2 > t1 AND t3 > t2 AND t4 > t3                 AS s4,
           t1 IS NOT NULL AND t2 > t1 AND t3 > t2 AND t4 > t3 AND t5 > t4     AS s5
    FROM per_user
)
SELECT COUNT(*) FILTER (WHERE s1) AS step1_visit,
       COUNT(*) FILTER (WHERE s2) AS step2_signup,
       COUNT(*) FILTER (WHERE s3) AS step3_quote_started,
       COUNT(*) FILTER (WHERE s4) AS step4_quote_completed,
       COUNT(*) FILTER (WHERE s5) AS step5_policy_bound,
       ROUND(100.0 * COUNT(*) FILTER (WHERE s5) / NULLIF(COUNT(*) FILTER (WHERE s1), 0), 2) AS overall_conversion_pct
FROM steps;
-- Simplification: first occurrence of each event per user. Strict per-attempt funnels need sessionizing first (Q62).
```
