# Winery Sales Agent POS — Flutter App Build Specification

> **Audience:** an AI coding agent (or developer) building the mobile app.
> **Backend:** already implemented in the `winery` Frappe app (Frappe/ERPNext v16).
> This document is self-contained: architecture, the exact live API, app pages,
> process flows, and acceptance criteria. Where this document and any earlier design
> note disagree, **this document wins** — the API section below describes endpoints
> that actually exist and were tested end-to-end.

| | |
|---|---|
| **App** | Winery Sales Agent POS (Android-first Flutter app) |
| **Backend base** | `https://winery.finesoftafrika.com` |
| **API namespace** | `winery.winery.pos.api.*` |
| **Auth** | Per-agent Frappe API key/secret + in-app PIN |
| **Currency** | KES (from the agent profile) |
| **Version** | 1.0 — 2026-07-05 |

---

## Table of Contents
1. [Product Overview](#1-product-overview)
2. [System Architecture](#2-system-architecture)
3. [Backend Data Model (what exists)](#3-backend-data-model-what-exists)
4. [API Reference (live endpoints)](#4-api-reference-live-endpoints)
5. [Error Handling](#5-error-handling)
6. [Flutter App Architecture](#6-flutter-app-architecture)
7. [Local Database & Sync Engine](#7-local-database--sync-engine)
8. [App Pages](#8-app-pages)
9. [Process Flows](#9-process-flows)
10. [Build Plan & Milestones](#10-build-plan--milestones)
11. [Acceptance Criteria](#11-acceptance-criteria)

---

## 1. Product Overview

Field **sales agents** carry finished winery products (batch-tracked bottled wine) in a
dedicated per-agent warehouse and sell to customers in the field. Every sale is recorded
in ERPNext as a submitted **POS Sales Invoice** with a payment split across **Cash**,
**M-Pesa** (Daraja STK Push or a manually typed code), and **Bank** (deposit/transfer
reference). Stock is **consignment**: the company owns it in the agent's warehouse until
sold; revenue books at the moment of the field sale.

The app is **offline-first**: sales are saved locally and synced when connectivity
returns. The server is the single source of truth — pricing, discount caps, stock
validation, and batch selection are all enforced server-side. The client never chooses a
warehouse, price, or agent.

**In scope (v1):** login + PIN, product catalogue with per-agent stock, cart, checkout
with split payments, M-Pesa STK Push with live confirmation, manual M-Pesa/bank fallbacks,
offline sales queue with idempotent sync, receipt print/share, sales history, my-stock,
day-close.

**Out of scope (v1):** returns/credit notes, credit sales, multi-currency, agent-to-agent
transfers.

---

## 2. System Architecture

```
┌──────────────────────────────┐                          ┌───────────────────────────────┐
│ Flutter App (Android-first)  │   HTTPS REST             │ Frappe/ERPNext v16            │
│                              │   Authorization: token   │  winery app › pos package     │
│  Presentation (screens)      │ ───────────────────────▶ │   winery.winery.pos.api.*     │
│  State (Riverpod)            │   JSON  {"message": …}   │   ├ sale.py  (posting engine) │
│  Domain (use-cases)          │ ◀─────────────────────── │   ├ mpesa.py (Daraja STK)     │
│  Data (dio + Drift SQLite)   │                          │   └ setup.py (bootstrap)      │
│  Sync queue + printer        │                          │  Standard ERPNext docs:       │
└──────────────────────────────┘                          │   Sales Invoice (is_pos)      │
        ┌──────────────┐   STK push / callback            │   Stock Ledger / Batch        │
        │ Safaricom    │ ◀───────────────────────────────▶│   Mode of Payment / GL        │
        │ Daraja API   │                                  └───────────────────────────────┘
        └──────────────┘
```

**Principles**
- **Single source of truth** — every sale is a standard ERPNext Sales Invoice; no parallel
  ledger. The app mirrors state locally for offline use only.
- **Server-side trust boundary** — the agent, warehouse, price list, discount cap, and
  batch are resolved from the authenticated user server-side. Do not send them.
- **Idempotent sync** — every sale carries a client-generated `pos_client_uuid`; the server
  upserts on it, so retries never double-post.

---

## 3. Backend Data Model (what exists)

You do not build these — they exist. Listed so you understand the fields the API returns.

- **Sales Agent** — one per app user. Fields the app sees via `login`: `name`,
  `sales_agent_name`, `agent_warehouse`, `selling_price_list`, `default_customer`,
  `max_discount_pct`, `pos_profile`, `currency`, `company`. Status can be
  Active/Suspended/Inactive (only Active can transact).
- **Sales Invoice** (standard) with custom fields `pos_sales_agent`, `pos_client_uuid`
  (unique). Payment rows carry `winery_mpesa_receipt_no`, `winery_bank_reference`,
  `winery_verification_status` (Auto-verified / Pending / Verified / Rejected).
- **Winery Mpesa Payment Request** — one row per STK Push (`checkout_request_id`,
  `status` ∈ Pending/Success/Failed/Timeout, `mpesa_receipt_number`).
- **Winery POS Day Close** — submittable end-of-day reconciliation record.
- **Modes of Payment**: exactly `"Cash"`, `"M-Pesa"`, `"Bank"` (use these strings).

---

## 4. API Reference (live endpoints)

### 4.1 Conventions

- **URL:** `POST|GET https://winery.finesoftafrika.com/api/method/winery.winery.pos.api.<function>`
- **Auth header (all except `login` and `mpesa_callback`):**
  `Authorization: token <api_key>:<api_secret>`
- **Body:** `Content-Type: application/json`. Send parameters as top-level JSON keys.
  Nested arrays/objects (e.g. `items`, `payments`) are sent as real JSON — no
  double-encoding needed.
- **Success envelope:** Frappe wraps the return value: `{"message": <payload>}`. All
  example responses below show the **contents of `message`**.
- **Errors:** non-2xx. The response body contains `exc_type`, a human message in
  `_server_messages`, and — for POS business errors — a top-level **`error_code`** and
  sometimes **`error_detail`**. Always branch on `error_code` when present (see §5).

> **Dart tip:** create one `dio` instance with `baseUrl =
> "https://winery.finesoftafrika.com/api/method/winery.winery.pos.api."`, an auth
> interceptor that injects the token header, and a response interceptor that unwraps
> `data["message"]`.

---

### 4.2 `login` — exchange credentials for API keys  *(guest)*

`POST winery.winery.pos.api.login`

Request:
```json
{ "usr": "john@finesoft.co.ke", "pwd": "••••••••" }
```
Response (`message`):
```json
{
  "api_key": "a1b2c3d4e5f6g7h",
  "api_secret": "s3cr3t9x8y7z",
  "agent": {
    "name": "John Mwangi",
    "sales_agent_name": "John Mwangi",
    "agent_warehouse": "Agent - John Mwangi - W",
    "selling_price_list": "Standard Selling",
    "default_customer": "Walk-in - John Mwangi",
    "max_discount_pct": 10.0,
    "pos_profile": "Winery Field Sales",
    "currency": "KES",
    "company": "Winery"
  },
  "server_time": "2026-07-05 09:15:22.123456"
}
```
- Store `api_key`/`api_secret` in `flutter_secure_storage`. Use them for every later call.
- Errors: `401` (bad credentials), or `error_code: "AGENT_INACTIVE"` if the user has no
  active Sales Agent. On either, show the login error and do not proceed.
- After a successful login, force PIN setup; on subsequent launches unlock with the PIN and
  reuse the stored keys (no re-login).

---

### 4.3 `bootstrap` — full/delta offline dataset

`GET winery.winery.pos.api.bootstrap?modified_after=<ISO datetime|optional>`

Response (`message`):
```json
{
  "sync_timestamp": "2026-07-05 09:15:22.987654",
  "items": [
    {
      "item_code": "WINE-CAB-750",
      "item_name": "Cabernet 750ml",
      "item_group": "Red Wine",
      "uom": "Bottle",
      "image": "/files/cab750.jpg",
      "has_batch_no": 1,
      "rate": 1200.0,
      "stock_qty": 48.0
    }
  ],
  "customers": [
    { "name": "CUST-0102", "customer_name": "Naivas Karen", "mobile_no": "0722000111" }
  ],
  "modes_of_payment": ["Cash", "M-Pesa", "Bank"],
  "settings": { "max_discount_pct": 10.0, "currency": "KES" }
}
```
- `rate` is the price from the agent's price list (0 if unpriced). `stock_qty` is the qty
  in the agent's own warehouse at sync time — **advisory** when offline; the server
  re-checks at posting.
- `image` is a server-relative path; prefix with the base host to load. Cache decoded
  images locally.
- **Delta sync:** pass `modified_after` = the previous `sync_timestamp` to receive only
  changed items/customers. Merge into the local DB; treat missing rows as unchanged.

---

### 4.4 `stock` — lightweight stock refresh

`GET winery.winery.pos.api.stock`

Response (`message`): a map of `item_code → qty` in the agent warehouse.
```json
{ "WINE-CAB-750": 48.0, "WINE-ROSE-750": 12.0 }
```
Poll this on the **My Stock** screen and after a successful sync.

---

### 4.5 `create_sale` — post one sale

`POST winery.winery.pos.api.create_sale`

Send the cart as top-level JSON. Used both online (at checkout) and by the sync queue.

Request:
```json
{
  "pos_client_uuid": "9f8b2c1e-4a5d-4e6f-8a9b-0c1d2e3f4a5b",
  "posting_datetime": "2026-07-05 10:42:10",
  "customer": null,
  "quick_customer": { "customer_name": "Mama Njeri Shop", "mobile_no": "0711223344" },
  "items": [
    { "item_code": "WINE-CAB-750", "qty": 3, "discount_pct": 0 },
    { "item_code": "WINE-ROSE-750", "qty": 1, "discount_pct": 5 }
  ],
  "payments": [
    { "mode_of_payment": "Cash", "amount": 2000 },
    { "mode_of_payment": "M-Pesa", "amount": 1740,
      "checkout_request_id": "ws_CO_05072026104210123" }
  ]
}
```

Field rules:
- `pos_client_uuid` **required** — generate a UUID v4 per sale and reuse it on every retry.
- `posting_datetime` optional — set it to the moment the agent completed the sale
  (important for offline sales made earlier). Format `YYYY-MM-DD HH:MM:SS`.
- Customer: send `customer` (a Customer name) **or** `quick_customer` (name + phone) **or**
  neither (falls back to the agent's default walk-in customer). Do not send both.
- `items[].discount_pct` optional (0 if omitted); must be ≤ the agent's `max_discount_pct`.
- `payments[]`: only rows with `amount > 0` count. Per mode:
  - **Cash** — just `amount`.
  - **M-Pesa (STK)** — `amount` + `checkout_request_id` from a **confirmed** STK request
    (status `Success`); the server verifies the amount matches and stamps the receipt.
  - **M-Pesa (manual code)** — `amount` + `mpesa_receipt_no` (the code from the customer's
    SMS). Stored as `Pending` verification.
  - **Bank** — `amount` + `bank_reference` (required).
  - The payment amounts **must sum to the server-computed grand total**.

Response (`message`) — HTTP `201` for a new sale, `200` if it was a duplicate:
```json
{
  "sales_invoice": "ACC-SINV-2026-01427",
  "grand_total": 4740.0,
  "duplicate": false,
  "customer": "Mama Njeri Shop",
  "posting_date": "2026-07-05",
  "payments": [
    { "mode_of_payment": "Cash", "amount": 2000.0, "mpesa_receipt_no": null,
      "bank_reference": null, "verification_status": null },
    { "mode_of_payment": "M-Pesa", "amount": 1740.0, "mpesa_receipt_no": "SGR3XKPLM9",
      "bank_reference": null, "verification_status": "Auto-verified" }
  ],
  "items": [
    { "item_code": "WINE-CAB-750", "item_name": "Cabernet 750ml", "qty": 3.0,
      "rate": 1200.0, "amount": 3600.0 }
  ]
}
```
- `duplicate: true` means this `pos_client_uuid` was already posted — adopt the returned
  invoice as the authoritative result (do **not** create another).
- Business errors: `DISCOUNT_EXCEEDED`, `STOCK_SHORT` (with `error_detail.shortages`),
  `PAYMENT_MISMATCH`, `MPESA_NOT_CONFIRMED`, `DUPLICATE_MPESA_CODE`, `AGENT_INACTIVE` (§5).

---

### 4.6 `sync_batch` — upload queued offline sales

`POST winery.winery.pos.api.sync_batch`

Request (max 25 sales per call, processed FIFO):
```json
{ "sales": [ { /* create_sale payload */ }, { /* … */ } ] }
```
Response (`message`) — a per-sale list, aligned to input order. Each entry is **either** a
`create_sale` success object **or** an error object:
```json
[
  { "sales_invoice": "ACC-SINV-2026-01428", "grand_total": 1200.0, "duplicate": false, "…": "…" },
  { "pos_client_uuid": "…", "error_code": "STOCK_SHORT",
    "detail": { "shortages": [ { "item_code": "WINE-CAB-750", "requested": 5, "available": 2 } ] },
    "message": "Insufficient stock in the agent warehouse for one or more items." }
]
```
- Partial success is normal. Mark successes `synced`; route error entries to the
  **Conflicts inbox** (do not auto-retry business errors). Each sale is committed in its own
  savepoint server-side, so one failure does not roll back the others.

---

### 4.7 `history` — the agent's past invoices

`GET winery.winery.pos.api.history?from_date=2026-07-01&to_date=2026-07-05&limit=50&start=0`

Response (`message`): list of invoices (agent-scoped), each with a `payments` array
(`mode_of_payment`, `amount`, `winery_mpesa_receipt_no`, `winery_bank_reference`,
`winery_verification_status`). Use for backfilling history after re-install; the local DB
is the primary source.

---

### 4.8 `stk_push` — initiate M-Pesa STK Push

`POST winery.winery.pos.api.stk_push`

Request:
```json
{ "phone": "0722000111", "amount": 1740, "pos_client_uuid": "9f8b2c1e-…" }
```
Response (`message`):
```json
{ "checkout_request_id": "ws_CO_05072026104210123", "status": "Pending" }
```
- The server normalises the phone to `2547XXXXXXXX`. Errors: `INVALID_PHONE`,
  `DARAJA_UNREACHABLE`. Requires connectivity — disable STK when offline.

---

### 4.9 `payment_status` — poll an STK request

`GET winery.winery.pos.api.payment_status?checkout_request_id=ws_CO_05072026104210123`

Response (`message`):
```json
{ "status": "Success", "mpesa_receipt_number": "SGR3XKPLM9",
  "result_desc": "The service request is processed successfully." }
```
- `status` ∈ `Pending | Success | Failed | Timeout`. Poll every **3 s**, client timeout
  **90 s**. On `Success`, proceed to `create_sale` with the `checkout_request_id`. On
  `Failed`/`Timeout`, offer retry / manual code / switch to cash.

---

### 4.10 `mpesa_callback` — Safaricom webhook *(guest; not called by the app)*

`POST winery.winery.pos.api.mpesa_callback` — Safaricom posts the STK result here. Listed
for completeness only; the app never calls it.

---

### 4.11 `day_summary` — today's figures

`GET winery.winery.pos.api.day_summary?date=2026-07-05`  *(date optional; defaults today)*

Response (`message`):
```json
{
  "date": "2026-07-05",
  "invoice_count": 14,
  "grand_total": 61250.0,
  "by_mode": { "Cash": 21000.0, "M-Pesa": 36250.0, "Bank": 4000.0 },
  "pending_verification": 2,
  "stock": [ { "item_code": "WINE-CAB-750", "sold": 12.0, "balance": 48.0 } ]
}
```

---

### 4.12 `day_close` — submit end-of-day reconciliation

`POST winery.winery.pos.api.day_close`

Request:
```json
{ "date": "2026-07-05", "declared_cash": 20800, "notes": "" }
```
Response (`message`):
```json
{ "day_close": "DAYCLOSE-John Mwangi-2026-07-05", "system_cash": 21000.0,
  "declared_cash": 20800.0, "cash_variance": -200.0, "grand_total": 61250.0 }
```
- `cash_variance = declared_cash − system_cash`. Error `ALREADY_CLOSED` if a close already
  exists for that agent/date.

---

## 5. Error Handling

On a non-2xx response, read `error_code` from the body when present and map it:

| `error_code` | Meaning | App behaviour |
|---|---|---|
| `AGENT_INACTIVE` | User has no active Sales Agent | Force logout with a message |
| `STOCK_SHORT` | Requested qty > agent stock (see `error_detail.shortages` / batch `detail`) | Online: block checkout, show available. Sync: Conflicts inbox |
| `PAYMENT_MISMATCH` | Payments ≠ grand total (or bad payload) | Re-fetch/re-price, ask agent to adjust |
| `DISCOUNT_EXCEEDED` | Line discount above cap (`error_detail.max_discount_pct`) | Clamp to cap, re-confirm |
| `MPESA_NOT_CONFIRMED` | STK not `Success` / no code supplied | Keep polling or offer fallback |
| `INVALID_PHONE` | Not a valid Safaricom number | Inline field error |
| `DUPLICATE_MPESA_CODE` | Manual code already used | Reject, prompt re-check |
| `DARAJA_UNREACHABLE` | Daraja down/timeout | Offer manual code or cash |
| `ALREADY_CLOSED` | Day close exists for the date | Show existing summary |
| `SERVER_ERROR` | Unexpected (in `sync_batch` entries) | Conflicts inbox; keep local copy |

Transport rules:
- **Network / 5xx** on a sale → keep the sale `pending` in the queue; exponential backoff.
- **4xx business error** on a sale → mark `failed`; Conflicts inbox; **no** auto-retry.
- **401** on any call → attempt one silent retry, else force re-login (preserve the queue).
- **`duplicate: true`** → treat as success; adopt the server invoice number.

---

## 6. Flutter App Architecture

**Stack**

| Concern | Package |
|---|---|
| Framework | Flutter 3.x / Dart 3, Android `minSdk 24` (iOS later) |
| State | `flutter_riverpod` (+ `riverpod_generator`) |
| Navigation | `go_router` |
| HTTP | `dio` (auth + retry + unwrap interceptors) |
| Local DB | `drift` (SQLite) |
| Secure storage | `flutter_secure_storage` (API keys, PIN hash) |
| Connectivity | `connectivity_plus` |
| Receipt printing | `esc_pos_utils` + `print_bluetooth_thermal` (58/80 mm) |
| Receipt share | `pdf` + `share_plus` |
| IDs / hashing | `uuid`, `crypto` |
| Crash/analytics | `sentry_flutter` (optional) |

**Layered structure**
```
lib/
├── app/            # MaterialApp, router, theme, PIN gate
├── core/           # env (base url), formatters (KES, phone), failures, result types
├── data/
│   ├── api/        # dio client + one wrapper per endpoint in §4
│   ├── db/         # drift tables + DAOs
│   └── repositories/  # CatalogueRepo, SalesRepo, PaymentsRepo, ReportsRepo, AuthRepo
├── domain/         # entities + use-cases (CreateSale, InitiateStkPush, SyncPendingSales,
│                   #   CloseDay, Bootstrap)
├── features/       # auth, home, catalogue, cart, checkout, receipt, history, stock,
│                   #   day_close, conflicts, settings  (each: screen + controller/provider)
└── services/       # SyncEngine, PrinterService, PdfReceiptBuilder, ConnectivityService
```

**Auth & security**
- Store `api_key:api_secret` only in secure storage; never in SQLite.
- PIN (4–6 digits) hashed locally (PBKDF2 via `crypto`); gate app open and 5-min background.
- "Forgot PIN" ⇒ full re-login. Logout is blocked while unsynced sales exist.

---

## 7. Local Database & Sync Engine

**Drift tables**

| Table | Purpose |
|---|---|
| `items` | catalogue cache (item_code, name, group, uom, image path, has_batch, rate) |
| `stock_snapshot` | item_code → qty + `as_of` timestamp (show staleness) |
| `customers` | cached customers for the picker |
| `settings` | max_discount_pct, currency, last `sync_timestamp` |
| `sales` | one row per sale keyed by `pos_client_uuid`; `sync_status ∈ pending|synced|failed`; server invoice no. once synced |
| `sale_items`, `sale_payments` | children of `sales` |
| `sync_queue` | FIFO of pending `pos_client_uuid`s + attempt count + next-retry time |

**Sync engine rules**
- Triggers: connectivity regained, app foregrounded, after checkout, manual pull-to-refresh.
- FIFO; batch via `sync_batch` (≤25); exponential backoff (30 s → 16 min cap) per batch.
- Business error (`STOCK_SHORT`, `DISCOUNT_EXCEEDED`, …) → `failed` + Conflicts inbox; no
  auto-retry. Network/5xx → stays `pending`, retried.
- Idempotent: always send the original `pos_client_uuid`; on `duplicate:true` adopt the
  server invoice.
- **Offline checkout allows Cash + manual M-Pesa code + bank reference only.** STK Push
  requires connectivity and is disabled offline (show an explanatory label).

---

## 8. App Pages

Navigation:
```
Splash → Login (first run) → PIN setup
       → PIN unlock → Home
                       ├ Catalogue → Cart → Checkout → Receipt
                       ├ Sales History → Sale detail (reprint/share)
                       ├ My Stock
                       ├ Day Close
                       ├ Conflicts inbox (badge when non-empty)
                       └ Settings (printer pairing, re-sync, logout)
```

| # | Page | Contents & behaviour |
|---|---|---|
| 1 | **Login** | email + password → `login`; store keys; then force PIN setup. |
| 2 | **PIN unlock** | Gate on open / 5-min background; forgot ⇒ re-login. |
| 3 | **Home** | Today's total + Cash/M-Pesa/Bank split (local, reconciled with `day_summary` when online); sync badge (`n pending`); low-stock alerts; shortcuts. |
| 4 | **Catalogue** | Grid/list of items with image, price, *my stock* chip + staleness ("stock as of 09:15"); search + item-group filter; tap = add, long-press = qty. |
| 5 | **Cart** | Qty steppers; per-line discount % (input capped at `max_discount_pct`); subtotal/total; customer selector (default walk-in / pick / quick-create name+phone). |
| 6 | **Checkout** | Core screen. Addable payment rows: **Cash** (amount + change helper), **M-Pesa** (phone → *Send STK* → live status polling `payment_status` → receipt code fills in; or *Enter code manually*), **Bank** (reference). "Complete Sale" enables only when Σ payments = total. Offline: STK disabled + "Will sync when online" banner. |
| 7 | **Receipt** | Itemised receipt + payment breakdown incl. M-Pesa receipt no.; Print (ESC/POS), Share PDF (WhatsApp), New Sale. Unsynced sales print a "PROVISIONAL — pending sync" strip. |
| 8 | **Sales History** | Local-first list; filter date/mode/sync status; unsynced = amber, failed = red → Conflicts. Detail: reprint, share, server invoice no. |
| 9 | **My Stock** | Item, sold-today, balance; pull-to-refresh → `stock`. |
| 10 | **Day Close** | Shows `day_summary`; agent enters declared cash; variance shown before confirm → `day_close`; then locks that date. |
| 11 | **Conflicts inbox** | Failed syncs with server reason (e.g. "Stock short: WINE-CAB-750 — available 2, requested 3"); actions: edit & retry (reopens as a new cart) or void locally (with reason). |
| 12 | **Settings** | Printer pairing/test print, force full re-bootstrap, app/server info, logout (blocked while unsynced sales exist). |

---

## 9. Process Flows

### 9.1 Login & bootstrap
```
login(usr,pwd) → store keys, set PIN
bootstrap()    → write items/prices/stock/customers/settings to SQLite; save sync_timestamp
```

### 9.2 Cash sale (online)
```
build cart → save local (uuid, status=pending)
create_sale(payload)   # payments:[Cash]
  → 201 { sales_invoice, … }  → mark synced → show receipt (print/share)
```

### 9.3 M-Pesa STK sale
```
checkout → stk_push(phone, amount, uuid) → { checkout_request_id, status:Pending }
loop every 3s (≤90s): payment_status(checkout_request_id)
   Pending … → Success { mpesa_receipt_number }
create_sale(payload with M-Pesa row { amount, checkout_request_id })
   → server verifies request=Success & amount matches → 201, payment Auto-verified
Failure paths: Failed/Timeout → retry STK | enter code manually | switch to cash.
```

### 9.4 Offline sale & sync
```
offline checkout (Cash / manual M-Pesa code / bank ref only)
   → enqueue sale (uuid, pending), print PROVISIONAL receipt
connectivity returns → SyncEngine:
   sync_batch([sale1, sale2, …]) → per-sale results
      success → mark synced (adopt invoice no.)
      error   → Conflicts inbox
   stock()  → refresh snapshot
```

### 9.5 Day close
```
day_summary(date) → show totals + by_mode
agent declares cash → day_close(date, declared_cash) → variance; lock date
(second attempt → ALREADY_CLOSED → show existing summary)
```

---

## 10. Build Plan & Milestones

1. **M0 — Skeleton**: project, theme, router, env, dio client + interceptors (auth header,
   `message` unwrap, error→`error_code` mapping), secure storage, PIN gate.
2. **M1 — Auth + bootstrap**: Login → `login`, store keys; `bootstrap` into Drift; Home
   shell with sync badge.
3. **M2 — Catalogue + cart + cash checkout**: Catalogue from local DB with stock chips;
   Cart with discount cap; Checkout (Cash only) → `create_sale`; Receipt (print + PDF).
4. **M3 — Offline queue**: local-first save, `sync_queue`, `sync_batch`, backoff, Conflicts
   inbox, `stock` refresh, Sales History.
5. **M4 — M-Pesa STK**: `stk_push` + `payment_status` polling UX; manual-code fallback;
   bank reference; multi-row split payments summing to total.
6. **M5 — Reports + polish**: My Stock, Day Close (`day_summary`/`day_close`), low-stock
   alerts, Settings (printer pairing, re-bootstrap), Sentry, Play Store internal track.

---

## 11. Acceptance Criteria

- **Auth**: valid login stores keys and lands on PIN setup; inactive agent → clear error;
  relaunch unlocks via PIN without re-login.
- **Catalogue**: items, prices, and per-agent stock render from the local DB and refresh via
  `bootstrap`/`stock`; staleness timestamp shown.
- **Cash sale**: completes online, shows a receipt with the server invoice number, and
  decrements the on-screen stock; the same sale is not double-posted on retry
  (`duplicate:true` handled).
- **Discount cap**: a line discount above `max_discount_pct` is blocked with a clear message
  (server `DISCOUNT_EXCEEDED` also handled defensively).
- **M-Pesa STK**: sending an STK shows a live status that resolves to Success with the
  receipt number on the completed sale; Failed/Timeout offers fallbacks.
- **Split payments**: Cash + M-Pesa + Bank rows must sum to the total before "Complete Sale"
  enables; bank rows require a reference.
- **Offline**: a sale made offline is queued, prints a PROVISIONAL receipt, and syncs
  automatically on reconnect; a `STOCK_SHORT` on sync lands in the Conflicts inbox rather
  than being lost.
- **Day close**: shows the summary, computes variance, submits once, and blocks a second
  close for the same date.

---

## Appendix — Quick reference

**Base:** `https://winery.finesoftafrika.com/api/method/winery.winery.pos.api.`
**Header:** `Authorization: token <api_key>:<api_secret>` · `Content-Type: application/json`
**Unwrap:** read `response.data["message"]`.
**Modes of payment (exact strings):** `Cash`, `M-Pesa`, `Bank`.

| Function | Method | Key params |
|---|---|---|
| `login` | POST | `usr`, `pwd` |
| `bootstrap` | GET | `modified_after?` |
| `stock` | GET | — |
| `create_sale` | POST | `pos_client_uuid`, `items[]`, `payments[]`, `customer?`/`quick_customer?`, `posting_datetime?` |
| `sync_batch` | POST | `sales[]` (≤25) |
| `history` | GET | `from_date?`, `to_date?`, `limit?`, `start?` |
| `stk_push` | POST | `phone`, `amount`, `pos_client_uuid` |
| `payment_status` | GET | `checkout_request_id` |
| `day_summary` | GET | `date?` |
| `day_close` | POST | `date?`, `declared_cash`, `notes?` |
