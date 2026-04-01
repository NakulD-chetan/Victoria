# 05 — Delta Lake Internals

> **One-line:** Delta Lake adds **ACID transactions**, **time travel**, and **schema enforcement** to Parquet files using a **JSON transaction log** (`_delta_log/`) — turning a data lake into a **lakehouse**.

---

## 1. Delta Lake = Parquet + Transaction Log

```
Regular Parquet directory:
  /orders/
    part-00000.parquet
    part-00001.parquet
    part-00002.parquet
    (No coordination, no ACID, no versioning)

Delta Lake directory:
  /orders/
    part-00000.snappy.parquet
    part-00001.snappy.parquet
    part-00002.snappy.parquet
    _delta_log/                     ← THIS IS THE MAGIC
      00000000000000000000.json     (version 0 — initial commit)
      00000000000000000001.json     (version 1 — next commit)
      00000000000000000002.json     (version 2 — next commit)
      00000000000000000010.checkpoint.parquet (checkpoint every 10 versions)
```

**The data files are standard Parquet.** Delta Lake's intelligence is entirely in the `_delta_log/` directory.

---

## 2. Transaction Log — The Core Innovation

### What Each Log Entry Contains

```json
// _delta_log/00000000000000000001.json
{
  "commitInfo": {
    "timestamp": 1711900000000,
    "operation": "WRITE",
    "operationParameters": {"mode": "Append"}
  }
}
{"add": {
    "path": "part-00003.snappy.parquet",
    "size": 134217728,
    "modificationTime": 1711900000000,
    "dataChange": true,
    "stats": "{\"numRecords\":100000, \"minValues\":{\"amount\":1}, \"maxValues\":{\"amount\":99999}}"
  }
}
{"remove": {
    "path": "part-00001.snappy.parquet",
    "deletionTimestamp": 1711900000000,
    "dataChange": true
  }
}
```

### Log Entry Actions

| Action | Meaning |
|--------|---------|
| **add** | New Parquet file is part of the table |
| **remove** | Parquet file is no longer part of the table (logically deleted) |
| **metaData** | Schema change, partition columns change, table properties |
| **txn** | Application-level transaction ID (for idempotent writes) |
| **protocol** | Reader/writer protocol version requirements |
| **commitInfo** | Who, when, what operation |

### How a Read Works

```
Reader wants current state of table:

1. Find latest checkpoint (e.g., version 10 checkpoint)
2. Read checkpoint → get baseline file list
3. Read log entries 11, 12, 13, ... up to latest version
4. Apply adds and removes → get current list of valid Parquet files
5. Read only those Parquet files

Current table state = Checkpoint + subsequent log entries
```

---

## 3. ACID Guarantees — How They Work

| Property | How Delta Achieves It |
|----------|----------------------|
| **Atomicity** | Each commit is a single JSON log file — either it's written or it's not |
| **Consistency** | Schema enforcement — rejects writes that don't match schema |
| **Isolation** | Optimistic concurrency — writers don't block readers. Conflict resolution on commit |
| **Durability** | Files on cloud storage (S3/ADLS) with built-in durability |

### Optimistic Concurrency Control

```
Writer A: reads version 5 → does work → tries to commit version 6
Writer B: reads version 5 → does work → tries to commit version 6

Who wins? First to write 00000000000000000006.json to storage.

Loser: Reads version 6 → checks for conflicts:
  - If no conflict (different partitions) → re-commit as version 7
  - If conflict (same files modified) → FAIL → retry or error
```

**Interview tip:** "Delta Lake uses **optimistic concurrency** — it assumes conflicts are rare. Both readers and writers can proceed simultaneously. Conflicts are detected only at commit time."

---

## 4. Time Travel

```python
# Read version 5
df = spark.read.format("delta").option("versionAsOf", 5).load("/orders/")

# Read as of timestamp
df = spark.read.format("delta").option("timestampAsOf", "2024-01-15").load("/orders/")

# See table history
from delta.tables import DeltaTable
dt = DeltaTable.forPath(spark, "/orders/")
dt.history().show()
```

### How Time Travel Works

```
Want version 5?
  → Read log entries 0-5 (or checkpoint + entries up to 5)
  → Build file list as of version 5
  → Read those Parquet files (which still exist on disk)
  
Files from old versions are NOT deleted until VACUUM runs.
```

---

## 5. OPTIMIZE — File Compaction

### The Small File Problem

```
Before OPTIMIZE:
  /orders/
    part-00000.parquet  (1 MB)
    part-00001.parquet  (2 MB)
    part-00002.parquet  (500 KB)
    part-00003.parquet  (3 MB)
    ... (thousands of tiny files from streaming appends)

After OPTIMIZE:
  /orders/
    part-00000-compacted.parquet  (128 MB)
    part-00001-compacted.parquet  (128 MB)
    (old small files logically removed in log, physically removed by VACUUM)
```

```sql
OPTIMIZE orders;
OPTIMIZE orders WHERE date = '2024-01-15';
```

---

## 6. Z-ORDER — Multi-Dimensional Clustering

### Problem

```
Table has queries filtering on BOTH customer_id AND order_date.
Parquet/Delta can only sort by one column → other column's min/max ranges overlap.
```

### Z-Order Solution

```
Z-ORDER interleaves bits of multiple columns into a single sort order:

customer_id: [1, 2, 3, 4]    →  Z-value: interleave bits
order_date:  [D1, D2, D3, D4]     of both columns

Result: Data is clustered in BOTH dimensions simultaneously.
Queries filtering on EITHER column (or both) get good data skipping.
```

```sql
OPTIMIZE orders ZORDER BY (customer_id, order_date);
```

### Z-Order vs Clustering Key (Snowflake)

| Feature | Delta Z-Order | Snowflake Clustering |
|---------|--------------|---------------------|
| **When** | Manual (`OPTIMIZE ... ZORDER BY`) | Automatic (background reclustering) |
| **Cost** | Compute cost of rewriting files | Automatic compute cost (credits) |
| **Columns** | 2-4 columns recommended | 2-4 columns recommended |
| **Monitoring** | `DESCRIBE DETAIL` | `SYSTEM$CLUSTERING_INFORMATION` |

---

## 7. VACUUM — Physical File Cleanup

```sql
-- Remove files older than 7 days that are no longer in current table state
VACUUM orders RETAIN 168 HOURS;

-- Default retention: 7 days
-- WARNING: After VACUUM, time travel beyond retention is impossible!
```

### VACUUM vs Time Travel Tension

```
VACUUM RETAIN 24 HOURS  → Can only time-travel 24 hours back
VACUUM RETAIN 720 HOURS → Can time-travel 30 days back, but storage cost higher

Trade-off: Storage cost ↔ Time travel window
```

**Interview tip:** "VACUUM and time travel are in **tension**. Aggressive VACUUM saves storage but destroys history. Configure retention based on business requirements — typically 7-30 days."

---

## 8. Schema Enforcement & Evolution

| Feature | Behavior |
|---------|----------|
| **Schema enforcement** | Rejects writes that don't match table schema (extra columns, wrong types) |
| **Schema evolution** | Explicitly allow new columns with `mergeSchema` option |
| **Auto merge** | `spark.databricks.delta.schema.autoMerge.enabled = true` |

```python
# This FAILS — new column "discount" not in schema
df_with_discount.write.format("delta").mode("append").save("/orders/")

# This WORKS — merge schema
df_with_discount.write.format("delta") \
    .mode("append") \
    .option("mergeSchema", "true") \
    .save("/orders/")
```

---

## 9. MERGE (Upsert) — SCD and CDC Pattern

```sql
MERGE INTO target_orders t
USING source_changes s
ON t.order_id = s.order_id
WHEN MATCHED AND s.op = 'update' THEN
    UPDATE SET t.amount = s.amount, t.status = s.status
WHEN MATCHED AND s.op = 'delete' THEN
    DELETE
WHEN NOT MATCHED THEN
    INSERT (order_id, amount, status) VALUES (s.order_id, s.amount, s.status);
```

**This is how CDC events (from Debezium) are applied to Delta tables** — one MERGE handles inserts, updates, and deletes.

---

## 10. Common Interview Questions

| Question | Key Points |
|----------|------------|
| "What is Delta Lake?" | ACID layer on top of Parquet using JSON transaction log (`_delta_log/`) |
| "How does the transaction log work?" | JSON files with add/remove actions. Checkpoints every 10 versions. Read = checkpoint + subsequent logs |
| "How does Delta achieve ACID?" | Atomicity: atomic log writes. Isolation: optimistic concurrency. Consistency: schema enforcement |
| "What is OPTIMIZE?" | File compaction — merges small Parquet files into larger optimal-sized files |
| "What is Z-ORDER?" | Multi-dimensional clustering — interleaves bits of multiple columns for better data skipping on any |
| "VACUUM vs Time Travel?" | VACUUM deletes old files → limits time travel window. Trade-off: storage vs history |
| "How does MERGE work?" | Match source with target on key → UPDATE/DELETE matched rows, INSERT unmatched |
| "Delta vs Iceberg?" | Delta: Databricks-native, Z-order. Iceberg: engine-neutral, hidden partitioning |

---

## Key Takeaways

- **Delta Lake** = Parquet files + `_delta_log/` (JSON transaction log). Data is standard Parquet.
- **Transaction log**: JSON files with add/remove/metadata actions. Checkpoints every 10 versions.
- **ACID**: Atomic commits, schema enforcement, optimistic concurrency, cloud storage durability.
- **Time travel**: Read any historical version. Limited by VACUUM retention.
- **OPTIMIZE**: Compacts small files. **Z-ORDER**: Multi-column clustering for data skipping.
- **VACUUM**: Physically deletes old files. Tension with time travel — balance retention period.
- **MERGE**: Upsert pattern for CDC — handles INSERT/UPDATE/DELETE in one statement.
- **Schema enforcement** prevents bad writes. **Schema evolution** allows controlled changes.

---
