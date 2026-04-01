# 02 — Avro Deep Dive

> **One-line:** Avro is a **row-based binary** serialization format with **schema embedded in every file** and the **best schema evolution** support — making it the standard for **Kafka**, **CDC**, and **data exchange** between services.

---

## 1. Why Avro Exists (Different Problem Than Parquet)

| Parquet Solves | Avro Solves |
|---------------|------------|
| "Read few columns from wide table fast" | "Serialize entire records fast for streaming/messaging" |
| Analytical queries (SELECT, GROUP BY) | Row-level ingestion, Kafka messages, CDC events |
| Read-heavy workloads | Write-heavy workloads |
| Column pruning, predicate pushdown | Schema evolution, compatibility guarantees |

**Interview line:** "Parquet is optimized for **reading columns**. Avro is optimized for **writing rows** with schema evolution — that's why Kafka uses Avro and data lakes use Parquet."

---

## 2. Avro File Internal Structure

### Object Container File (OCF) Format

```
┌────────────────────────────────────────────────┐
│              AVRO FILE (.avro)                   │
│                                                  │
│  ┌──────────── FILE HEADER ──────────────────┐  │
│  │  Magic bytes: "Obj" + 0x01                 │  │
│  │  File metadata:                            │  │
│  │    - "avro.schema" → full JSON schema      │  │
│  │    - "avro.codec" → compression codec      │  │
│  │  Sync marker (16 random bytes)             │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌──────────── DATA BLOCK 1 ─────────────────┐  │
│  │  Record count (long)                       │  │
│  │  Block size in bytes (long)                │  │
│  │  Serialized records (compressed together)  │  │
│  │    Record 1: {name: "Alice", age: 30}      │  │
│  │    Record 2: {name: "Bob", age: 25}        │  │
│  │    ...                                     │  │
│  │  Sync marker (same 16 bytes)               │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌──────────── DATA BLOCK 2 ─────────────────┐  │
│  │  (same structure)                          │  │
│  │  Sync marker                               │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
└──────────────────────────────────────────────────┘
```

### Why Sync Markers Matter

```
File: [Header] [Block1] [sync] [Block2] [sync] [Block3] [sync]

Spark needs to split this file across tasks.
Each task finds the nearest sync marker → starts reading from there.
Without sync markers → can't split → single-task bottleneck.
```

**Avro is splittable** because of sync markers — unlike raw JSON or CSV (which need careful splitting).

---

## 3. Avro Schema — JSON Definition

### Schema Types

| Type | Avro Name | Example |
|------|-----------|---------|
| **Null** | `"null"` | Missing values |
| **Boolean** | `"boolean"` | true/false |
| **Int** | `"int"` | 32-bit integer |
| **Long** | `"long"` | 64-bit integer |
| **Float** | `"float"` | 32-bit IEEE 754 |
| **Double** | `"double"` | 64-bit IEEE 754 |
| **String** | `"string"` | UTF-8 text |
| **Bytes** | `"bytes"` | Raw byte sequence |
| **Array** | `{"type": "array", "items": "string"}` | List of strings |
| **Map** | `{"type": "map", "values": "int"}` | Key-value pairs |
| **Record** | Complex type with named fields | Structured object |
| **Enum** | `{"type": "enum", "symbols": [...]}` | Fixed set of values |
| **Union** | `["null", "string"]` | One of multiple types (nullable) |
| **Fixed** | Fixed-length bytes | UUID, hash |

### Record Schema Example

```json
{
  "type": "record",
  "name": "Customer",
  "namespace": "com.company.events",
  "fields": [
    {"name": "id", "type": "long"},
    {"name": "name", "type": "string"},
    {"name": "email", "type": ["null", "string"], "default": null},
    {"name": "age", "type": "int"},
    {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    {"name": "tags", "type": {"type": "array", "items": "string"}, "default": []},
    {"name": "address", "type": {
      "type": "record",
      "name": "Address",
      "fields": [
        {"name": "city", "type": "string"},
        {"name": "state", "type": "string"},
        {"name": "zip", "type": "string"}
      ]
    }}
  ]
}
```

### Logical Types (Important for Interviews)

| Logical Type | Underlying | Meaning |
|-------------|-----------|---------|
| `date` | int | Days since Unix epoch |
| `time-millis` | int | Milliseconds since midnight |
| `timestamp-millis` | long | Milliseconds since Unix epoch |
| `timestamp-micros` | long | Microseconds since Unix epoch |
| `decimal` | bytes/fixed | Arbitrary precision decimal |
| `uuid` | string | UUID string |

---

## 4. Schema Evolution — Avro's Superpower

This is the **#1 reason** Avro is used in Kafka and data exchange.

### Evolution Rules

| Change | Backward Compatible? | Forward Compatible? | Full Compatible? |
|--------|---------------------|--------------------|--------------------|
| **Add field with default** | Yes | Yes | Yes |
| **Remove field with default** | Yes | Yes | Yes |
| **Add field WITHOUT default** | No | Yes | No |
| **Remove field WITHOUT default** | Yes | No | No |
| **Rename field** | No (use aliases) | No (use aliases) | No (use aliases) |
| **Change type (compatible)** | int→long, float→double | Yes | Depends |
| **Change type (incompatible)** | No | No | No |

### Compatibility Modes Explained

```
BACKWARD compatible:
  New schema can READ old data.
  "I updated my consumer — can it still read old Kafka messages?" → YES
  Rule: New fields must have defaults.

FORWARD compatible:
  Old schema can READ new data.
  "I updated my producer — can old consumers still read new messages?" → YES
  Rule: Removed fields must have had defaults.

FULL compatible:
  Both directions work.
  Rule: Only add/remove fields that have defaults.

NONE:
  No compatibility guarantees.
  Dangerous — can break consumers at any time.
```

### Evolution Example

```
V1 Schema:
  { "name": "Customer",
    "fields": [
      {"name": "id", "type": "long"},
      {"name": "name", "type": "string"}
    ]
  }

V2 Schema (BACKWARD compatible — added field with default):
  { "name": "Customer",
    "fields": [
      {"name": "id", "type": "long"},
      {"name": "name", "type": "string"},
      {"name": "email", "type": ["null", "string"], "default": null}  ← NEW
    ]
  }

V2 consumer reads V1 data → email field is missing → uses default (null) ✓
V1 consumer reads V2 data → ignores unknown "email" field ✓ (forward)
```

**Interview tip:** "The golden rule: **always add new fields with a default value** and use **union with null** (`["null", "string"]`) — this ensures both backward and forward compatibility."

---

## 5. Schema Registry (Confluent)

### What It Is

| Feature | Detail |
|---------|--------|
| **What** | Central repository for Avro/Protobuf/JSON schemas |
| **Why** | Enforces compatibility rules before producers can publish new schemas |
| **Where** | Runs alongside Kafka — producers/consumers register/fetch schemas |
| **Storage** | Stores schemas in a Kafka topic (`_schemas`) |

### How It Works

```
Producer                          Schema Registry                    Consumer
   │                                    │                                │
   │  1. Register schema v2 ──────────►│                                │
   │                                    │  2. Check compatibility       │
   │                                    │     (v2 vs v1)                │
   │  3. Get schema ID (42) ◄──────────│                                │
   │                                    │                                │
   │  4. Send message to Kafka:         │                                │
   │     [magic byte][schema_id=42]     │                                │
   │     [avro binary payload]          │                                │
   │         │                          │                                │
   │         └──────── Kafka ──────────►│                                │
   │                                    │  5. Consumer reads schema_id  │
   │                                    │     fetches schema from ◄─────│
   │                                    │     registry                  │
   │                                    │  6. Deserialize with schema ──►│
```

### Wire Format (Kafka + Schema Registry)

```
┌──────┬────────────┬──────────────────────┐
│ 0x00 │ Schema ID  │ Avro binary payload  │
│ (1B) │ (4 bytes)  │ (variable length)    │
└──────┴────────────┴──────────────────────┘

Magic byte 0x00 signals "this uses Schema Registry"
Schema ID → Registry lookup → get schema → deserialize
```

**Interview line:** "The message **doesn't carry the full schema** — just a 4-byte schema ID. The consumer fetches the schema from the registry and caches it. This keeps messages **tiny** while maintaining schema governance."

---

## 6. Avro vs Parquet vs JSON — Wire Format Size

```
Same record: {"id": 12345, "name": "Alice", "age": 30, "city": "Mumbai"}

JSON:     ~60 bytes (field names repeated, text encoding)
Avro:     ~20 bytes (no field names, binary encoding, schema separate)
Parquet:  N/A — not used for single records (file format, not wire format)

At 1M messages/sec:
  JSON:    ~60 MB/sec network
  Avro:    ~20 MB/sec network  → 3x less bandwidth
```

---

## 7. Avro in Spark

```python
# Read Avro file
df = spark.read.format("avro").load("data/customers.avro")

# Write as Avro
df.write.format("avro").save("output/customers.avro")

# Read from Kafka with Avro + Schema Registry
from confluent_kafka.schema_registry import SchemaRegistryClient
# ... or use Spark's built-in avro functions:
from pyspark.sql.avro.functions import from_avro, to_avro

df = spark.readStream \
    .format("kafka") \
    .option("subscribe", "customers") \
    .load() \
    .select(from_avro("value", schema_str).alias("data"))
```

---

## 8. Common Interview Questions

| Question | Key Points |
|----------|------------|
| "Why is Avro used with Kafka?" | Row-based (fast writes), schema embedded, excellent schema evolution, compact binary |
| "How does schema evolution work?" | Add/remove fields with defaults → backward/forward compatible |
| "What is Schema Registry?" | Central schema store → enforces compatibility before producers can register new schemas |
| "Avro vs Parquet?" | Avro: row-based, streaming, schema evolution. Parquet: columnar, analytics, predicate pushdown |
| "Avro vs JSON?" | Avro: binary, 3x smaller, schema enforced. JSON: text, human-readable, no schema |
| "What is backward compatibility?" | New consumer can read data written with old schema |
| "What happens if producer sends incompatible schema?" | Schema Registry rejects registration → producer can't publish → prevents breaking consumers |
| "How are Avro messages stored in Kafka?" | Magic byte + 4-byte schema ID + binary payload. Schema fetched from registry |

---

## Key Takeaways

- **Avro** = row-based binary format with **embedded schema** and **best schema evolution**.
- File structure: Header (schema + codec) → Data Blocks (compressed records) → Sync Markers (splittability).
- **Schema evolution** rules: add/remove fields **with defaults** = safe. Rename/incompatible type change = breaks.
- **Schema Registry**: central schema store, enforces compatibility, messages carry only 4-byte schema ID.
- **Compatibility modes**: BACKWARD (new reads old), FORWARD (old reads new), FULL (both), NONE (chaos).
- Avro is **3x smaller** than JSON for the same data — critical at millions of messages/sec.
- **Golden rule**: Always use `["null", "string"]` unions with `default: null` for optional fields.

---
