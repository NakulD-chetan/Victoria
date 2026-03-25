# Internals: HTTP Protocol Deep Dive — From HTTP/1.0 to HTTP/3

> **Permanent Recall:** HTTP/1.0 = one request per TCP connection. HTTP/1.1 = keep-alive + pipelining (head-of-line blocking). HTTP/2 = binary framing, multiplexing, HPACK header compression, server push, stream prioritization — all on ONE TCP connection. HTTP/3 = QUIC (UDP-based), no TCP head-of-line blocking, 0-RTT connection setup. Every API call (REST, GraphQL, gRPC) rides on HTTP — understanding the wire format is understanding API performance.

---

## The Evolution: Why Each Version Exists

```
HTTP/1.0 (1996) → HTTP/1.1 (1997) → HTTP/2 (2015) → HTTP/3 (2022)

PROBLEM EACH VERSION SOLVES:

HTTP/1.0:  New TCP connection per request (3-way handshake every time)
           GET /page.html → close → GET /style.css → close → GET /logo.png → close
           3 requests = 3 TCP handshakes = 3 × ~100ms = 300ms overhead

HTTP/1.1:  Keep-alive (reuse connection) + pipelining
           But: head-of-line blocking (request 2 waits for response 1)
           Workaround: browsers open 6 parallel connections per host

HTTP/2:    Binary framing, multiplexing (all requests interleaved on 1 connection)
           Header compression (HPACK)
           But: TCP head-of-line blocking (one lost packet blocks ALL streams)

HTTP/3:    QUIC over UDP — per-stream loss recovery
           0-RTT connection resumption
           No TCP head-of-line blocking
```

---

## HTTP/1.1 — Wire Format (Text-Based)

```
HTTP/1.1 REQUEST (raw bytes on the wire):

  GET /api/v1/users/123 HTTP/1.1\r\n         ← Request line
  Host: api.example.com\r\n                    ← Required header
  Accept: application/json\r\n                 ← Content negotiation
  Authorization: Bearer eyJhbG...\r\n          ← Auth token
  Connection: keep-alive\r\n                   ← Persist connection
  Accept-Encoding: gzip, deflate\r\n           ← Compression
  \r\n                                         ← Empty line = end of headers
                                               ← No body for GET

BYTE-LEVEL:
  "GET " = 0x47 0x45 0x54 0x20
  "/api" = 0x2F 0x61 0x70 0x69
  "\r\n" = 0x0D 0x0A (carriage return + line feed)

  Every character = 1 byte (ASCII)
  Headers are REPEATED in every request
  "Accept: application/json\r\n" = 30 bytes EVERY TIME
  Typical request headers: 200-800 bytes of text

HTTP/1.1 RESPONSE:

  HTTP/1.1 200 OK\r\n                          ← Status line
  Content-Type: application/json\r\n
  Content-Length: 85\r\n
  Cache-Control: max-age=3600\r\n
  ETag: "abc123"\r\n
  X-RateLimit-Remaining: 99\r\n
  \r\n                                         ← End of headers
  {"id":123,"name":"John","email":"john@example.com","created_at":"2024-03-10T12:00:00Z"}
```

### Keep-Alive and Connection Reuse

```
HTTP/1.0 (no keep-alive):
  ┌──────────┐                    ┌──────────┐
  │ Client   │                    │ Server   │
  │          │── TCP SYN ────────►│          │
  │          │◄─ SYN+ACK ────────│          │
  │          │── ACK ────────────►│          │  ← 1.5 RTT to connect
  │          │── GET /users ─────►│          │
  │          │◄─ 200 OK ─────────│          │
  │          │── FIN ────────────►│          │  ← Connection closed
  │          │                    │          │
  │          │── TCP SYN ────────►│          │  ← ANOTHER handshake!
  │          │◄─ SYN+ACK ────────│          │
  │          │── ACK ────────────►│          │
  │          │── GET /orders ────►│          │
  │          │◄─ 200 OK ─────────│          │
  │          │── FIN ────────────►│          │
  └──────────┘                    └──────────┘
  2 requests = 2 TCP handshakes = 2 × 1.5 RTT overhead

HTTP/1.1 (keep-alive, default):
  ┌──────────┐                    ┌──────────┐
  │ Client   │                    │ Server   │
  │          │── TCP SYN ────────►│          │
  │          │◄─ SYN+ACK ────────│          │
  │          │── ACK ────────────►│          │  ← 1 connection
  │          │── GET /users ─────►│          │
  │          │◄─ 200 OK ─────────│          │
  │          │── GET /orders ────►│          │  ← REUSE connection
  │          │◄─ 200 OK ─────────│          │
  │          │── GET /products ──►│          │  ← REUSE again
  │          │◄─ 200 OK ─────────│          │
  └──────────┘                    └──────────┘
  3 requests = 1 TCP handshake = 1 × 1.5 RTT overhead
```

### Head-of-Line Blocking (HTTP/1.1's Biggest Problem)

```
HEAD-OF-LINE BLOCKING:

HTTP/1.1 requires responses in ORDER of requests.
Even with pipelining (send multiple requests without waiting):

  Client sends:  GET /slow   GET /fast   GET /tiny
  Server must respond: /slow(5s) → /fast(10ms) → /tiny(1ms)
  
  /fast and /tiny WAIT for /slow to complete!

  ┌──────────────────────────────────────────────────────────┐
  │ Time ──────────────────────────────────────────────────► │
  │                                                          │
  │ Request 1: GET /slow-api   [============ 5 seconds ====] │
  │ Request 2: GET /fast-api          BLOCKED        [=10ms=]│
  │ Request 3: GET /tiny-api          BLOCKED           [1ms]│
  │                                                          │
  │ Total: 5 seconds + 10ms + 1ms = ~5 seconds              │
  │ Without HOL: max(5s, 10ms, 1ms) = 5s (but others done)  │
  └──────────────────────────────────────────────────────────┘

BROWSER WORKAROUND:
  Open 6 parallel TCP connections to same host
  Each connection: independent request/response pipeline
  6 connections × 1 request each = 6 parallel requests
  But: 6 TCP handshakes, 6 congestion windows, 6× memory

  This is why HTTP/1.1 sites use "domain sharding":
    images1.example.com, images2.example.com
    Browser opens 6 connections per domain = 12 parallel
```

---

## HTTP/2 — Binary Framing Revolution

```
HTTP/2 CORE INNOVATION:

All communication split into BINARY FRAMES on a SINGLE TCP connection.
Multiple requests/responses INTERLEAVED (multiplexed) on same connection.

┌──────────────────────────────────────────────────────────────┐
│                   SINGLE TCP CONNECTION                        │
│                                                              │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐         │
│  │Str 1│ │Str 3│ │Str 1│ │Str 5│ │Str 3│ │Str 1│         │
│  │HDRS │ │HDRS │ │DATA │ │HDRS │ │DATA │ │DATA │         │
│  │frame│ │frame│ │frame│ │frame│ │frame│ │frame│         │
│  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘         │
│                                                              │
│  Stream 1: GET /users     (headers, then data frames)        │
│  Stream 3: GET /orders    (interleaved with stream 1)        │
│  Stream 5: POST /payment  (can start before others finish)   │
│                                                              │
│  NO head-of-line blocking at HTTP level!                     │
│  (Still HOL at TCP level — see HTTP/3)                       │
└──────────────────────────────────────────────────────────────┘
```

### HTTP/2 Frame Format (Binary)

```
HTTP/2 FRAME (9-byte header + payload):

  ┌───────────────────────────────────────────────────┐
  │ Bytes 0-2:  Length (24 bits) — payload size        │
  │             Max: 2^24 - 1 = 16,777,215 bytes      │
  │             Default max: 16,384 (16 KB)            │
  │ Byte 3:    Type (8 bits):                          │
  │             0x0 = DATA                             │
  │             0x1 = HEADERS                          │
  │             0x2 = PRIORITY                         │
  │             0x3 = RST_STREAM                       │
  │             0x4 = SETTINGS                         │
  │             0x5 = PUSH_PROMISE                     │
  │             0x6 = PING                             │
  │             0x7 = GOAWAY                           │
  │             0x8 = WINDOW_UPDATE                    │
  │             0x9 = CONTINUATION                     │
  │ Byte 4:    Flags (8 bits):                         │
  │             END_STREAM (0x1)                       │
  │             END_HEADERS (0x4)                      │
  │             PADDED (0x8)                           │
  │             PRIORITY (0x20)                        │
  │ Bytes 5-8: Stream ID (31 bits + 1 reserved)       │
  │             0 = connection-level frame             │
  │             Odd = client-initiated                  │
  │             Even = server-initiated (push)          │
  ├───────────────────────────────────────────────────┤
  │ Bytes 9+:  Payload (type-specific)                 │
  └───────────────────────────────────────────────────┘

EXAMPLE: GET /api/v1/users/123

  HEADERS frame (stream 1):
    ┌────────────────────────────────────────────────┐
    │ Length: 45                                      │
    │ Type: 0x01 (HEADERS)                           │
    │ Flags: 0x05 (END_STREAM | END_HEADERS)         │
    │ Stream ID: 1                                   │
    │ Payload: HPACK-encoded headers:                │
    │   :method = GET                                │
    │   :path = /api/v1/users/123                    │
    │   :scheme = https                              │
    │   :authority = api.example.com                  │
    │   accept = application/json                    │
    │   authorization = Bearer eyJ...                │
    └────────────────────────────────────────────────┘

  Response HEADERS frame (stream 1):
    ┌────────────────────────────────────────────────┐
    │ Length: 25                                      │
    │ Type: 0x01 (HEADERS)                           │
    │ Flags: 0x04 (END_HEADERS)                      │
    │ Stream ID: 1                                   │
    │ Payload: HPACK-encoded:                        │
    │   :status = 200                                │
    │   content-type = application/json              │
    └────────────────────────────────────────────────┘

  Response DATA frame (stream 1):
    ┌────────────────────────────────────────────────┐
    │ Length: 85                                      │
    │ Type: 0x00 (DATA)                              │
    │ Flags: 0x01 (END_STREAM)                       │
    │ Stream ID: 1                                   │
    │ Payload: {"id":123,"name":"John",...}           │
    └────────────────────────────────────────────────┘
```

```

HPACK solution: headeHPACK — Header Compression
```

```
HPACK — WHY HTTP/2 HEADERS ARE TINY:

HTTP/1.1 problem:
  Every request repeats ALL headers (Host, Accept, Authorization...)
  Typical: 200-800 bytes of headers × 100 requests = 20-80 KB wasted
  Headers can't be gzip'd (CRIME attack vulnerability)
r-specific compression
  Three techniques combined:

1. STATIC TABLE (61 pre-defined headers):
   ┌───────┬──────────────────┬───────────────────────┐
   │ Index │ Header Name      │ Header Value          │
   ├───────┼──────────────────┼───────────────────────┤
   │ 1     │ :authority       │                       │
   │ 2     │ :method          │ GET                   │
   │ 3     │ :method          │ POST                  │
   │ 4     │ :path            │ /                     │
   │ 5     │ :path            │ /index.html           │
   │ 6     │ :scheme          │ http                  │
   │ 7     │ :scheme          │ https                 │
   │ 8     │ :status          │ 200                   │
   │ ...   │ ...              │ ...                   │
   │ 61    │ www-authenticate │                       │
   └───────┴──────────────────┴───────────────────────┘

   ":method: GET" = just index 2 = 1 BYTE instead of 12 bytes!

2. DYNAMIC TABLE (connection-specific):
   Headers seen before are added to a dynamic table.
   Second request with same "authorization: Bearer eyJ..."
   → just reference index 62 = 1-2 bytes instead of ~500 bytes!

   ┌───────────────────────────────────────────────────────┐
   │ Request 1: authorization: Bearer eyJhbGciOiJIUzI1... │
   │   → Sent in full (500 bytes)                          │
   │   → Added to dynamic table as index 62                │
   │                                                       │
   │ Request 2: authorization: Bearer eyJhbGciOiJIUzI1... │
   │   → Just send index 62 = 1 byte!                     │
   │   → 500x compression for repeated headers!            │
   └───────────────────────────────────────────────────────┘

3. HUFFMAN CODING:
   Frequently used characters get shorter bit sequences.
   'e' = 5 bits (00101), 'a' = 5 bits (00011)
   vs. ASCII: every char = 8 bits
   ~30% savings on header values

RESULT:
  First request headers: ~200 bytes (vs 500 in HTTP/1.1)
  Subsequent requests: ~20-50 bytes (dynamic table refs!)
  At 10,000 requests: saves ~5 MB of header overhead
```

### HTTP/2 Multiplexing — How It Works

```
MULTIPLEXING INTERNALS:

Each HTTP request/response = one STREAM (identified by stream ID)
Streams are independent: can be created, used, closed independently
ALL streams share ONE TCP connection

FLOW CONTROL (per-stream AND per-connection):
  ┌──────────────────────────────────────────────────────────┐
  │ HTTP/2 FLOW CONTROL:                                     │
  │                                                          │
  │ Each stream has a flow control WINDOW (default 65,535 B) │
  │ Sender can send up to window size of DATA frames         │
  │ Receiver sends WINDOW_UPDATE to grant more space         │
  │                                                          │
  │ Connection-level window: total DATA across ALL streams   │
  │ Stream-level window: DATA for one specific stream        │
  │                                                          │
  │ Stream 1 window: 65535 ──send 10000──► 55535             │
  │ Stream 3 window: 65535 ──send 65535──► 0 (blocked!)      │
  │   → Stream 3 waits for WINDOW_UPDATE from receiver       │
  │   → Stream 1 can still send (independent windows)        │
  │                                                          │
  │ This prevents one large response from starving others    │
  └──────────────────────────────────────────────────────────┘

STREAM STATES:
  idle → open → half-closed (local/remote) → closed

  Client sends HEADERS → stream becomes "open"
  Client sends END_STREAM → "half-closed (local)"
  Server sends END_STREAM → stream "closed"

STREAM PRIORITIZATION:
  Client can tell server: "Stream 1 is more important than Stream 3"
  Weight: 1-256 (relative priority)
  Dependencies: Stream 5 depends on Stream 1

  Used for: load critical CSS before images
  gRPC uses this for request prioritization
```

### TCP Head-of-Line Blocking (HTTP/2's Remaining Problem)

```
TCP HEAD-OF-LINE BLOCKING:

HTTP/2 solved HTTP-level HOL blocking (streams are independent).
But ALL streams share ONE TCP connection.
TCP guarantees in-order byte delivery.

PROBLEM:
  ┌──────────────────────────────────────────────────────────┐
  │ TCP sends segments: [S1-A] [S3-B] [S1-C] [S5-D] [S3-E] │
  │                                                          │
  │ Segment [S3-B] is LOST (packet loss)                     │
  │                                                          │
  │ TCP must retransmit [S3-B] before delivering [S1-C]      │
  │ Even though [S1-C] is for a DIFFERENT stream!            │
  │                                                          │
  │ Stream 1 and Stream 5 are BLOCKED waiting for            │
  │ Stream 3's retransmission                                │
  │                                                          │
  │ At 1% packet loss: HTTP/2 can be SLOWER than HTTP/1.1   │
  │ (HTTP/1.1 with 6 connections: loss on 1 doesn't block 5) │
  └──────────────────────────────────────────────────────────┘

This is why HTTP/3 was created (QUIC over UDP).
```

---

## HTTP/3 and QUIC — UDP-Based Transport

```
HTTP/3 ARCHITECTURE:

HTTP/1.1:  HTTP  → TCP  → IP
HTTP/2:    HTTP  → TCP  → IP
HTTP/3:    HTTP  → QUIC → UDP → IP

QUIC (Quick UDP Internet Connections):
  ┌──────────────────────────────────────────────────────────┐
  │ QUIC RUNS OVER UDP:                                      │
  │                                                          │
  │ Why UDP not TCP?                                         │
  │   TCP is in the kernel (can't change it easily)          │
  │   UDP is a thin wrapper (no ordering, no retransmission) │
  │   QUIC implements reliability IN USERSPACE               │
  │   Can be updated without kernel changes!                 │
  │                                                          │
  │ QUIC PROVIDES:                                           │
  │   ✓ Reliable delivery (like TCP)                         │
  │   ✓ Congestion control (like TCP)                        │
  │   ✓ TLS 1.3 encryption (built-in, not optional)         │
  │   ✓ Per-stream loss recovery (no cross-stream HOL!)      │
  │   ✓ Connection migration (change IP without reconnect)   │
  │   ✓ 0-RTT connection resumption                          │
  └──────────────────────────────────────────────────────────┘

NO TCP HEAD-OF-LINE BLOCKING:
  ┌──────────────────────────────────────────────────────────┐
  │ QUIC treats each stream independently:                   │
  │                                                          │
  │ Stream 1: [pkt A] [pkt C] ← received, delivered         │
  │ Stream 3: [pkt B] LOST    ← retransmit only stream 3    │
  │ Stream 5: [pkt D] [pkt E] ← received, delivered         │
  │                                                          │
  │ Packet B loss blocks ONLY Stream 3                       │
  │ Streams 1 and 5 continue normally!                       │
  └──────────────────────────────────────────────────────────┘

0-RTT CONNECTION SETUP:
  TCP + TLS 1.3:       1 RTT (TCP) + 1 RTT (TLS) = 2 RTT
  QUIC first connect:  1 RTT (QUIC handshake includes TLS)
  QUIC resumption:     0 RTT (cached keys → send data immediately!)

  ┌──────────────────────────────────────────────────────────┐
  │ QUIC 0-RTT:                                              │
  │                                                          │
  │ Client has cached session ticket from previous connection│
  │ Client sends: QUIC Initial + TLS early data + HTTP req   │
  │ All in FIRST packet!                                      │
  │ Server responds immediately with data                    │
  │                                                          │
  │ Latency: 0 round trips before data flows                 │
  │ vs TCP+TLS: 2-3 round trips                              │
  │ At 100ms RTT: saves 200-300ms per new connection         │
  └──────────────────────────────────────────────────────────┘

CONNECTION MIGRATION:
  TCP: connection = (src IP, src port, dst IP, dst port)
       Change IP (WiFi → cellular) → new connection needed
  QUIC: connection = Connection ID (random token)
        Change IP → same Connection ID → connection survives!
        Phone switching networks: no interruption
```

---

## HTTP Connection Lifecycle at Kernel Level

```
WHAT HAPPENS WHEN YOU CALL fetch('/api/users'):

BROWSER / CLIENT:
  1. DNS lookup: api.example.com → 93.184.216.34
     Check: browser DNS cache → OS DNS cache → resolver
     Time: 0ms (cached) to 50ms (remote lookup)

  2. TCP connect: SYN → SYN+ACK → ACK
     Kernel: socket() → connect()
     Time: 1 RTT (~1ms same DC, ~100ms cross-continent)

  3. TLS handshake: ClientHello → ServerHello → keys
     Time: 1-2 RTT (~2-200ms)
     (covered in detail in TLS file)

  4. HTTP request: send bytes over TLS
     Kernel: write() → TLS encrypt → TCP segment → IP → NIC

  5. Wait for response
     Server processes → sends response bytes
     Kernel: NIC → IP → TCP → TLS decrypt → read()

  6. Connection reuse or close
     Keep-alive: connection stays open for next request
     HTTP/2: same connection for ALL requests to this host

TOTAL LATENCY (first request, cross-continent):
  DNS:        0-50 ms
  TCP:        100 ms (1 RTT)
  TLS:        200 ms (2 RTT for TLS 1.2, 1 RTT for TLS 1.3)
  Request:    100 ms (1 RTT for request + response)
  ────────────────────
  Total:      400-450 ms (first request)
  Second request (same connection): ~100 ms (just 1 RTT)

THIS IS WHY CONNECTION REUSE MATTERS:
  Without keep-alive: 450ms per request
  With keep-alive: 450ms first, then 100ms each
  HTTP/2: 450ms first, then ALL requests share one connection
  HTTP/3 0-RTT: 100ms even for first request (resumed)
```

---

## HTTP/2 Connection Setup (Upgrade or ALPN)

```
HTTP/2 CONNECTION NEGOTIATION:

METHOD 1: ALPN (Application-Layer Protocol Negotiation, used with TLS):
  ┌──────────────────────────────────────────────────────────┐
  │ During TLS handshake:                                    │
  │                                                          │
  │ ClientHello includes ALPN extension:                     │
  │   protocols: ["h2", "http/1.1"]                         │
  │   "I support HTTP/2 and HTTP/1.1"                       │
  │                                                          │
  │ ServerHello responds:                                    │
  │   selected_protocol: "h2"                                │
  │   "Let's use HTTP/2"                                     │
  │                                                          │
  │ After TLS handshake: both sides know it's HTTP/2        │
  │ No extra round trips needed!                             │
  └──────────────────────────────────────────────────────────┘

METHOD 2: HTTP Upgrade (cleartext, rare):
  Client: GET / HTTP/1.1
          Upgrade: h2c
          HTTP2-Settings: <base64-encoded SETTINGS>

  Server: HTTP/1.1 101 Switching Protocols
          Upgrade: h2c

HTTP/2 CONNECTION PREFACE (after negotiation):
  Client sends magic string (24 bytes):
    "PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
    (0x505249202a20485454502f322e300d0a0d0a534d0d0a0d0a)

  Then client sends SETTINGS frame (stream 0):
    HEADER_TABLE_SIZE = 4096
    ENABLE_PUSH = 1
    MAX_CONCURRENT_STREAMS = 100
    INITIAL_WINDOW_SIZE = 65535
    MAX_FRAME_SIZE = 16384
    MAX_HEADER_LIST_SIZE = 8192

  Server sends its SETTINGS frame
  Both sides ACK each other's SETTINGS
  Connection ready for streams!
```

---

## Comparison: Wire Overhead Per API Request

```
OVERHEAD COMPARISON FOR "GET /api/v1/users/123":

HTTP/1.1 (text, no compression):
  Request:
    "GET /api/v1/users/123 HTTP/1.1\r\n"               31 bytes
    "Host: api.example.com\r\n"                          24 bytes
    "Accept: application/json\r\n"                       28 bytes
    "Authorization: Bearer eyJhbGc...500chars\r\n"      520 bytes
    "Accept-Encoding: gzip\r\n"                          23 bytes
    "Connection: keep-alive\r\n"                         24 bytes
    "\r\n"                                                2 bytes
    ──────────────────────────────────────
    Total: ~652 bytes

HTTP/2 (binary, HPACK, first request):
  HEADERS frame:
    Frame header:                                         9 bytes
    :method GET (static table index 2):                   1 byte
    :path /api/v1/users/123 (literal, Huffman):         ~18 bytes
    :scheme https (static table index 7):                 1 byte
    :authority api.example.com (literal, Huffman):       ~15 bytes
    accept application/json (near-static):               ~3 bytes
    authorization Bearer eyJ... (literal):             ~400 bytes
    ──────────────────────────────────────
    Total: ~447 bytes (31% smaller)

HTTP/2 (same request, second time — dynamic table):
  HEADERS frame:
    Frame header:                                         9 bytes
    :method GET:                                          1 byte
    :path (changed, literal):                           ~18 bytes
    :scheme, :authority (dynamic table ref):              2 bytes
    accept (dynamic table ref):                           1 byte
    authorization (dynamic table ref):                    1 byte
    ──────────────────────────────────────
    Total: ~32 bytes (95% smaller than HTTP/1.1!)

SAVINGS AT SCALE (1M API requests):
  HTTP/1.1:  652 bytes × 1M = 652 MB of headers
  HTTP/2:    ~50 bytes avg × 1M = 50 MB of headers
  Savings:   602 MB of bandwidth just for headers!
```

---

## Server Push (HTTP/2)

```
SERVER PUSH — PREEMPTIVE RESOURCE DELIVERY:

Server sends resources BEFORE client requests them.

  Normal:                            With Push:
  Client: GET /page.html             Client: GET /page.html
  Server: 200 /page.html             Server: 200 /page.html
  Client: GET /style.css                   + PUSH_PROMISE /style.css
  Server: 200 /style.css                   + DATA /style.css (pushed)
  Client: GET /app.js                      + PUSH_PROMISE /app.js
  Server: 200 /app.js                     + DATA /app.js (pushed)

  Without push: 3 round trips      With push: 1 round trip!

HOW IT WORKS:
  1. Server sends PUSH_PROMISE frame on original stream
     Contains: request headers that the pushed resource would have
  2. Client can RST_STREAM the push (reject if already cached)
  3. Server sends HEADERS + DATA frames on a new (even) stream ID

LIMITATIONS:
  Same-origin only (can't push cross-origin resources)
  Client can disable push (SETTINGS ENABLE_PUSH = 0)
  Pushing resources the client already cached = waste
  In practice: mostly replaced by 103 Early Hints
```

---

## 30-SECOND REVISION BOX

```
HTTP/1.0: new TCP per request (slow)
HTTP/1.1: keep-alive, text headers, HOL blocking, 6 connections/host
HTTP/2: binary frames, streams, multiplexing, HPACK, 1 TCP connection
  Frame: 9-byte header (length, type, flags, stream ID) + payload
  HPACK: static table (61) + dynamic table + Huffman = 95% smaller headers
  Flow control: per-stream + per-connection windows
  Still TCP HOL: one lost packet blocks all streams
HTTP/3: QUIC over UDP, per-stream recovery, 0-RTT, connection migration
LATENCY: first request 400ms (TCP+TLS+HTTP), subsequent 100ms (reuse)
```

---

**Prev: [[08_Question-List]] | Next: [[10_Internals-TLS-Handshake-Cryptography]]**