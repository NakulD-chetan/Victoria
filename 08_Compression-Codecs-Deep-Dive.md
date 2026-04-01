# 08 — Compression Codecs Deep Dive

> **One-line:** Compression is a **three-way trade-off** between **file size**, **CPU cost**, and **read/write speed** — choosing the right codec can save **50-90% storage** and dramatically affect pipeline performance.

---

## 1. Why Compression Matters in DE

```
Without compression:     1 TB/day × 365 days = 365 TB/year
With Snappy (3x):        365 / 3 = ~122 TB/year → saves 243 TB
With Zstd (5x):          365 / 5 = ~73 TB/year  → saves 292 TB

At $0.023/GB/month (S3): 
  Uncompressed: ~$8,400/month
  Snappy:       ~$2,800/month
  Zstd:         ~$1,680/month → saves $6,720/month
```

---

## 2. The Big Five Codecs

| Codec | Ratio | Compress Speed | Decompress Speed | Best For |
|-------|-------|---------------|-----------------|----------|
| **Snappy** | Medium (2-3x) | Very Fast | Very Fast | Default in Spark/Parquet — balanced |
| **LZ4** | Low-Medium (2-3x) | Fastest | Fastest | Real-time, ultra-low latency |
| **Gzip** | High (5-8x) | Slow | Medium | Archival, cold storage, network transfer |
| **Zstd** | High (4-7x) | Fast-Medium | Fast | Modern default — best ratio/speed balance |
| **Brotli** | Highest (6-10x) | Slowest | Medium | Web assets, static content (rare in DE) |

```
Speed vs Ratio spectrum:

Fast compress/decompress ◄──────────────────────────► Best compression ratio
  LZ4     Snappy         Zstd              Gzip         Brotli
  (2-3x)  (2-3x)        (4-7x)            (5-8x)       (6-10x)
```

---

## 3. Snappy — The Spark Default

| Feature | Detail |
|---------|--------|
| **Created by** | Google (2011) |
| **Goal** | Speed over ratio — "reasonable compression at 250 MB/sec" |
| **Ratio** | 2-3x (modest) |
| **Speed** | ~250 MB/s compress, ~500 MB/s decompress |
| **Splittable** | Yes (Snappy-framed format) |
| **Used in** | Parquet default, Spark default, Kafka (optional) |

### Why Spark Uses Snappy by Default

```
Spark reads data from disk → decompresses → processes in memory

With Snappy: Decompress 500MB/sec → barely noticeable overhead
With Gzip:   Decompress 100MB/sec → 5x slower → CPU becomes bottleneck

For interactive analytics: Snappy wins (faster queries)
For cold storage:          Gzip/Zstd wins (smaller files, less cost)
```

---

## 4. Zstd — The Modern Champion

| Feature | Detail |
|---------|--------|
| **Created by** | Facebook/Meta (2016) |
| **Goal** | "Gzip-level compression at Snappy-level speed" |
| **Ratio** | 4-7x (close to Gzip) |
| **Speed** | ~150 MB/s compress, ~400 MB/s decompress |
| **Tunable levels** | 1 (fast, low ratio) to 22 (slow, best ratio) |
| **Splittable** | With framed format |
| **Used in** | Delta Lake (recommended), Kafka, Linux kernel, many modern systems |

### Zstd Levels

```
Level 1:  Fast compress,   ratio ~3x    → similar to Snappy speed, better ratio
Level 3:  Default balance, ratio ~4x    → good default
Level 9:  Slower compress, ratio ~5-6x  → batch processing, cold storage
Level 19: Very slow,       ratio ~6-7x  → archival
Level 22: Extremely slow,  ratio ~7x    → maximum compression, rare
```

```python
# Spark with Zstd
df.write.format("parquet") \
    .option("compression", "zstd") \
    .save("output/orders/")

# Delta Lake default is Snappy; switch to Zstd
spark.conf.set("spark.sql.parquet.compression.codec", "zstd")
```

**Interview tip:** "Zstd is the **best modern default** — it gives Gzip-level compression at near-Snappy speed. If your platform supports it (most do in 2026), switch from Snappy to Zstd."

---

## 5. Gzip — The Archival Standard

| Feature | Detail |
|---------|--------|
| **Created by** | GNU project (1992) |
| **Ratio** | 5-8x (high) |
| **Speed** | ~30 MB/s compress, ~100 MB/s decompress (slower) |
| **Splittable** | NOT splittable (single stream!) |
| **Used in** | Archival, web (HTTP compression), cold storage |

### Gzip Splittability Problem

```
Spark reads a 1GB gzip file:
  → Cannot split into multiple tasks
  → SINGLE task reads entire file
  → No parallelism!

Solution 1: Use Snappy/Zstd (splittable)
Solution 2: Split data into many small gzip files (1 file = 1 task)
Solution 3: Use gzip for archival, Snappy/Zstd for processing
```

**Interview tip:** "Gzip files are **not splittable** — a 10GB gzip file = 1 Spark task = no parallelism. Always use Snappy or Zstd for data that Spark will process."

---

## 6. LZ4 — The Speed Demon

| Feature | Detail |
|---------|--------|
| **Created by** | Yann Collet (2011, same person who later created Zstd) |
| **Ratio** | 2-3x (low) |
| **Speed** | ~400 MB/s compress, ~1000+ MB/s decompress (fastest!) |
| **Used in** | Kafka (message compression), real-time systems, gaming |

### When LZ4 Makes Sense

```
Message broker processing 1M messages/sec:
  LZ4:   Compress at 400MB/s → negligible latency → throughput maintained
  Gzip:  Compress at 30MB/s  → becomes bottleneck → throughput drops

For Kafka with latency SLA < 10ms → LZ4 is the right choice
```

---

## 7. Compression in Different Contexts

### Parquet + Compression

```
Parquet applies compression at the PAGE level:
  Each page (1MB) is individually compressed.
  Different columns can use different codecs (but usually same).

Encoding + Compression stack:
  Raw values 
    → Encoding (dictionary, RLE, delta)   ← reduces data representation
    → Compression (Snappy, Zstd, Gzip)    ← reduces byte size
  
  Encoding is format-specific (Parquet/ORC built-in).
  Compression is codec-specific (applied on top).
```

### Kafka + Compression

| Level | What |
|-------|------|
| **Producer compression** | Producer compresses batch → sends compressed to broker |
| **Broker storage** | Stores compressed (no re-compression) |
| **Consumer decompression** | Consumer decompresses on read |

```
Kafka codec options: none, gzip, snappy, lz4, zstd

Recommendation:
  Low latency: LZ4
  Balanced:    Snappy or Zstd
  Max savings: Gzip (but higher latency)
```

### Spark Configuration

```python
# Parquet compression
spark.conf.set("spark.sql.parquet.compression.codec", "zstd")  # snappy|gzip|lz4|zstd|none

# ORC compression
spark.conf.set("spark.sql.orc.compression.codec", "zlib")  # snappy|zlib|lzo|zstd|none

# General Spark shuffle compression
spark.conf.set("spark.io.compression.codec", "lz4")  # lz4|snappy|zstd
```

---

## 8. Decision Guide

| Use Case | Recommended Codec | Why |
|----------|------------------|-----|
| **Spark batch analytics** | Zstd (or Snappy) | Good ratio + fast decompress |
| **Data lake (Parquet/Delta)** | Zstd | Best ratio at reasonable speed |
| **Kafka messages** | LZ4 or Zstd | Low latency + good compression |
| **Cold/archival storage** | Gzip or Zstd-19 | Maximum compression, read rarely |
| **Real-time streaming** | LZ4 | Fastest compress + decompress |
| **Network transfer** | Gzip or Zstd | Minimize bytes over wire |
| **Spark shuffle** | LZ4 | Speed critical for shuffle data |

---

## 9. Common Interview Questions

| Question | Key Points |
|----------|------------|
| "Why does Spark default to Snappy?" | Fast decompress → queries stay fast. Modest ratio is acceptable trade-off |
| "Snappy vs Gzip vs Zstd?" | Snappy: fast, 2-3x. Gzip: slow, 5-8x. Zstd: balanced, 4-7x (best modern default) |
| "Why is Gzip problematic in Spark?" | Not splittable → single task reads entire file → no parallelism |
| "What compression for Kafka?" | LZ4 for lowest latency. Zstd for best balance. Gzip for max savings |
| "Encoding vs Compression?" | Encoding: format-specific (dictionary, RLE). Compression: codec (Snappy, Zstd) applied on top |
| "How do you choose a codec?" | Trade-off triangle: ratio vs CPU vs speed. Match to use case (hot vs cold data) |

---

## Key Takeaways

- Compression = **three-way trade-off**: file size vs CPU cost vs read/write speed.
- **Snappy**: fast, 2-3x ratio — Spark/Parquet default. Good for hot data.
- **Zstd**: best modern default — Gzip-level ratio at near-Snappy speed. Tunable levels 1-22.
- **Gzip**: best ratio, but slow and **not splittable** — avoid for Spark processing, OK for archival.
- **LZ4**: fastest codec — best for real-time, Kafka, shuffle data.
- **Encoding + Compression**: Parquet applies encoding (dictionary, RLE) first, then compression on top.
- **2026 recommendation**: Switch from Snappy to Zstd for Parquet/Delta. Use LZ4 for Kafka/real-time.

---
