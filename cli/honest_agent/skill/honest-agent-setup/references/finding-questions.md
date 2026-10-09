# Finding what to evaluate

Skip this if the user already knows their questions. Otherwise, the best evals are the
questions people really ask. Places to look, roughly in order of effort:

1. **Ask the team:** the questions they ask the agent or an analyst most often, and the
   ones where a wrong answer would hurt.
2. **Dashboards and reports** people rely on: each headline number is a question
   ("revenue last month", "active customers").
3. **The warehouse's query history:** the most frequent queries, and the tables they
   read, show what the business actually looks at.

## Query history: starting points

These are pointers to check against the vendor's current docs, not tested SQL. The
user runs any query and shares what they choose; you never run it. Querying history
often needs extra privileges; if the user doesn't have them, go back to 1 and 2.

- **Snowflake:** `snowflake.account_usage.query_history` (up to a year, with some
  delay; needs access to the `snowflake` database), or the
  `information_schema.query_history()` table function (recent days only). For which
  tables were read, `snowflake.account_usage.access_history` (Enterprise edition).
- **BigQuery:** the region's `INFORMATION_SCHEMA.JOBS` views (e.g.
  `` `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT ``), with `referenced_tables` per job.
- **Databricks:** the `system.query.history` system table, if system tables are enabled.
- **Amazon Redshift:** `SYS_QUERY_HISTORY` (and `STL_QUERY` on provisioned clusters).
- **PostgreSQL:** the `pg_stat_statements` extension, if installed: normalized queries
  with call counts.
- **MotherDuck:** check MotherDuck's docs for its query history views.
- **DuckDB (a local file):** no query history is kept; use 1 and 2.

A useful first query groups recent successful `select`s by their text (or by the
tables they read), counts them, and keeps the top 20 to 50. Filter out the agent's own
service user and automated jobs if the user can tell them apart.

From the results, pick a handful of questions that matter to the business, then turn
each one into the question a person would type, in their words.
