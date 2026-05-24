
https://drive.google.com/drive/folders/1Mj1x3x4oX05vzpPwuzvIHgWqiUVZGv7f

# File Formats Deep Dive — Index

> This folder goes **deep inside** each file format — byte-level structure, encoding types, internal mechanics — the kind of detail interviewers ask to test whether you **truly understand** Parquet, Avro, ORC, Delta, Iceberg, etc.



---

## Notes

| # | Topic | What You'll Learn |
|---|-------|-------------------|
| 01 | **Parquet Deep Dive** | Row groups, column chunks, pages, encoding types, predicate pushdown mechanics |
| 02 | **Avro Deep Dive** | Schema definition, evolution rules, Object Container File, Schema Registry |
| 03 | **ORC Deep Dive** | Stripes, indexes, bloom filters, ACID transactions, Hive integration |
| 04 | **JSON, CSV & Semi-Structured** | Schema inference, nested data, common pitfalls, when to use |
| 05 | **Delta Lake Internals** | Transaction log (_delta_log), ACID mechanics, OPTIMIZE, VACUUM, Z-Order |
| 06 | **Apache Iceberg Internals** | Metadata tree, snapshots, hidden partitioning, schema evolution |
| 07 | **Protobuf & Thrift** | Protocol Buffers, Thrift, comparison with Avro, gRPC integration |
| 08 | **Compression Codecs Deep Dive** | Snappy, Gzip, Zstd, LZ4, Brotli — internals, benchmarks, when to use |
| 09 | **Format Selection Interview Guide** | Decision matrix, comparison tables, 20+ interview Q&A |

---

## Relationship to Existing Notes

| Existing Note | What It Covers | This Folder Adds |
|--------------|----------------|------------------|
| `Spark-Notes/18-File-Formats-Parquet-ORC-Avro.md` | Surface comparison | Byte-level internals, encoding types, performance tuning |
| `DE-Master/01-DE-Fundamentals/01_Concept.md` | Format table + compression table | Deep mechanics, decision reasoning, interview scenarios |
| `DE-Master/03-Data-Lakes-and-Lakehouse/01_Concept.md` | Delta/Iceberg/Hudi overview | Internal architecture, transaction log structure, metadata tree |

---
