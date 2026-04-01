# 09 — Format Selection Interview Guide

> **One-line:** This is your **cheat sheet** for the interview question "Which file format would you use for X?" — decision trees, comparison matrices, and 25+ rapid-fire Q&A.

---

## 1. The Master Decision Tree

```
What is your use case?
│
├── ANALYTICS (SQL, GROUP BY, dashboards)?
│   │
│   ├── Using Spark/Presto/Athena?
│   │   └── PARQUET ← default choice
│   │
│   ├── Using Hive with UPDATE/DELETE?
│   │   └── ORC (with ACID)
│   │
│   └── Need ACID on data lake?
│       ├── Databricks → DELTA LAKE (Parquet + tx log)
│       └── Multi-engine → ICEBERG (Parquet + metadata tree)
│
├── STREAMING / MESSAGING (Kafka, CDC)?
│   │
│   ├── Need schema evolution?
│   │   └── AVRO (with Schema Registry)
│   │
│   ├── Need maximum performance?
│   │   └── PROTOBUF
│   │
│   └── Simple/human-readable?
│       └── JSON (but larger)
│
├── DATA EXCHANGE (APIs, configs, humans)?
│   │
│   ├── Human-readable needed?
│   │   └── JSON
│   │
│   ├── Simple tabular export?
│   │   └── CSV (with caveats)
│   │
│   └── High-performance RPC?
│       └── PROTOBUF (gRPC)
│
└── ARCHIVAL / COLD STORAGE?
    └── PARQUET + GZIP/ZSTD (maximum compression)
```

---

## 2. Master Comparison Matrix

| Feature | Parquet | ORC | Avro | JSON | CSV | Protobuf | Delta | Iceberg |
|---------|---------|-----|------|------|-----|----------|-------|---------|
| **Type** | Columnar | Columnar | Row | Row | Row | Row | Table format | Table format |
| **Storage model** | File | File | File | File | File | Wire/File | Parquet + log | Parquet + metadata |
| **Compression** | Excellent | Best | Good | Poor | Poor | Excellent | Excellent | Excellent |
| **Column pruning** | Yes | Yes | No | No | No | No | Yes | Yes |
| **Predicate pushdown** | Yes | Strong | No | No | No | No | Yes | Yes |
| **Schema evolution** | Limited | Limited | Excellent | None | None | Good | Good | Best |
| **Schema in file** | Footer | Footer | Header | Every record | Header row | External .proto | Footer | Metadata tree |
| **ACID** | No | Hive only | No | No | No | No | Yes | Yes |
| **Time travel** | No | No | No | No | No | No | Yes | Yes |
| **Splittable** | Yes | Yes | Yes | JSONL yes | Uncompressed yes | N/A | Yes | Yes |
| **Human readable** | No | No | No | Yes | Yes | No | No | No |
| **Best for** | Analytics | Hive | Kafka/CDC | APIs | Exchange | gRPC | Databricks lake | Multi-engine lake |

---

## 3. File Format vs Table Format

```
FILE FORMATS (how bytes are organized on disk):
  Parquet, ORC, Avro, JSON, CSV, Protobuf
  → Define how individual files are structured

TABLE FORMATS (how files are organized as a logical table):
  Delta Lake, Apache Iceberg, Apache Hudi
  → Add ACID, versioning, schema management ON TOP of file formats
  → Delta uses Parquet files underneath
  → Iceberg can use Parquet, ORC, or Avro underneath

Analogy:
  File format = how a single BOOK is printed (font, layout)
  Table format = how the LIBRARY organizes books (catalog, shelving system)
```

---

## 4. Serialization Format vs File Format

| Term | What | Examples |
|------|------|---------|
| **Serialization format** | How a single RECORD is converted to bytes for network transfer | Avro record, Protobuf message, JSON object |
| **File format** | How many records are STORED on disk with metadata | Parquet file, ORC file, Avro container file |

```
Kafka message → serialized as Avro record (wire format)
  → consumed by Spark
  → written as Parquet file (storage format)
  → managed by Delta Lake (table format)

Three different "formats" in one pipeline!
```

---

## 5. Format Combinations in Real Pipelines

| Pipeline Stage | Format | Why |
|---------------|--------|-----|
| **Source DB → CDC** | Avro (Debezium) | Schema evolution, compact |
| **Kafka topics** | Avro or Protobuf | Schema Registry, binary |
| **Landing zone (Bronze)** | JSON or Avro files | Raw preservation |
| **Bronze → Silver** | Parquet (Delta/Iceberg) | Analytical performance |
| **Silver → Gold** | Parquet (Delta/Iceberg) | Optimized queries |
| **Gold → BI tools** | SQL over Parquet | Dashboard queries |
| **API responses** | JSON or Protobuf | Client consumption |
| **Archival** | Parquet + Zstd/Gzip | Maximum compression |

---

## 6. Performance Benchmarks (Approximate)

### Read Performance (Analytics Query: SELECT 3 columns, filter on 1)

```
10 million rows, 50 columns:

CSV:        ~30 seconds   (read all, parse text, no pushdown)
JSON:       ~25 seconds   (read all, parse text, no pushdown)
Avro:       ~15 seconds   (read all rows, binary but row-based)
ORC:        ~1.5 seconds  (column pruning, strong pushdown)
Parquet:    ~2 seconds    (column pruning, pushdown)
```

### Write Performance

```
10 million rows:

CSV:        ~5 seconds    (simple text write)
JSON:       ~8 seconds    (text + structure)
Avro:       ~3 seconds    (binary, fast row writes)
Parquet:    ~10 seconds   (columnar organization overhead)
ORC:        ~12 seconds   (columnar + index building)
```

### File Size

```
10 million rows, 50 columns (mixed types):

CSV:        ~2.5 GB
JSON:       ~4.0 GB
Avro:       ~800 MB
Parquet:    ~400 MB (with Snappy)
Parquet:    ~250 MB (with Zstd)
ORC:        ~350 MB (with Zlib)
```

---

## 7. Rapid-Fire Interview Q&A (25+ Questions)

### Basics

| Q | A |
|---|---|
| "Default file format in Spark?" | Parquet |
| "Parquet — row or columnar?" | Columnar |
| "Avro — row or columnar?" | Row-based |
| "What is column pruning?" | Reading only the columns in SELECT, skipping others |
| "What is predicate pushdown?" | Using min/max statistics to skip data blocks that can't match filters |

### Comparisons

| Q | A |
|---|---|
| "Parquet vs Avro?" | Parquet: columnar, analytics. Avro: row, streaming, schema evolution |
| "Parquet vs ORC?" | Both columnar. ORC: better compression, Hive ACID. Parquet: wider ecosystem |
| "Avro vs Protobuf?" | Avro: self-describing, dynamic. Protobuf: faster, smaller, needs codegen |
| "JSON vs Avro?" | JSON: human-readable, large. Avro: binary, 3x smaller, schema-enforced |
| "CSV vs Parquet for analytics?" | Parquet 10-100x faster — column pruning, compression, pushdown |

### Deep Dive

| Q | A |
|---|---|
| "Internal structure of Parquet?" | File → Row Groups (128MB) → Column Chunks → Pages (1MB). Footer has schema + stats |
| "How does Parquet encoding work?" | Dictionary (default) → RLE → Bit Packing → Delta. Falls back to Plain for high cardinality |
| "What is a row group in Parquet?" | Horizontal slice (~128MB). Unit of parallel processing. Contains column chunks |
| "Why is Gzip not good for Spark?" | Not splittable → 1 file = 1 task → no parallelism |
| "Best compression codec in 2026?" | Zstd — Gzip-level ratio at near-Snappy speed |

### Table Formats

| Q | A |
|---|---|
| "Delta Lake vs Iceberg?" | Delta: Databricks ecosystem, Z-ORDER. Iceberg: engine-neutral, hidden partitioning |
| "What is Delta transaction log?" | `_delta_log/` with JSON files tracking add/remove of Parquet files → ACID |
| "What is Iceberg hidden partitioning?" | Partition transforms (day, month, bucket) — users query naturally, engine prunes |
| "File format vs table format?" | File: how bytes stored. Table: how files organized with ACID/versioning |
| "What does OPTIMIZE do in Delta?" | Compacts small Parquet files into larger optimal-sized files |

### Practical

| Q | A |
|---|---|
| "You receive JSON from API — how to store in lake?" | Land as JSON in Bronze → convert to Parquet/Delta at Silver |
| "Kafka pipeline — which format?" | Avro or Protobuf with Schema Registry → Parquet/Delta in lake |
| "How to handle small files?" | Coalesce, repartition, OPTIMIZE, AQE auto-coalesce |
| "Archival storage format?" | Parquet + Zstd or Gzip compression |
| "Schema changes breaking pipeline?" | Avro Schema Registry (streaming) + Delta/Iceberg schema evolution (lake) |

---

## 8. The One-Line Summary for Each Format

| Format | One-Line |
|--------|----------|
| **Parquet** | Columnar king of analytics — Spark's default, column pruning, predicate pushdown |
| **ORC** | Columnar with best compression + native ACID — Hive's champion |
| **Avro** | Row-based binary with best schema evolution — Kafka's standard |
| **JSON** | Human-readable, flexible, self-describing — APIs and configs |
| **CSV** | Simplest format, most pitfalls — human exchange only |
| **Protobuf** | Fastest + smallest binary serialization — gRPC and high-performance services |
| **Delta Lake** | Parquet + JSON transaction log = ACID lakehouse (Databricks) |
| **Iceberg** | Parquet + metadata tree = engine-neutral ACID lakehouse |

---

## Key Takeaways

- **Analytics** → Parquet (default) or ORC (Hive). Always columnar.
- **Streaming/Kafka** → Avro (standard) or Protobuf (performance). Always with Schema Registry.
- **ACID on lake** → Delta Lake (Databricks) or Iceberg (multi-engine).
- **Compression** → Zstd is the modern default. Snappy for speed. Gzip for archival.
- **File format ≠ table format** — Parquet is how bytes are stored; Delta/Iceberg is how files are organized.
- **JSON/CSV → Parquet** conversion at Bronze→Silver is a standard pattern.
- Know the **decision tree** and **comparison matrix** — interviewers love "which format for X?" questions.

---
