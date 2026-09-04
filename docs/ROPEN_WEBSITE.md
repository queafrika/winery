# Ropen Coffee and Fine Foods — public website & shop

The marketing site and M-Pesa storefront for `winery.finesoftafrika.com`, built into
the existing `winery` app. The ERP desk is untouched and still lives at `/app`.

---

## 0. Where the content comes from

All site copy is drawn from the company's own presentation (`ropen.pptx`), not
invented. Key facts the pages depend on:

- The company is **family-owned**, specialising in farming and processing of fine
  alcoholic and non-alcoholic beverages, across **four divisions**: Coffee Farming
  & Processing, Ropen Winery, Bansoko Centre, and TerraNova Coffee (USA) LLC.
- The wine brand is **Banny's Dry Banana Wine** — 8.5% ABV, 750ml, made in Ruiru,
  Kiambu. Ingredients, allergen statement and health warning are taken from the
  bottle label artwork.
- The coffee farm is **Njagũ Farm**, Njagũ village, Lari / Githunguri, Kiambu:
  1,550–1,725m, 1,380mm rainfall, 15–23 °C, humic nitisols; SL28/SL34 with
  Ruiru 11 infill; acquired 2023 and under rehabilitation.
- The woman on the label represents the **traditional Kikuyu woman**, honouring
  the women who led the banana plant's food, brew, thatching and weaving uses —
  and the women and children conscripted into establishing these coffee farms
  between 1912 and 1954. Part of coffee proceeds funds aged women's welfare.

If any of this changes, it lives in `www/*.py` (FAQs, meta) and `www/*.html`
(body copy), plus product copy in `ecommerce/setup.py`.

---

## 1. Routes

| Route | Page | Indexed |
|---|---|---|
| `/` | Home — hero with Winery / Coffee / Shop cards | yes |
| `/winery` | The winery: process, tasting notes, FAQ, CTA → `/shop?group=wine` | yes |
| `/coffee` | The coffee: origin, process, FAQ, CTA → `/shop?group=coffee` | yes |
| `/about` | Company story, values, locations | yes |
| `/contact` | Contact form (creates a Lead) + contact details | yes |
| `/shop` | Product grid, Wine/Coffee filter chips, search, sort | yes |
| `/shop?group=wine` \| `?group=coffee` | Filtered landing pages with their own copy and metadata | yes |
| `/shop/<web-slug>` | Product detail, add to basket / buy now | yes |
| `/cart` | Basket | no |
| `/checkout` | Delivery details → M-Pesa STK prompt | no |
| `/order/<token>` | Order confirmation, keyed by an unguessable 24-char token | no |
| `/sitemap.xml`, `/robots.txt` | Generated, includes every product page | — |

The dynamic routes are declared in `winery/hooks.py` under `website_route_rules`.

---

## 2. Managing the shop from the ERP

No separate "Website Item" table — the shop reads ERPNext `Item` directly.
Each Item has a collapsible **Website** section (custom fields, module `Winery`):

| Field | Purpose |
|---|---|
| `publish_on_website` | The on/off switch. Nothing appears in `/shop` without it. |
| `web_slug` | URL segment → `/shop/<web_slug>`. Unique. |
| `web_tagline` | One-liner on product cards. |
| `web_rank` | Sort order (lower first) under "Featured". |
| `web_meta_title` / `web_meta_description` | Search-result title and snippet. |
| `web_description` | Rich text shown under "About this product". |

**To publish a product:** set the Item's Item Group to `Wine` or `Coffee`, tick
`publish_on_website`, give it a `web_slug`, add an image, and make sure it has a
`Standard Selling` **Item Price**. An item with no price shows an "Enquire" button
instead of "Add", so it can never be bought at the wrong price.

Prices, names and availability are **always** re-read from the ERP — the browser's
basket only ever holds `{item_code, qty}`.

---

## 3. Order flow

```
browser basket (localStorage)
  → POST start_checkout          re-prices server-side, creates a Ropen Web Order
  → M-Pesa STK push              via the existing POS Daraja client
  → Safaricom callback           winery.winery.pos.api.mpesa_callback
  → doc event on payment request winery.ecommerce.payments.on_payment_request_update
  → Customer + submitted Sales Order
```

**Ropen Web Order** (new doctype) holds the shopper's details and the priced cart
while payment is in flight. A Sales Order is created *only* on confirmed payment,
so the Sales Order list stays free of abandoned baskets. The web order links to
its Customer, Sales Order and M-Pesa payment request for support queries.

Key properties:

- **Idempotent** — a replayed Safaricom callback, the reconciliation cron and the
  checkout poller can all settle the same order; only the first creates a Sales Order.
- **VAT is inclusive**, matching the POS engine: the shopper pays exactly the cart
  total and ERPNext back-calculates the 16% out of the rate.
- **Guest checkout** — no signup. Returning shoppers are matched on
  `Customer.custom_web_phone`.
- Orders stuck "Pending Payment" for 20 minutes are swept to `Expired` by
  `winery.ecommerce.payments.expire_stale_orders` (cron, every 10 min), after the
  existing STK reconciliation has had its chance.

---

## 4. Before go-live

### Required — M-Pesa credentials

Checkout is **disabled** until these are set. The checkout page says so plainly
rather than failing at the last step.

Desk → **Winery Mpesa Settings**:

- `enabled` ✓, `environment` = Production
- `shortcode`, `till_type` (Paybill / Buy Goods)
- `consumer_key`, `consumer_secret`, `passkey` from the Daraja app
- Copy the read-only `callback_url` into your Daraja app configuration.
  It must be publicly reachable over HTTPS.

### Required — canonical host

Canonical URLs, `og:url` and the sitemap derive from the request host, which emits
`:8000` when the dev server is hit directly. Pin it once TLS is live:

```bash
bench --site winery.finesoftafrika.com execute \
  winery.ecommerce.setup.set_canonical_host \
  --kwargs '{"url": "https://winery.finesoftafrika.com"}'
bench restart
```

### Replace the remaining placeholder content

Site copy and photography now come from the company's own deck (`ropen.pptx`) —
real brand (Banny's), real farm (Njagũ), real history, real product specs and
real photography. What is still placeholder:

**Contact details** — Desk → Website Settings → *Ropen Storefront* section:
phone, email, street, town, county, WhatsApp, and the Facebook / Instagram /
LinkedIn URLs (the footer social icons only appear once a URL is set). These feed
the footer, the contact page and the `LocalBusiness` structured data.

| Field | Current value | Status |
|---|---|---|
| Phone | `+254 700 000 000` | **placeholder** |
| Email | `hello@ropen.co.ke` | **placeholder** |
| Town / County | `Ruiru, Kiambu County` | from the bottle label |
| TerraNova USA contacts | Grace Evans, Robinson Mutiso | from the deck |

**Coffee prices** — the four `ROPEN-COF-*` items carry invented shilling prices.
Their names, origin copy and specs are now real (Njagũ Farm, SL28/SL34,
1,550–1,725m, washed and sun-dried), but confirm the retail pricing.

**Coffee product photography** — the four coffee pack shots are still free-licence
Unsplash stand-ins; the deck contained no packaged-coffee photography. Every other
image on the site — heroes, farm, drying beds, cherry, bottles, label, fibre — is
the company's own. Credits for the remaining stock images are in
`winery/public/images/PHOTO-CREDITS.json`.

**Faces in photographs** — `about-farmers.webp` shows identifiable people at the
farm. Confirm you have their consent to publish before go-live.

---

## 5. Where things live

```
winery/
  ecommerce/
    catalog.py     which Items are published, and at what price (read-only)
    cart.py        authoritative cart re-pricing; browser prices are never trusted
    order.py       Ropen Web Order → Customer + Sales Order
    payments.py    M-Pesa handshake; reuses winery/winery/pos/mpesa.py
    api.py         guest endpoints, all rate-limited
    seo.py         titles, meta, Open Graph, JSON-LD graph
    setup.py       idempotent setup — safe to re-run
    constants.py   department definitions, caps, KSh formatter
  www/             one .py + .html per page
  templates/ropen/ layout, navbar, footer, macros, SVG icon set
  public/
    css/ropen-web.css   design system (brand tokens, components)
    js/ropen-web.js     cart, filters, checkout polling — no framework, no build
    fonts/              self-hosted Fraunces + Inter (variable, latin subsets)
    images/             optimised WebP, product shots under images/products/
  winery/doctype/ropen_web_order{,_item}/
```

Re-run setup at any time — it checks before it writes and deletes nothing:

```bash
bench --site winery.finesoftafrika.com execute winery.ecommerce.setup.run
```

---

## 5a. Asset cache-busting

`ropen-web.css` and `ropen-web.js` are linked with `?v={{ asset_version }}`,
computed in `ecommerce/seo.py` from the two files' mtimes. Without it, Frappe
serves them with `Cache-Control: max-age=43200` and a CSS fix can sit on disk for
twelve hours without reaching a returning visitor — which is exactly what
happened during the build. Edit either file and the version changes on the next
render; nothing to bump by hand.

---

## 6. Design system

- **Type** — Fraunces (display) + Inter (text), both variable, self-hosted as
  woff2 with latin/latin-ext subsets. No Google Fonts request at runtime.
- **Colour** — the brand palette already in `winery.css`: purple `#6B2D8B`,
  gold `#F5A800`, green `#2E7A2E`, dark green `#1A5C2A`.
- **Icons** — inline SVG (`templates/ropen/icons.html`), not emoji, so they render
  identically everywhere and inherit colour.
- The base link colour uses `:where(.ropen) a` so it contributes no specificity and
  component classes (`.btn`, `.cart-btn`, `.chip`) always win. Keep it that way.

The storefront deliberately does **not** extend Frappe's `web.html`: it ships a
lean `<head>` with no desk bundles, which is what keeps it fast.

---

## 7. SEO

Per page: unique title (≤60 chars) and meta description (≤158), canonical URL,
Open Graph + Twitter card, and a JSON-LD `@graph`.

Structured data emitted:

- `Organization` + `LocalBusiness` (address, hours, `paymentAccepted: M-Pesa`) on every page
- `WebSite` with a `SearchAction` pointing at `/shop?q=`
- `BreadcrumbList` on every interior page
- `Product` + `Offer` (price, KES, availability) on product pages
- `ItemList` on the home, shop and department pages
- `FAQPage` on `/winery` and `/coffee`

Also: semantic headings (exactly one `<h1>` per page), alt text on every image,
lazy loading below the fold, responsive `srcset`, WebP, `hreflang`-ready `en-KE`,
skip link, and `noindex` on basket/checkout/order plus on `/shop?q=` search results
(thin, duplicated content).

---

## 8. Verification

Two suites were run against this build; both are in the session scratchpad and can
be re-run against a live site by changing `BASE`.

- **Browser end-to-end (27 checks, all passing)** — filters, search, empty-state
  recovery, Winery/Coffee CTAs landing pre-filtered, add-to-cart, quantity stepper,
  cart re-pricing and removal, checkout validation, mobile nav, zero JS errors.
- **M-Pesa settlement with a stubbed Daraja (24 checks, all passing)** — STK push,
  pending poll, callback → Paid + Customer + submitted Sales Order with a
  VAT-inclusive total matching the cart, replay idempotency, and a cancelled
  payment creating no Sales Order.

All test records were removed afterwards.
