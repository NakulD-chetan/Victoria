# 04 — JSON, CSV & Semi-Structured Data

> **One-line:** JSON and CSV are the most common data **exchange** formats — easy for humans, **terrible** for analytics at scale — and knowing their pitfalls is essential for DE interviews.

---

## 1. CSV — The Simplest (and Most Dangerous) Format

### What CSV Is

```
id,name,age,city
1,Alice,30,Mumbai
2,"Bob, Jr.",25,Pune
3,Carol,35,"New Delhi"
```

| Feature | Detail |
|---------|--------|
| **Type** | Row-based, text, delimiter-separated |
| **Schema** | External (first row header or none) |
| **Compression** | None built-in (apply gzip/snappy externally) |
| **Human readable** | Yes |
| **Size** | Large (text encoding, field names repeated in header concept) |

### CSV Pitfalls (Interview Favorites)

| Pitfall | Example | Solution |
|---------|---------|----------|
| **Delimiter in data** | `"Bob, Jr."` contains comma | Quoting with `"`, but quoting rules vary |
| **Newline in data** | Multi-line address field | Quoting, but many parsers break |
| **No type information** | Is `"30"` a string or integer? | Schema inference guesses (often wrong) |
| **No null representation** | Empty string vs null vs `"NULL"` vs `"\\N"` | Ambiguous — must define convention |
| **Encoding issues** | UTF-8 vs Latin-1 vs Windows-1252 | BOM detection, explicit encoding param |
| **Header mismatch** | File has 10 columns, header has 9 | Corrupt data or delimiter in unquoted field |
| **Schema evolution** | New column added mid-stream | Breaks positional parsing |
| **Not splittable** when compressed | gzip CSV can't be split across tasks | Use splittable compression (bzip2) or convert to Parquet |

### CSV in Spark — Watch Out

```python
# Basic read — Spark infers schema (SLOW, unreliable)
df = spark.read.csv("data/orders.csv", header=True, inferSchema=True)

# Better — define schema explicitly (FAST, reliable)
from pyspark.sql.types import StructType, StructField, StringType, IntegerType

schema = StructType([
    StructField("id", IntegerType()),
    StructField("name", StringType()),
    StructField("age", IntegerType()),
    StructField("city", StringType())
])
df = spark.read.csv("data/orders.csv", header=True, schema=schema)
```

**Interview tip:** "Never use `inferSchema=True` in production. It reads the **entire file twice** (once for schema, once for data) and often guesses wrong. Always define schema explicitly."

---

## 2. JSON — Flexible but Expensive

### JSON Variants

| Variant | Structure | Usage |
|---------|-----------|-------|
| **JSON** | Single object or array | API responses |
| **JSONL / JSON Lines** | One JSON object per line | Logs, streaming, data exchange |
| **NDJSON** | Same as JSONL (Newline Delimited JSON) | Same |

```
JSONL (one record per line — preferred for data engineering):
{"id": 1, "name": "Alice", "age": 30, "address": {"city": "Mumbai", "state": "MH"}}
{"id": 2, "name": "Bob", "age": 25, "address": {"city": "Pune", "state": "MH"}}
```

### JSON Strengths

| Strength | Detail |
|----------|--------|
| **Self-describing** | Field names in every record |
| **Nested structures** | Arrays, objects, arbitrary depth |
| **Flexible schema** | Each record can have different fields |
| **Human readable** | Easy to debug, inspect |
| **Universal** | Every language, every API, every tool supports it |

### JSON Weaknesses for Analytics

| Weakness | Impact |
|----------|--------|
| **Field names repeated** | `"name"` stored in every record → 2-5x storage overhead |
| **Text encoding** | Numbers as text: `"30"` = 2 bytes vs 4 bytes for int32 |
| **No column pruning** | Must parse entire record to get one field |
| **No predicate pushdown** | Can't skip records without reading them |
| **Schema inference is expensive** | Spark reads entire file to figure out schema |
| **Nested data complexity** | Flattening nested JSON for tabular analysis is painful |

### Size Comparison

```
Same 1 million records:

CSV:        ~50 MB
JSON:       ~120 MB  (field names repeated, text encoding)
Avro:       ~25 MB   (binary, no field names in data)
Parquet:    ~15 MB   (columnar, compressed, no field names)

JSON is 8x larger than Parquet for the same data!
```

### JSON in Spark — Handling Nested Data

```python
# Read JSON
df = spark.read.json("data/events.jsonl")

# Flatten nested fields
from pyspark.sql.functions import col

df_flat = df.select(
    col("id"),
    col("name"),
    col("address.city").alias("city"),
    col("address.state").alias("state")
)

# Explode arrays
from pyspark.sql.functions import explode

df_exploded = df.select(
    col("id"),
    explode(col("tags")).alias("tag")
)

# Handle schema evolution — read with explicit schema
schema = spark.read.json("data/sample.jsonl").schema
df = spark.read.schema(schema).json("data/events.jsonl")
```

---

## 3. Semi-Structured Data Handling

### The Landing Zone Pattern

```
API / Source → JSON → Bronze (raw JSON) → Silver (Parquet/Delta) → Gold
                           │
                           └── Flatten, type-cast, validate at Bronze→Silver
```

| Stage | Format | Why |
|-------|--------|-----|
| **Landing** | JSON / CSV as-is | Preserve raw data for replay |
| **Bronze** | JSON stored as string column or raw files | Schema-on-read, flexibility |
| **Silver** | Parquet / Delta with explicit schema | Performance, type safety |
| **Gold** | Parquet / Delta (aggregated) | Optimized for queries |

### Snowflake VARIANT Type

```sql
-- Store semi-structured JSON as VARIANT
CREATE TABLE raw_events (
    event_data VARIANT,
    loaded_at TIMESTAMP
);

-- Query nested fields
SELECT
    event_data:user_id::INT as user_id,
    event_data:action::STRING as action,
    event_data:metadata:device::STRING as device
FROM raw_events;
```

### Spark JSON Functions

| Function | What It Does |
|----------|-------------|
| `from_json(col, schema)` | Parse JSON string into struct |
| `to_json(col)` | Convert struct to JSON string |
| `get_json_object(col, path)` | Extract value using JSON path |
| `json_tuple(col, keys...)` | Extract multiple values at once |
| `explode(col)` | Flatten array into rows |
| `schema_of_json(sample)` | Infer schema from sample JSON |

---

## 4. When to Use What

| Format | Use When | Avoid When |
|--------|----------|------------|
| **CSV** | Human exchange, Excel export, simple config | Analytics at scale, complex data |
| **JSON** | API responses, configs, landing zone | Large-scale analytics (use Parquet) |
| **JSONL** | Log ingestion, streaming landing | Long-term analytical storage |
| **Parquet** | Analytics, data lake, Spark ETL | Streaming wire format |
| **Avro** | Kafka, CDC, schema evolution | Analytical queries |

---

## 5. Common Interview Questions

| Question | Key Points |
|----------|------------|
| "Why not use JSON/CSV for data lakes?" | No column pruning, no predicate pushdown, no compression, repeated field names → huge I/O waste |
| "How do you handle nested JSON in Spark?" | `col("field.nested")` for structs, `explode()` for arrays, `from_json()` for strings |
| "CSV vs Parquet performance?" | Parquet 10-100x faster for analytics: column pruning + pushdown + compression |
| "Why use `inferSchema=False` for CSV?" | `inferSchema=True` reads file twice, guesses types wrong. Define schema explicitly |
| "How do you handle schema evolution in JSON?" | Store raw in Bronze, use explicit schema at Silver, handle missing fields with defaults |
| "What is JSONL?" | One JSON object per line — splittable, streamable, easy to append |

---

## Key Takeaways

- **CSV**: simple, human-readable, but **full of pitfalls** (delimiters, nulls, types, encoding). Never for analytics at scale.
- **JSON**: self-describing, flexible, supports nesting — but **8x larger** than Parquet and **no analytical optimizations**.
- **JSONL**: one record per line — preferred over array JSON for data pipelines (splittable, appendable).
- Always **convert JSON/CSV to Parquet** at the Bronze→Silver boundary.
- Never use `inferSchema=True` in production Spark — define schemas explicitly.
- Semi-structured handling: store raw → flatten at Silver → aggregate at Gold.

---
