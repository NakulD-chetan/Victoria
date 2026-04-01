# 06 — Apache Iceberg Internals

> **One-line:** Iceberg is an **open table format** with a **metadata tree** (catalog → metadata files → manifest lists → manifest files → data files) that enables **hidden partitioning**, **snapshot isolation**, and true **engine-neutrality** — the fastest-growing table format in 2026.

---

## 1. Why Iceberg is Taking Over

| Problem with Hive-style tables | Iceberg Solution |
|-------------------------------|-----------------|
| Partitions are directory paths → users must know structure | **Hidden partitioning** — engine handles it transparently |
| Listing files is slow (S3 LIST is expensive) | **Metadata tree** — no file listing needed |
| No ACID — concurrent writes corrupt data | **Snapshot isolation** — readers never see partial writes |
| Schema changes risky | **Safe schema evolution** — add, drop, rename, reorder columns |
| Partition changes require rewrite | **Partition evolution** — change partitioning without rewriting data |

---

## 2. Iceberg Metadata Tree — The Architecture

```
┌─────────────────────────────────────────────────────┐
│                    CATALOG                           │
│  (Hive Metastore / Glue / REST / Nessie)            │
│  Points to → current metadata file location          │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│              METADATA FILE (JSON)                    │
│  - Table schema (current + history)                  │
│  - Partition spec (current + history)                │
│  - Current snapshot ID                               │
│  - Snapshot list (all versions)                      │
│  - Sort order                                        │
│  - Properties                                        │
└────────────────────┬────────────────────────────────┘
                     │ current snapshot
                     ▼
┌─────────────────────────────────────────────────────┐
│           MANIFEST LIST (Avro file)                  │
│  - List of manifest files for this snapshot          │
│  - Per-manifest: partition range, file count,        │
│    added/deleted counts                              │
└────────────────────┬────────────────────────────────┘
                     │ points to manifests
            ┌────────┴────────┐
            ▼                 ▼
┌───────────────────┐ ┌───────────────────┐
│ MANIFEST FILE 1   │ │ MANIFEST FILE 2   │
│ (Avro file)       │ │ (Avro file)       │
│                   │ │                   │
│ Data file entries: │ │ Data file entries: │
│ - file path       │ │ - file path       │
│ - partition vals  │ │ - partition vals  │
│ - record count    │ │ - record count    │
│ - column stats    │ │ - column stats    │
│   (min, max,      │ │   (min, max,      │
│    null count)    │ │    null count)    │
└────────┬──────────┘ └────────┬──────────┘
         │                     │
    ┌────┴────┐           ┌────┴────┐
    ▼         ▼           ▼         ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Parquet │ │Parquet │ │Parquet │ │Parquet │
│File 1  │ │File 2  │ │File 3  │ │File 4  │
└────────┘ └────────┘ └────────┘ └────────┘
```

### Why This Tree Structure Matters

| Benefit | How |
|---------|-----|
| **No file listing** | Manifest files already list all data files → skip expensive S3 LIST |
| **Fast planning** | Manifest-level stats → skip entire manifests. File-level stats → skip files |
| **Snapshot isolation** | Each snapshot points to its own manifest list → readers see consistent state |
| **Incremental processing** | Compare manifest lists between snapshots → find only changed files |

**Interview tip:** "Iceberg's metadata tree eliminates **S3 LIST calls** — the biggest performance bottleneck for Hive-style tables on object storage. Instead of listing millions of files, Iceberg reads a few manifest files."

---

## 3. Hidden Partitioning

### Hive-Style Partitioning (Old Way)

```sql
-- Users MUST know partition structure
SELECT * FROM events WHERE year=2024 AND month=01 AND day=15;

-- This DOES NOT use partitions (full scan!)
SELECT * FROM events WHERE event_date = '2024-01-15';

-- Users must manually convert dates to partition columns
```

### Iceberg Hidden Partitioning (New Way)

```sql
-- Define partition transform ONCE at table creation
CREATE TABLE events (
    event_id BIGINT,
    event_date TIMESTAMP,
    user_id BIGINT,
    action STRING
) USING iceberg
PARTITIONED BY (days(event_date));

-- Users just query naturally — Iceberg handles partition pruning
SELECT * FROM events WHERE event_date = '2024-01-15';
-- Iceberg automatically translates to correct partition → efficient scan
```

### Supported Partition Transforms

| Transform | Input | Partition Value | Example |
|-----------|-------|----------------|---------|
| `year(ts)` | Timestamp | Year integer | `2024` |
| `month(ts)` | Timestamp | Year-month | `2024-01` |
| `day(ts)` | Timestamp | Date | `2024-01-15` |
| `hour(ts)` | Timestamp | Date-hour | `2024-01-15-08` |
| `bucket(N, col)` | Any | Hash bucket 0 to N-1 | `bucket(16, user_id)` → `7` |
| `truncate(L, col)` | String/Int | Truncated value | `truncate(3, city)` → `"Mum"` |
| `identity(col)` | Any | Same value | Same as Hive-style |

---

## 4. Partition Evolution

```sql
-- Start with monthly partitioning
CREATE TABLE logs (...) PARTITIONED BY (month(ts));

-- Traffic grows → need daily partitioning
ALTER TABLE logs ADD PARTITION FIELD day(ts);

-- Old data stays monthly partitioned
-- New data is daily partitioned
-- Iceberg handles BOTH transparently in queries!
-- NO DATA REWRITE needed
```

**Interview line:** "Iceberg's partition evolution lets you change partitioning strategy **without rewriting existing data**. Old data keeps old partitioning, new data uses new partitioning. Queries work across both seamlessly."

---

## 5. Snapshot Isolation & Time Travel

```
Snapshot 1 (version 1): [file_A, file_B]
    │
    ├── Writer adds file_C, removes file_A
    │
Snapshot 2 (version 2): [file_B, file_C]
    │
    ├── Writer adds file_D
    │
Snapshot 3 (version 3): [file_B, file_C, file_D]

Reader at any point sees a CONSISTENT snapshot.
Reader at snapshot 1 → sees file_A + file_B (even if snapshot 3 is current).
Writers don't block readers. Readers don't block writers.
```

```sql
-- Time travel by snapshot ID
SELECT * FROM orders VERSION AS OF 12345;

-- Time travel by timestamp
SELECT * FROM orders TIMESTAMP AS OF '2024-01-15 10:00:00';

-- See snapshot history
SELECT * FROM orders.snapshots;
```

---

## 6. Schema Evolution

| Operation | Supported? | Detail |
|-----------|-----------|--------|
| **Add column** | Yes | New column has NULL in old data files (no rewrite) |
| **Drop column** | Yes | Column ignored in reads (no rewrite) |
| **Rename column** | Yes | Uses column IDs, not names (unique to Iceberg) |
| **Reorder columns** | Yes | Metadata-only change |
| **Widen type** | Yes | int → long, float → double |
| **Change required ↔ optional** | Yes | Make column nullable or required |

### Column IDs — Why Iceberg is Better

```
Parquet matches columns by NAME:
  Rename "city" to "location" → treated as DROP "city" + ADD "location" → data loss!

Iceberg matches columns by ID:
  Column "city" has ID=5. Rename to "location" → still ID=5 → data preserved!
```

---

## 7. Iceberg vs Delta Lake

| Feature | Iceberg | Delta Lake |
|---------|---------|------------|
| **Engine support** | Spark, Flink, Trino, Presto, Hive, Dremio, Snowflake | Primarily Spark/Databricks |
| **Partitioning** | Hidden (transforms) + evolution | Standard directory partitioning |
| **Schema evolution** | Column IDs (rename-safe) | Column names (rename-risky) |
| **Metadata** | Tree (catalog→metadata→manifests→data) | Transaction log (JSON files) |
| **File listing** | No S3 LIST needed (manifest has paths) | No S3 LIST (log has paths) |
| **Clustering** | Sort order in metadata | Z-ORDER |
| **Governance** | Multi-engine catalogs (Nessie, REST) | Unity Catalog (Databricks) |
| **Community** | Apache, vendor-neutral | Databricks-driven, Linux Foundation |
| **Adoption 2026** | Growing fastest (Snowflake, AWS adopted) | Strong in Databricks ecosystem |

**Interview line:** "Choose Iceberg for **engine-neutral** environments (Snowflake + Spark + Trino). Choose Delta for **Databricks-heavy** environments. Both solve the same core problems."

---

## 8. Maintenance Operations

| Operation | What | Command |
|-----------|------|---------|
| **Expire snapshots** | Remove old snapshots (like VACUUM) | `CALL system.expire_snapshots('orders', TIMESTAMP '...')` |
| **Remove orphan files** | Clean up unreferenced data files | `CALL system.remove_orphan_files('orders')` |
| **Rewrite data files** | Compact small files (like OPTIMIZE) | `CALL system.rewrite_data_files('orders')` |
| **Rewrite manifests** | Compact manifest files | `CALL system.rewrite_manifests('orders')` |

---

## 9. Common Interview Questions

| Question | Key Points |
|----------|------------|
| "What is Apache Iceberg?" | Open table format with metadata tree, hidden partitioning, snapshot isolation, schema evolution |
| "Explain Iceberg's metadata structure" | Catalog → Metadata file → Manifest list → Manifest files → Data files (Parquet) |
| "What is hidden partitioning?" | Partition transforms (day, month, bucket) — users query naturally, Iceberg prunes |
| "What is partition evolution?" | Change partitioning without rewriting data — old and new partitioning coexist |
| "Iceberg vs Delta Lake?" | Iceberg: engine-neutral, hidden partitioning, column IDs. Delta: Databricks ecosystem, Z-ORDER |
| "How does schema evolution work in Iceberg?" | Column IDs enable safe rename. Add/drop/reorder are metadata-only changes |
| "Why no S3 LIST in Iceberg?" | Manifest files contain exact file paths — no need to list directory |

---

## Key Takeaways

- **Iceberg** = open table format with **metadata tree** architecture (catalog → metadata → manifests → data).
- **Hidden partitioning**: users query naturally; Iceberg handles partition pruning via transforms.
- **Partition evolution**: change partitioning without rewriting data — old and new coexist.
- **Column IDs**: enable safe rename/reorder — unlike Parquet/Delta which match by name.
- **Snapshot isolation**: each snapshot is a consistent view; readers never see partial writes.
- **Engine-neutral**: works with Spark, Flink, Trino, Presto, Snowflake, Hive — biggest differentiator vs Delta.
- **Fastest-growing** table format in 2026 — Snowflake, AWS, Netflix, Apple have adopted it.

---
