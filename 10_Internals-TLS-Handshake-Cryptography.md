# Internals: TLS Handshake and Cryptography

> **Permanent Recall:** TLS wraps every HTTPS API call. TLS 1.2: 2-RTT handshake (ClientHello → ServerHello+Cert → KeyExchange → Finished). TLS 1.3: 1-RTT (merged steps, forward secrecy mandatory, 0-RTT resumption). Certificate chain: server cert → intermediate CA → root CA (pinned in browser/OS). Key exchange: ECDHE (Elliptic Curve Diffie-Hellman Ephemeral) generates shared secret. Symmetric encryption (AES-256-GCM or ChaCha20-Poly1305) for bulk data. Every API request is: TCP → TLS → HTTP inside encrypted tunnel.

---

## Why TLS Matters for API Design

```
EVERY API CALL OVER HTTPS:

  Application: fetch("https://api.example.com/users/123")

  What actually happens:
    1. TCP 3-way handshake                    (~1 RTT)
    2. TLS handshake (key exchange, auth)     (~1-2 RTT)
    3. HTTP request/response (encrypted)       (~1 RTT)

  TLS adds 1-2 round trips of latency to EVERY new connection.
  At 100ms RTT: that's 100-200ms added latency.

  This is why:
    - Connection pooling matters (reuse TLS connections)
    - HTTP/2 matters (one TLS connection for all requests)
    - TLS 1.3 matters (1 RTT instead of 2)
    - 0-RTT matters (0 additional RTT for resumption)
    - gRPC uses long-lived HTTP/2 connections (amortize TLS cost)
```

---

## TLS 1.2 Handshake — Full Detail

```
TLS 1.2 HANDSHAKE (2 round trips):

Client                                          Server
  │                                                │
  │  1. ClientHello                                │
  │  ──────────────────────────────────────────►   │
  │  • Protocol version: TLS 1.2                   │
  │  • Client random (32 bytes)                    │
  │  • Session ID (for resumption)                 │
  │  • Cipher suites (ordered preference):         │
  │    [TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,     │
  │     TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256,     │
  │     ...]                                       │
  │  • Extensions: SNI, ALPN, etc.                 │
  │                                                │
  │  2. ServerHello                                │
  │  ◄──────────────────────────────────────────   │
  │  • Protocol version: TLS 1.2                   │
  │  • Server random (32 bytes)                    │
  │  • Selected cipher suite                       │
  │  • Session ID                                  │
  │                                                │
  │  3. Certificate                                │
  │  ◄──────────────────────────────────────────   │
  │  • Server's X.509 certificate chain            │
  │  • [Server cert] → [Intermediate CA] → [Root]  │
  │                                                │
  │  4. ServerKeyExchange (for ECDHE)              │
  │  ◄──────────────────────────────────────────   │
  │  • ECDHE params: curve name, server public key │
  │  • Signed with server's RSA/ECDSA private key  │
  │                                                │
  │  5. ServerHelloDone                            │
  │  ◄──────────────────────────────────────────   │
  │                                                │  ← End of RTT 1
  │                                                │
  │  6. ClientKeyExchange                          │
  │  ──────────────────────────────────────────►   │
  │  • Client's ECDHE public key                   │
  │  • Both sides now compute shared secret:       │
  │    shared_secret = ECDH(client_priv, server_pub)│
  │                  = ECDH(server_priv, client_pub)│
  │                                                │
  │  7. ChangeCipherSpec                           │
  │  ──────────────────────────────────────────►   │
  │  • "From now on, everything is encrypted"      │
  │                                                │
  │  8. Finished (encrypted)                       │
  │  ──────────────────────────────────────────►   │
  │  • HMAC of all handshake messages              │
  │  • Proves both sides have same keys            │
  │                                                │
  │  9. ChangeCipherSpec                           │
  │  ◄──────────────────────────────────────────   │
  │                                                │
  │  10. Finished (encrypted)                      │
  │  ◄──────────────────────────────────────────   │
  │                                                │  ← End of RTT 2
  │                                                │
  │  === HANDSHAKE COMPLETE ===                    │
  │  All subsequent data encrypted with AES-GCM    │
  │                                                │
  │  11. HTTP Request (encrypted)                  │
  │  ──────────────────────────────────────────►   │
  │  GET /api/v1/users/123                         │
  │                                                │
```

---

## TLS 1.3 Handshake — 1 RTT

```
TLS 1.3 HANDSHAKE (1 round trip — merged steps):

Client                                          Server
  │                                                │
  │  1. ClientHello                                │
  │  ──────────────────────────────────────────►   │
  │  • Protocol version: TLS 1.3                   │
  │  • Client random (32 bytes)                    │
  │  • Cipher suites: [AES_256_GCM_SHA384, ...]    │
  │  • Key share: client's ECDHE public key        │
  │    (SPECULATIVELY included — no wait!)         │
  │  • Supported groups: [x25519, secp256r1]       │
  │  • ALPN: [h2, http/1.1]                       │
  │                                                │
  │  2. ServerHello + EncryptedExtensions +        │
  │     Certificate + CertificateVerify + Finished │
  │  ◄──────────────────────────────────────────   │
  │  • Server random                               │
  │  • Selected cipher suite                       │
  │  • Server's ECDHE public key                   │
  │  • == Encryption starts HERE ==                │
  │  • Certificate chain (encrypted!)              │
  │  • Signature proving server owns cert          │
  │  • Finished (HMAC of transcript)               │
  │                                                │  ← End of RTT 1
  │                                                │
  │  3. Finished (encrypted)                       │
  │  ──────────────────────────────────────────►   │
  │  • Client Finished (HMAC)                      │
  │                                                │
  │  At this point, client can ALREADY send HTTP!  │
  │  4. HTTP Request (encrypted, same flight)      │
  │  ──────────────────────────────────────────►   │
  │                                                │
  │  Total: 1 RTT for handshake + first request    │
  │  (vs 2 RTT in TLS 1.2)                        │

KEY INSIGHT — WHY 1 RTT:
  TLS 1.2: client waits for server's key exchange params
           THEN sends its own key exchange
           = 2 round trips

  TLS 1.3: client GUESSES which key exchange method server will use
           Sends its public key in ClientHello speculatively
           If server agrees: saves 1 entire round trip!
           If server disagrees: HelloRetryRequest (rare, adds 1 RTT)
```

### 0-RTT Resumption (TLS 1.3)

```
0-RTT EARLY DATA:

After first connection, server gives client a "session ticket."
On reconnection, client uses ticket to send data IMMEDIATELY.

  Previous connection:
    Server → Client: NewSessionTicket (encrypted, contains PSK)
    Client stores: PSK (Pre-Shared Key) + server config

  Resumed connection:
  ┌──────────────────────────────────────────────────────────┐
  │ Client sends IN ONE PACKET:                              │
  │                                                          │
  │   ClientHello                                            │
  │     + pre_shared_key extension (PSK from ticket)         │
  │     + early_data extension ("I'm sending 0-RTT data")    │
  │   + Application Data (HTTP request, encrypted with PSK)  │
  │                                                          │
  │ Server can process the HTTP request IMMEDIATELY          │
  │ Before handshake even completes!                         │
  │                                                          │
  │ Total: 0 round trips of overhead!                        │
  │ (Data sent with first packet)                            │
  │                                                          │
  │ SECURITY CONCERN:                                        │
  │   0-RTT data is NOT forward-secret (uses cached PSK)     │
  │   0-RTT data is REPLAYABLE (attacker can resend)         │
  │   Only safe for idempotent requests (GET, not POST)      │
  │   Servers must implement anti-replay mechanisms           │
  └──────────────────────────────────────────────────────────┘
```

---

## Certificate Chain Verification

```
CERTIFICATE CHAIN — HOW THE SERVER IS AUTHENTICATED:

Server sends a CHAIN of certificates:

  ┌──────────────────────────────────────────────────────────┐
  │                                                          │
  │  Server cert (leaf):                                     │
  │    Subject: CN=api.example.com                           │
  │    Issuer: CN=Let's Encrypt Authority X3                 │
  │    Public key: RSA 2048-bit or ECDSA P-256               │
  │    Validity: 2024-01-01 to 2024-04-01 (90 days)         │
  │    Signature: signed by issuer's private key             │
  │         │                                                │
  │         ▼                                                │
  │  Intermediate CA cert:                                   │
  │    Subject: CN=Let's Encrypt Authority X3                │
  │    Issuer: CN=DST Root CA X3                             │
  │    Signature: signed by root CA's private key            │
  │         │                                                │
  │         ▼                                                │
  │  Root CA cert (pre-installed in OS/browser):             │
  │    Subject: CN=DST Root CA X3                            │
  │    Self-signed                                           │
  │    Stored in: /etc/ssl/certs/ (Linux)                    │
  │               Keychain (macOS)                           │
  │               Certificate Store (Windows)                │
  │                                                          │
  └──────────────────────────────────────────────────────────┘

VERIFICATION STEPS:
  1. Check chain: leaf → intermediate → root (must form valid chain)
  2. Check signatures: each cert signed by the next cert's key
  3. Check root: root cert must be in trusted store (pre-installed)
  4. Check validity: not before, not after dates
  5. Check revocation: OCSP (online check) or CRL (revocation list)
  6. Check hostname: cert's CN or SAN matches requested domain
     api.example.com must match cert's *.example.com or api.example.com

IF ANY CHECK FAILS:
  Browser: shows certificate warning (user can override)
  API client: connection refused (ERR_CERT_AUTHORITY_INVALID)
  curl: "SSL certificate problem: unable to get local issuer certificate"
  In code: SSLHandshakeException / CERTIFICATE_VERIFY_FAILED
```

---

## Key Exchange: ECDHE (Elliptic Curve Diffie-Hellman Ephemeral)

```
ECDHE — HOW TWO STRANGERS AGREE ON A SHARED SECRET:

The Diffie-Hellman problem: Alice and Bob need a shared secret,
but they can only communicate over a public channel (the internet).

ECDHE WITH CURVE25519:

  1. Both agree on curve parameters (public knowledge):
     Curve: x25519 (Curve25519)
     Base point G (generator point on the curve)

  2. Client generates ephemeral key pair:
     client_private = random 32 bytes
     client_public = client_private × G  (point multiplication on curve)
     Sends client_public in ClientHello

  3. Server generates ephemeral key pair:
     server_private = random 32 bytes
     server_public = server_private × G
     Sends server_public in ServerHello

  4. Both compute the SAME shared secret:
     Client: shared = client_private × server_public
                    = client_private × (server_private × G)
     Server: shared = server_private × client_public
                    = server_private × (client_private × G)

     Both equal: client_private × server_private × G
     But attacker seeing client_public and server_public
     CANNOT compute the shared secret (ECDH problem is hard)

  5. Key derivation (HKDF):
     From shared_secret + client_random + server_random:
       client_write_key = HKDF(shared, "client write key", 32)
       server_write_key = HKDF(shared, "server write key", 32)
       client_write_iv  = HKDF(shared, "client write IV", 12)
       server_write_iv  = HKDF(shared, "server write IV", 12)

WHY "EPHEMERAL" (the E in ECDHE):
  Key pair generated fresh for EVERY connection
  Even if server's long-term RSA key is compromised later:
    Past sessions can't be decrypted (keys were ephemeral, deleted)
  This is FORWARD SECRECY — TLS 1.3 requires it

PERFORMANCE:
  x25519 key generation: ~50 microseconds
  x25519 shared secret:  ~150 microseconds
  RSA-2048 sign:         ~500 microseconds
  ECDSA-P256 sign:       ~100 microseconds
  Total TLS 1.3 handshake crypto: ~500 µs
```

---

## Symmetric Encryption — Bulk Data Protection

```
AFTER HANDSHAKE: ALL DATA ENCRYPTED WITH SYMMETRIC CIPHER

AES-256-GCM (most common):
  ┌──────────────────────────────────────────────────────────┐
  │ AES-256-GCM: Authenticated Encryption with Associated Data
  │                                                          │
  │ Inputs:                                                  │
  │   Key: 256-bit symmetric key (from HKDF)                 │
  │   IV/Nonce: 96-bit (12 bytes), unique per record         │
  │   Plaintext: the HTTP request/response data              │
  │   AAD: additional authenticated data (TLS record header) │
  │                                                          │
  │ Output:                                                  │
  │   Ciphertext: same length as plaintext                   │
  │   Tag: 128-bit (16 bytes) authentication tag             │
  │                                                          │
  │ TLS RECORD:                                              │
  │   ┌──────────┬───────────────────┬──────────┐           │
  │   │ Header   │ Encrypted payload │ Auth tag │           │
  │   │ (5 bytes)│ (N bytes)         │ (16 bytes)│          │
  │   │ type=23  │ AES-GCM(plaintext)│ GCM tag  │          │
  │   │ version  │                   │          │           │
  │   │ length   │                   │          │           │
  │   └──────────┴───────────────────┴──────────┘           │
  │                                                          │
  │ SECURITY PROVIDED:                                       │
  │   Confidentiality: attacker can't read plaintext         │
  │   Integrity: attacker can't modify without detection     │
  │   Authentication: tag verifies data hasn't been tampered │
  │                                                          │
  │ HARDWARE ACCELERATION:                                   │
  │   Intel AES-NI instruction set                           │
  │   AES-256-GCM with AES-NI: ~5 GB/s per core             │
  │   Without AES-NI: ~500 MB/s per core                     │
  │   Modern CPUs: TLS encryption overhead < 5%              │
  └──────────────────────────────────────────────────────────┘

ChaCha20-Poly1305 (alternative, for non-Intel):
  Used on: ARM devices (phones), older hardware without AES-NI
  Speed without hardware accel: ~1 GB/s (faster than software AES)
  Google: uses ChaCha20 for Android clients, AES for datacenter
```

---

## TLS Record Protocol — Encrypted Data on Wire

```
TLS RECORD LAYER — HOW ENCRYPTED DATA IS FRAMED:

Every piece of encrypted data is wrapped in a TLS record:

  ┌──────────────────────────────────────────────────────┐
  │ TLS Record:                                          │
  │                                                      │
  │ Byte 0:    Content type                              │
  │              20 = ChangeCipherSpec                    │
  │              21 = Alert                               │
  │              22 = Handshake                          │
  │              23 = Application Data                    │
  │ Bytes 1-2: Protocol version (0x0303 = TLS 1.2)      │
  │ Bytes 3-4: Length (max 16384 + padding)              │
  │ Bytes 5..: Encrypted fragment + auth tag             │
  └──────────────────────────────────────────────────────┘

EXAMPLE: Sending "GET /api/v1/users/123 HTTP/1.1\r\n..."

  Plaintext (HTTP request): 300 bytes
  
  TLS Record on wire:
    Content type: 0x17 (23 = Application Data)
    Version: 0x03 0x03
    Length: 0x01 0x40 (320 = 300 ciphertext + 16 tag + padding)
    Encrypted data: [AES-GCM encrypted 300 bytes]
    Auth tag: [16 bytes GCM tag]

  Total on wire: 5 (header) + 300 (encrypted) + 16 (tag) = 321 bytes
  Overhead per record: 21 bytes (~7% for 300-byte payload)
  For large payloads (16 KB): 21/16384 = 0.1% overhead

RECORD SIZE AND LATENCY:
  Max TLS record: 16 KB
  Large HTTP response (1 MB): split into ~64 TLS records
  Each record: independently decryptable
  Receiver can start processing before all records arrive
```

---

## mTLS — Mutual TLS for Service-to-Service

```
MUTUAL TLS (mTLS) — BOTH SIDES AUTHENTICATE:

Normal TLS: client verifies server (one-way)
mTLS: client AND server verify each other (two-way)

USE CASE: microservice-to-microservice API calls
  Service A calls Service B
  How does B know A is legitimate? → mTLS

MTLS HANDSHAKE (additional steps):
  ┌──────────────────────────────────────────────────────────┐
  │ Normal TLS handshake PLUS:                               │
  │                                                          │
  │ Server → CertificateRequest                              │
  │   "I also need YOUR certificate"                         │
  │                                                          │
  │ Client → Certificate                                     │
  │   Client's X.509 cert (issued by internal CA)            │
  │   Subject: CN=order-service                              │
  │   SAN: order-service.default.svc.cluster.local           │
  │                                                          │
  │ Client → CertificateVerify                               │
  │   Signature proving client owns the private key          │
  │                                                          │
  │ Server verifies:                                         │
  │   Client cert signed by trusted internal CA?             │
  │   Client cert not expired or revoked?                    │
  │   Client cert CN/SAN matches expected service identity?  │
  └──────────────────────────────────────────────────────────┘

SERVICE MESH (Istio, Linkerd):
  Automatically provisions mTLS certificates for every pod
  Sidecar proxy (Envoy) handles TLS: application sees plain HTTP
  Certificate rotation: automatic (short-lived certs, ~24h)
  No application code changes needed!

  Pod A (order-service):
    [App] → [Envoy sidecar] ──mTLS──► [Envoy sidecar] → [App]
    HTTP          encrypted tunnel          HTTP
                  (transparent to app)

  Envoy handles: cert provisioning, rotation, verification, encryption
```

---

## Session Resumption — Avoiding Repeated Handshakes

```
SESSION RESUMPTION — SKIPPING THE EXPENSIVE PARTS:

Full handshake: 1-2 RTT + crypto computation (~500 µs)
Resumed handshake: 1 RTT + minimal crypto (~50 µs)

TLS 1.2 SESSION TICKETS:
  ┌──────────────────────────────────────────────────────────┐
  │ First connection:                                        │
  │   Full handshake completes                               │
  │   Server sends NewSessionTicket:                         │
  │     Encrypted blob containing: master secret, cipher,    │
  │     negotiated parameters                                │
  │   Client stores ticket locally                           │
  │                                                          │
  │ Reconnection:                                            │
  │   Client sends ClientHello + SessionTicket               │
  │   Server decrypts ticket → recovers master secret        │
  │   No certificate exchange or key exchange needed!        │
  │   Handshake completes in 1 RTT                           │
  └──────────────────────────────────────────────────────────┘

TLS 1.3 PSK (Pre-Shared Key) + 0-RTT:
  ┌──────────────────────────────────────────────────────────┐
  │ First connection:                                        │
  │   Full TLS 1.3 handshake (1 RTT)                         │
  │   Server sends NewSessionTicket with PSK                 │
  │                                                          │
  │ Reconnection:                                            │
  │   Client sends ClientHello + pre_shared_key + early_data │
  │   + encrypted HTTP request (using PSK-derived keys)      │
  │   ALL IN ONE PACKET!                                     │
  │                                                          │
  │   Server: decrypt early data, process request            │
  │   Complete handshake simultaneously                      │
  │   0-RTT: data flows before handshake finishes           │
  └──────────────────────────────────────────────────────────┘

CONNECTION POOLING + SESSION RESUMPTION:
  API Client (e.g., HTTP client library):
    Pool of keep-alive connections to api.example.com
    Each connection: TLS session already established
    New request: pick connection from pool → send immediately
    No TCP handshake, no TLS handshake!
    Latency: just 1 RTT for request/response
```

---

## 30-SECOND REVISION BOX

```
TLS 1.2: 2-RTT handshake, ClientHello→ServerHello+Cert→KeyExchange→Finished
TLS 1.3: 1-RTT, key share in ClientHello (speculative), 0-RTT resumption
CERTIFICATE: leaf → intermediate → root CA (pre-installed trust anchor)
ECDHE: ephemeral key pairs, shared secret via curve math, forward secrecy
AES-256-GCM: symmetric encryption ~5 GB/s with AES-NI, 16-byte auth tag
TLS RECORD: 5-byte header + encrypted payload + 16-byte tag
mTLS: both sides present certificates (microservices, service mesh)
SESSION RESUMPTION: ticket/PSK avoids full handshake on reconnect
0-RTT: send data in first packet (PSK), replay risk for non-idempotent
OVERHEAD: first connection ~400ms (TCP+TLS+HTTP), reused ~100ms
```

---

**Prev: [[09_Internals-HTTP-Protocol-Deep-Dive]] | Next: [[11_Internals-REST-HTTP-Caching-Mechanics]]**
