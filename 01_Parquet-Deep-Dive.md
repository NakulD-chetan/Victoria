# 01 — Parquet Deep Dive

> **One-line:** Parquet is an **open-source columnar** storage format that stores data in **row groups → column chunks → pages** with embedded statistics — enabling Spark to skip irrelevant data and read only the columns you need.

---

## 1. Why Parquet is the King of Analytics

| Reason | Detail |
|--------|--------|
| **Spark's default** | `df.write.save()` defaults to Parquet |
| **Column pruning** | `SELECT name, age` reads only 2 columns, ignores 100 others |
| **Predicate pushdown** | `WHERE age > 30` skips entire row groups using min/max stats |
| **Compression** | Same-type values in columns compress 5-10x better than row formats |
| **Ecosystem** | Supported by Spark, Hive, Presto, Trino, Athena, BigQuery, Snowflake, DuckDB |

---

## 2. Parquet File Internal Structure

This is the **most asked** interview question about Parquet — know this diagram by heart.

```
┌────────────────────────────────────────────────┐
│                 PARQUET FILE                     │
│                                                  │
│  ┌──────────────── Row Group 1 ──────────────┐  │
│  │                                            │  │
│  │  ┌─ Column Chunk: "name" ──────────────┐  │  │
│  │  │  Page 1 (data page)                  │  │  │
│  │  │  Page 2 (data page)                  │  │  │
│  │  │  [Dictionary Page — if dict encoding]│  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │                                            │  │
│  │  ┌─ Column Chunk: "age" ───────────────┐  │  │
│  │  │  Page 1 (data page)                  │  │  │
│  │  │  Page 2 (data page)                  │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │                                            │  │
│  │  ┌─ Column Chunk: "city" ──────────────┐  │  │
│  │  │  Page 1 (data page)                  │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │                                            │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌──────────────── Row Group 2 ──────────────┐  │
│  │  (same structure as above)                 │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌──────────────── FOOTER ───────────────────┐  │
│  │  Schema (column names, types, nesting)     │  │
│  │  Row group metadata:                       │  │
│  │    - num_rows per row group                │  │
│  │    - column chunk offsets                  │  │
│  │    - column statistics (min, max, null_ct) │  │
│  │  Key-value metadata (user custom)          │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  [4-byte footer length] [Magic: "PAR1"]          │
└──────────────────────────────────────────────────┘
```

### The Four Levels

| Level | What | Size | Key Point |
|-------|------|------|-----------|
| **File** | One Parquet file on disk | 128MB–1GB typical | Contains 1+ row groups + footer |
| **Row Group** | Horizontal slice of the table (set of rows) | 128MB default in Spark | Unit of parallel processing; one row group = one Spark task reads it |
| **Column Chunk** | One column's data within a row group | Varies | Unit of column pruning — if you don't SELECT this column, it's never read |
| **Page** | Smallest unit of I/O and encoding | 1MB default | Unit of compression and encoding; pages are individually compressed |

---

## 3. Encoding Types (Interview Deep Dive)

Parquet doesn't store raw values — it uses **smart encoding** to reduce size dramatically.

| Encoding | How It Works | Best For | Example |
|----------|-------------|----------|---------|
| **Dictionary Encoding** | Build dictionary of unique values → store indices | Low-cardinality columns (status, country, gender) | `["Mumbai", "Pune", "Delhi"]` → `[0, 1, 2, 0, 0, 1]` |
| **Run-Length Encoding (RLE)** | Store value + count of consecutive repeats | Sorted data, boolean columns | `[A,A,A,B,B]` → `[(A,3),(B,2)]` |
| **Bit Packing** | Use minimum bits needed per value | Small integers, indices | Values 0-7 → only 3 bits each instead of 32 |
| **Delta Encoding** | Store differences between consecutive values | Timestamps, auto-increment IDs | `[1000,1001,1002,1003]` → `[1000, +1, +1, +1]` |
| **Plain Encoding** | Raw values, no compression tricks | Fallback when others don't help | High-cardinality strings |

### Dictionary + RLE Combo (Most Common)

```
Original column "status": ["active", "active", "active", "inactive", "active", "inactive", "inactive"]

Step 1 — Dictionary:
  Dictionary: {0: "active", 1: "inactive"}
  Indices:    [0, 0, 0, 1, 0, 1, 1]

Step 2 — RLE on indices:
  [(0, 3), (1, 1), (0, 1), (1, 2)]

Result: Instead of 7 strings → 4 tiny (value, count) pairs
Compression ratio: 80%+ savings
```

**Interview tip:** "Parquet uses **dictionary encoding by default** for all columns. If a column has too many unique values (high cardinality), it **falls back to plain encoding** after the dictionary page exceeds a threshold."

---

## 4. Predicate Pushdown — How Spark Skips Data

### What Happens Without Pushdown

```
Query: SELECT * FROM orders WHERE amount > 10000

Without pushdown:
  Read ALL row groups → load ALL data → filter in memory
  Read: 100GB → Filter: keep 1GB → Waste: 99GB of I/O
```

### What Happens With Pushdown

```
Footer metadata for each row group:
  Row Group 1: amount min=5, max=500        → SKIP (max < 10000)
  Row Group 2: amount min=100, max=50000    → READ (might have matches)
  Row Group 3: amount min=20000, max=99000  → READ (definitely has matches)
  Row Group 4: amount min=1, max=200        → SKIP (max < 10000)

Result: Read only 2 of 4 row groups → 50% less I/O
```

### Three Levels of Pushdown

| Level | What Gets Pushed | Where Stats Live |
|-------|-----------------|-----------------|
| **Row group level** | Min/max per column chunk → skip entire row groups | Footer metadata |
| **Page level** | Min/max per page → skip individual pages | Page header (Parquet 2.0+) |
| **Column level** | Column pruning → skip unneeded column chunks | Schema in footer |

### What Predicates Can Be Pushed Down

| Pushdown Works | Pushdown Does NOT Work |
|---------------|----------------------|
| `=`, `!=`, `<`, `>`, `<=`, `>=` | `LIKE '%pattern%'` |
| `IN (list)` | User-defined functions (UDFs) |
| `IS NULL`, `IS NOT NULL` | Complex expressions |
| `BETWEEN` | `OR` across different columns |
| `AND` combinations | Functions on columns: `UPPER(name) = 'X'` |

**Interview tip:** "Never apply a **function** on the filter column — `WHERE YEAR(date_col) = 2024` **breaks** pushdown. Instead use `WHERE date_col >= '2024-01-01' AND date_col < '2025-01-01'`."

---

## 5. Row Group Size — Performance Impact

| Row Group Size | Effect |
|---------------|--------|
| **Too small (1MB)** | Too many row groups → excessive metadata → slow footer reads |
| **Too large (1GB+)** | Less parallelism → fewer Spark tasks → memory pressure |
| **Sweet spot (128MB)** | Spark default → good balance of parallelism and I/O efficiency |

```python
# Configure row group size in Spark
spark.conf.set("parquet.block.size", 134217728)  # 128MB in bytes
```

---

## 6. Small File Problem

| Problem | Detail |
|---------|--------|
| **What** | Too many small Parquet files (< 128MB each) |
| **Why it's bad** | Each file = separate task → driver overhead, slow listing, metadata explosion |
| **Cause** | Too many partitions in write, frequent appends, streaming micro-batches |

### Solutions

| Solution | How |
|----------|-----|
| **Coalesce before write** | `df.coalesce(10).write.parquet(...)` — fewer output files |
| **Repartition** | `df.repartition(50).write.parquet(...)` — control file count |
| **OPTIMIZE (Delta)** | `OPTIMIZE table_name` — compacts small files into larger ones |
| **Spark AQE** | `spark.sql.adaptive.coalescePartitions.enabled = true` — auto-coalesce |
| **maxRecordsPerFile** | `df.write.option("maxRecordsPerFile", 1000000).parquet(...)` |

---

## 7. Parquet Schema Evolution

| Operation | Supported? | Detail |
|-----------|-----------|--------|
| **Add column** | Yes | New column = NULL in old files, has values in new files |
| **Remove column** | Yes (read side) | Old files still have it; new readers ignore it |
| **Rename column** | No | Parquet matches by **name** — rename = new column |
| **Change type** | Limited | Compatible promotions only (int → long) |

```python
# Enable schema merging in Spark
df = spark.read.option("mergeSchema", "true").parquet("path/")
```

**Interview tip:** "Parquet schema evolution is **limited** compared to Avro. For production, use **Delta Lake or Iceberg** on top of Parquet — they manage schema evolution properly."

---

## 8. Parquet in Spark — Tuning Configs

| Config | Default | What It Does |
|--------|---------|-------------|
| `spark.sql.parquet.filterPushdown` | `true` | Enable predicate pushdown |
| `spark.sql.parquet.mergeSchema` | `false` | Merge schemas across files on read |
| `spark.sql.parquet.compression.codec` | `snappy` | Compression codec (snappy/gzip/zstd/lz4) |
| `parquet.block.size` | `134217728` | Row group size in bytes (128MB) |
| `parquet.page.size` | `1048576` | Page size in bytes (1MB) |
| `parquet.enable.dictionary` | `true` | Enable dictionary encoding |

---

## 9. Reading Parquet Metadata (Debug Tool)

```python
# In PySpark — inspect Parquet footer
from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()

# Read metadata
df = spark.read.parquet("data/orders.parquet")
df.printSchema()

# Using parquet-tools CLI
# parquet-meta data/orders.parquet   → shows footer metadata
# parquet-head data/orders.parquet   → shows first few rows
```

```python
# In Python with pyarrow
import pyarrow.parquet as pq

meta = pq.read_metadata("orders.parquet")
print(f"Row groups: {meta.num_row_groups}")
print(f"Total rows: {meta.num_rows}")
print(f"Columns: {meta.num_columns}")

for i in range(meta.num_row_groups):
    rg = meta.row_group(i)
    print(f"Row Group {i}: {rg.num_rows} rows")
    for j in range(rg.num_columns):
        col = rg.column(j)
        print(f"  Column {col.path_in_schema}: min={col.statistics.min}, max={col.statistics.max}")
```

---

## 10. Common Interview Questions

| Question | Key Points |
|----------|------------|
| "What is the internal structure of Parquet?" | File → Row Groups → Column Chunks → Pages. Footer has schema + stats |
| "How does predicate pushdown work?" | Min/max stats in footer → skip row groups that can't match the filter |
| "What encoding does Parquet use?" | Dictionary (default), RLE, bit packing, delta. Falls back to plain for high cardinality |
| "What's the small file problem?" | Too many small files → overhead. Fix with coalesce, repartition, OPTIMIZE |
| "How big should a Parquet file be?" | 128MB–1GB. Row group = 128MB default |
| "Why is columnar faster for analytics?" | Reads only needed columns; same-type compression; vectorized execution |
| "Does Parquet support schema evolution?" | Add/remove columns yes. Rename/type change limited. Use Delta/Iceberg for full support |
| "Why shouldn't you apply functions on filter columns?" | Breaks predicate pushdown — Spark can't use min/max stats on `YEAR(date_col)` |

---

## Key Takeaways

- **Structure**: File → Row Groups (128MB) → Column Chunks → Pages (1MB). Footer stores schema + statistics.
- **Encoding**: Dictionary + RLE by default → massive compression for low-cardinality columns.
- **Predicate pushdown**: Min/max statistics in footer → skip irrelevant row groups → huge I/O savings.
- **Column pruning**: Only reads the columns in your SELECT — columnar format's biggest advantage.
- **Small file problem**: Too many small files kills performance → coalesce, repartition, OPTIMIZE.
- **Schema evolution**: Add columns OK. Rename/complex changes → use Delta Lake or Iceberg.
- **Spark default**: Always use Parquet for batch analytics unless you have a specific reason not to.

---
