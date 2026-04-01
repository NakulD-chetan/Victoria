# 03 — ORC Deep Dive

> **One-line:** ORC (Optimized Row Columnar) is a **columnar** format designed for **Hive** with **built-in indexes**, **bloom filters**, and **native ACID** support — offering the best compression ratios and the tightest integration with the Hadoop ecosystem.

---

## 1. ORC vs Parquet — Why Both Exist

| Dimension | ORC | Parquet |
|-----------|-----|---------|
| **Origin** | Hortonworks (Hive-focused) | Twitter + Cloudera (cross-engine) |
| **Ecosystem** | Hive, Presto, Spark | Spark, Presto, Trino, Athena, BigQuery |
| **ACID** | Native in Hive 3.x | No (use Delta Lake) |
| **Compression** | Typically 10-30% better | Excellent but slightly larger |
| **Indexes** | Built-in (stripe-level + row-level) | Footer statistics only |
| **Bloom filters** | Native support | Limited |
| **2026 usage** | Hive-heavy shops, legacy Hadoop | Industry standard for new projects |

**Interview line:** "ORC is technically superior in compression and indexing, but Parquet won the ecosystem battle — it's supported everywhere. ORC is best when Hive is your primary engine."

---

## 2. ORC File Internal Structure

```
┌────────────────────────────────────────────────┐
│                  ORC FILE                       │
│                                                  │
│  ┌──────────── Stripe 1 (64MB default) ──────┐  │
│  │                                            │  │
│  │  ┌─ Index Data ────────────────────────┐  │  │
│  │  │  Min/Max per column per 10K rows     │  │  │
│  │  │  Row positions for skip              │  │  │
│  │  │  Bloom filters (if enabled)          │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │                                            │  │
│  │  ┌─ Row Data ──────────────────────────┐  │  │
│  │  │  Column 1: encoded + compressed      │  │  │
│  │  │  Column 2: encoded + compressed      │  │  │
│  │  │  Column 3: encoded + compressed      │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │                                            │  │
│  │  ┌─ Stripe Footer ────────────────────┐  │  │
│  │  │  Column encoding info               │  │  │
│  │  │  Stream positions and sizes          │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │                                            │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌──────────── Stripe 2 ─────────────────────┐  │
│  │  (same structure)                          │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌──────────── FILE FOOTER ──────────────────┐  │
│  │  Schema (column names, types)              │  │
│  │  Stripe metadata (offset, length, rows)    │  │
│  │  Column statistics (min, max, sum, count)  │  │
│  │  Row count                                 │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌──────────── POSTSCRIPT ───────────────────┐  │
│  │  Footer length, compression type, version  │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
└──────────────────────────────────────────────────┘
```

### ORC vs Parquet Structure Mapping

| ORC Term | Parquet Equivalent | Size |
|----------|-------------------|------|
| **Stripe** | Row Group | 64MB default (vs Parquet 128MB) |
| **Index Data** | Footer statistics | ORC has MORE granular indexes (per 10K rows) |
| **Row Data** | Column Chunks + Pages | Compressed column data |
| **Stripe Footer** | Column metadata | Encoding and offset info |
| **File Footer** | File Footer | Schema + aggregate stats |

---

## 3. ORC's Three-Level Indexing

This is ORC's biggest advantage over Parquet — **three levels** of data skipping.

```
Level 1: FILE-LEVEL statistics (in File Footer)
  → "Column 'amount' across entire file: min=1, max=99999"
  → Skip the ENTIRE FILE if filter doesn't match

Level 2: STRIPE-LEVEL statistics (in File Footer per stripe)
  → "Column 'amount' in Stripe 3: min=5000, max=8000"
  → Skip specific stripes

Level 3: ROW-GROUP INDEX (in Index Data, every 10,000 rows)
  → "Rows 20001-30000 of Stripe 3: amount min=6000, max=7500"
  → Skip within a stripe at 10K-row granularity
```

**Interview tip:** "ORC indexes at **three levels**: file → stripe → row group (10K rows). Parquet indexes at **two levels**: file footer → row group. ORC's row-group index gives finer-grained skipping."

---

## 4. Bloom Filters in ORC

| Feature | Detail |
|---------|--------|
| **What** | Probabilistic data structure — answers "is value X **possibly** in this stripe?" |
| **False positives** | May say "yes" when value isn't there (reads extra data, minor cost) |
| **False negatives** | NEVER says "no" when value is there (never misses data) |
| **Use case** | Equality filters on high-cardinality columns (user_id, order_id) |

```
Without bloom filter:
  WHERE user_id = 'U12345'
  → Must check min/max stats: min='U00001', max='U99999' → range includes U12345
  → Must READ the stripe even though U12345 might not be there

With bloom filter:
  → Check bloom filter: "Is U12345 in this stripe?" → "NO" → SKIP stripe entirely
  → Saves reading 64MB of data per skipped stripe
```

```sql
-- Enable bloom filter for a column in Hive
CREATE TABLE orders (
    order_id STRING,
    amount DECIMAL(10,2)
) STORED AS ORC
TBLPROPERTIES (
    "orc.bloom.filter.columns" = "order_id",
    "orc.bloom.filter.fpp" = "0.01"
);
```

---

## 5. ORC Encoding Types

| Encoding | How It Works | Used For |
|----------|-------------|----------|
| **Dictionary** | Unique values dictionary + indices | Low-cardinality strings |
| **Run-Length (RLEv2)** | Value + repeat count (optimized version 2) | Sorted integers, booleans |
| **Direct** | Raw values | High-cardinality when dictionary is too large |
| **Delta** | Store differences between consecutive values | Timestamps, auto-increment |
| **Patched Base** | Base value + patches for outliers | Mostly-similar integers with a few outliers |

---

## 6. ORC ACID Transactions (Hive 3.x)

ORC is the **only** open file format with **native** ACID support (without a table format layer like Delta).

### How ACID Works in ORC

```
Base file: orders_000000 (original data)
    │
    ├── delta_0000001 (INSERT batch 1)
    ├── delta_0000002 (INSERT batch 2)
    ├── delete_delta_0000003 (DELETE batch)
    │
    └── Compaction (periodic):
         Minor compaction: merge deltas → fewer delta files
         Major compaction: merge base + all deltas → new base file
```

| Operation | How It Works |
|-----------|-------------|
| **INSERT** | New delta file with inserted rows |
| **UPDATE** | Delete old row (delete_delta) + Insert new row (delta) |
| **DELETE** | delete_delta file marking rows as deleted |
| **Read** | Merge base + deltas + delete_deltas at query time |
| **Compaction** | Background merge to reduce file count and speed reads |

---

## 7. ORC in Spark

```python
# Read ORC
df = spark.read.format("orc").load("data/orders_orc/")

# Write as ORC
df.write.format("orc").save("output/orders/")

# Write with compression
df.write.format("orc") \
    .option("compression", "zlib") \
    .save("output/orders/")

# ORC with bloom filter (Spark config)
spark.conf.set("orc.bloom.filter.columns", "order_id,customer_id")
```

---

## 8. When to Choose ORC vs Parquet

| Choose ORC When | Choose Parquet When |
|----------------|---------------------|
| Hive is primary query engine | Spark is primary engine |
| Need native ACID (no Delta Lake) | Using Delta Lake / Iceberg |
| Maximum compression is priority | Broader ecosystem support needed |
| Bloom filters needed for point lookups | Standard analytics workload |
| Existing Hadoop/Hive infrastructure | New cloud-native project |

---

## 9. Common Interview Questions

| Question | Key Points |
|----------|------------|
| "ORC vs Parquet?" | ORC: better compression, 3-level index, bloom filters, ACID. Parquet: wider ecosystem, Spark default |
| "What is a stripe in ORC?" | Horizontal slice of data (like Parquet row group), 64MB default, has index + data + footer |
| "How does ORC indexing work?" | Three levels: file → stripe → row group (10K rows). Min/max + bloom filters at each level |
| "What are bloom filters?" | Probabilistic structure — quickly checks if value exists in stripe. False positives OK, no false negatives |
| "How does ORC ACID work?" | Base files + delta files + delete_delta files. Merged at read time. Compaction merges periodically |
| "When would you NOT use ORC?" | Non-Hive ecosystems, Spark-heavy shops, cloud-native projects where Parquet+Delta is standard |

---

## Key Takeaways

- **ORC** = columnar format optimized for **Hive** with **three-level indexing** and **native ACID**.
- Structure: Stripes (64MB) → Index Data + Row Data + Stripe Footer. File Footer has schema + stats.
- **Three-level index** (file → stripe → 10K row groups) gives finer-grained data skipping than Parquet.
- **Bloom filters** enable efficient point lookups on high-cardinality columns.
- **ACID** via base + delta + delete_delta files — unique among raw file formats.
- **Better compression** than Parquet (10-30% smaller), but **narrower ecosystem** support.
- **Use ORC** for Hive-heavy environments. **Use Parquet** for everything else (Spark, cloud, modern stack).

---
