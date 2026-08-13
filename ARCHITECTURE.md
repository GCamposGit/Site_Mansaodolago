# Architecture

Static marketing site. Conversion paths: **stay**, **events**, **filming**.

## Pages

Public HTML at the repo root, plus `blog/`, `en/`, `es/`.  
Shared chrome (sidebar, header, footer, WhatsApp) is **copied per file** on purpose so Hostinger stays FTP-simple. Do not introduce a bundler unless deploy changes.

## Front-end JS

| File | Role |
|------|------|
| `js/site-config.js` | Domain, GA/Ads IDs, listing URLs (no iCal secrets) |
| `js/i18n.js` + `js/i18n-data.js` | PT / EN / ES strings (`?lang=` or `/en/`, `/es/`) |
| `js/seo.js` | Canonical + hreflang. EN/ES query URLs must be self-canonical |
| `js/analytics.js` | GA4 delayed; Ads conversion on click |
| `js/availability-calendar.js` | Reads `/api/availability.php` (blocked nights) |
| `js/price-table.js` | Stay rates + event fee constants |
| `js/price-calculator.js` | Stay total (max 5 guests) |
| `js/event-price-calculator.js` | Event total (max 35 guests) |
| `js/site.js` | Nav, WhatsApp forms, media helpers |
| `js/private-*.js` | **Not in Git.** Guest/event guide copy (address). Lives under `p/js/` on the server |

## Prices (stay)

Per-night table by weekday × paying guests (1–5).  
Children under 2 do not pay; they **count** toward the 5-person cap.

## Prices (events)

Per day:

```
(1-guest rate for that weekday) + R$400 + R$70 × (guests − 1)
```

Multi-day: **sum each calendar day from start to end inclusive**.  
Check: Saturday × 20 guests = **R$ 2.339**.

## Availability

`api/availability.php` fetches every URL in `api/config.php` → `ical_urls` and **unions** busy nights.  
The browser never sees iCal links.

Cron (Hostinger): run `api/cron.php` or `availability.php` via CLI hourly.

## International

- Main site: one HTML + client i18n (`?lang=en|es`).
- Ads landings: static `/en/` and `/es/` (better crawl + LCP).
- Stay cluster: `/hospedagem.html`, `/en/hospedagem.html`, `/es/hospedagem.html`.
- `seo.js` must not point an EN/ES `canonical` at the PT URL.

## Media

Web images live in `images/` (prefer WebP + width variants for heroes).  
Hero video: still image is LCP; MP4 loads after idle on desktop only.
