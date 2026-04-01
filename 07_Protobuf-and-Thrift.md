# 07 — Protocol Buffers (Protobuf) & Thrift

> **One-line:** Protobuf (Google) and Thrift (Facebook) are **binary serialization** formats that use **numbered field IDs** and **code generation** — smaller and faster than JSON/Avro, widely used in **gRPC**, **microservices**, and **high-performance** data pipelines.

---

## 1. Why Protobuf Matters for DE

| Reason | Detail |
|--------|--------|
| **gRPC standard** | Google's RPC framework uses Protobuf — increasingly used in data platform APIs |
| **Smaller than Avro** | 20-30% smaller for same data — critical at billions of messages |
| **Faster** | No runtime schema parsing — compiled schemas in generated code |
| **Used by** | Google, Uber, Netflix, Confluent (Kafka supports Protobuf via Schema Registry) |

---

## 2. Protobuf Schema Definition (.proto file)

```protobuf
syntax = "proto3";

package com.company.events;

message Customer {
  int64 id = 1;             // field number 1
  string name = 2;           // field number 2
  string email = 3;          // field number 3
  int32 age = 4;             // field number 4
  
  Address address = 5;       // nested message
  repeated string tags = 6;  // repeated = list/array
  
  enum Status {
    UNKNOWN = 0;
    ACTIVE = 1;
    INACTIVE = 2;
  }
  Status status = 7;
}

message Address {
  string city = 1;
  string state = 2;
  string zip = 3;
}
```

### Key Concepts

| Concept | Detail |
|---------|--------|
| **Field numbers** | Each field has a unique number — used in binary encoding (not the name) |
| **Never reuse** | Deleted field numbers should NEVER be reused |
| **`repeated`** | Array/list of values |
| **`oneof`** | Union — exactly one of the fields is set |
| **`map`** | Key-value pairs: `map<string, int32>` |
| **Nested messages** | Messages can contain other messages |
| **`optional`** | Field may or may not be present (proto3 all fields are optional by default) |

---

## 3. How Protobuf Encoding Works (Wire Format)

```
Each field encoded as: [field_number << 3 | wire_type] [value]

Wire types:
  0 = Varint (int32, int64, bool, enum)
  1 = 64-bit (fixed64, double)
  2 = Length-delimited (string, bytes, nested messages, repeated)
  5 = 32-bit (fixed32, float)

Example: id = 150 (field number 1, type int64)
  Tag:   0x08 (field 1, wire type 0)
  Value: 0x96 0x01 (varint encoding of 150)
  Total: 3 bytes

Same in JSON: "id": 150 → 9 bytes
Protobuf is 3x smaller just for this one field.
```

**Interview tip:** "Protobuf uses **field numbers** in the binary encoding, not field **names**. This is why it's so compact — no string field names in the payload."

---

## 4. Schema Evolution in Protobuf

| Change | Safe? | Rule |
|--------|-------|------|
| **Add new field** | Yes | Old readers ignore unknown field numbers |
| **Remove field** | Yes (but reserve number) | Mark as `reserved` — never reuse the number |
| **Rename field** | Yes | Binary uses field NUMBER, not name |
| **Change field number** | NO | Breaks everything — field number IS the identity |
| **Change type (compatible)** | Some | int32 → int64 OK. string → int32 NOT OK |
| **Change required ↔ optional** | Careful | proto3: all optional. proto2: more complex |

### Reserved Fields

```protobuf
message Customer {
  reserved 4, 8;                    // reserved field numbers
  reserved "old_phone", "legacy_id"; // reserved names
  
  int64 id = 1;
  string name = 2;
  // field 4 was "age" — removed but number reserved forever
}
```

---

## 5. Protobuf vs Avro vs JSON

| Feature | Protobuf | Avro | JSON |
|---------|----------|------|------|
| **Format** | Binary | Binary | Text |
| **Schema** | `.proto` file (compiled) | JSON schema (embedded) | None (or JSON Schema) |
| **Schema in payload** | No (only field numbers) | Yes (in file header) | Field names in every record |
| **Code generation** | Required (protoc compiler) | Optional | None |
| **Size** | Smallest | Small | Largest |
| **Speed** | Fastest (compiled) | Fast | Slowest (parsing) |
| **Schema evolution** | Field numbers | Field names + defaults | No enforcement |
| **Self-describing** | No (need .proto to decode) | Yes (schema in file) | Yes (field names present) |
| **Dynamic reading** | Harder (need compiled schema) | Easy (schema embedded) | Easy |
| **Best for** | gRPC, high-perf services | Kafka, CDC, data exchange | APIs, configs, humans |

### Size Comparison (Same Record)

```
Record: {id: 12345, name: "Alice", email: "alice@test.com", age: 30}

JSON:      ~65 bytes
Avro:      ~30 bytes
Protobuf:  ~25 bytes
```

---

## 6. Apache Thrift (Brief)

| Feature | Detail |
|---------|--------|
| **Created by** | Facebook (now Apache project) |
| **Similar to** | Protobuf (binary serialization with IDL) |
| **Includes** | RPC framework built-in (like gRPC for Protobuf) |
| **Used by** | Hive (Thrift server), HBase, Cassandra (internal protocol) |
| **Schema** | `.thrift` IDL files |

### Thrift Schema Example

```thrift
struct Customer {
  1: required i64 id,
  2: required string name,
  3: optional string email,
  4: optional i32 age
}

service CustomerService {
  Customer getCustomer(1: i64 id),
  list<Customer> searchCustomers(1: string query)
}
```

### Protobuf vs Thrift

| Dimension | Protobuf | Thrift |
|-----------|----------|--------|
| **Creator** | Google | Facebook |
| **RPC** | gRPC (separate) | Built-in |
| **Adoption** | Much wider (2026) | Declining (legacy Hadoop tools) |
| **Protocols** | Binary only | Binary, compact, JSON, etc. |
| **Performance** | Slightly faster | Comparable |
| **DE relevance** | gRPC APIs, Kafka, Confluent | Hive Thrift Server, legacy |

**Interview tip:** "In 2026, Protobuf + gRPC has largely **replaced** Thrift for new projects. Thrift is mainly seen in legacy Hadoop components (Hive Thrift Server, HBase)."

---

## 7. Protobuf with Kafka (Schema Registry)

```
Confluent Schema Registry supports:
  1. Avro schemas   (most common)
  2. Protobuf schemas (growing)
  3. JSON Schema     (least common)

Wire format is the same:
  [0x00] [4-byte schema ID] [protobuf binary payload]

Producer → registers .proto schema → gets ID → sends (ID + payload)
Consumer → fetches schema by ID → deserializes with generated code
```

---

## 8. Common Interview Questions

| Question | Key Points |
|----------|------------|
| "What is Protobuf?" | Binary serialization using numbered fields + code generation. Google's standard |
| "Protobuf vs Avro?" | Protobuf: faster, smaller, needs codegen. Avro: self-describing, dynamic, embedded schema |
| "Why is Protobuf smaller than JSON?" | No field names in payload (just field numbers), binary encoding (varint), no delimiters |
| "How does Protobuf schema evolution work?" | Field numbers are identity. Add/remove OK. Never reuse/change field numbers |
| "What is gRPC?" | Google's RPC framework using Protobuf. HTTP/2, bidirectional streaming, code generation |
| "Protobuf vs Thrift?" | Protobuf: wider adoption, gRPC. Thrift: built-in RPC, legacy Hadoop usage |
| "Can Kafka use Protobuf?" | Yes — Confluent Schema Registry supports Protobuf schemas alongside Avro |

---

## Key Takeaways

- **Protobuf** = binary serialization with **numbered field IDs** — smallest size, fastest serialization.
- Schema in `.proto` files → compiled to code with `protoc` → type-safe, fast.
- **Field numbers are sacred** — never change, never reuse. This enables schema evolution.
- **25-30% smaller** than Avro, **3x smaller** than JSON for same data.
- **gRPC** (Protobuf + HTTP/2) is the standard for inter-service communication.
- **Thrift** is similar but declining — mainly seen in legacy Hadoop (Hive Thrift Server).
- Kafka Schema Registry supports **Protobuf** alongside Avro.
- Use **Protobuf** for high-performance services. Use **Avro** for self-describing data exchange.

---
