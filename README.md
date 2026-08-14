# Mansão do Lago

Private estate in **Perdizes, São Paulo**: one guest suite, selected events, and film locations.

**Live site:** [www.mansaodolago.com](https://www.mansaodolago.com)

This repository is the **public front-end** of the site (static HTML, CSS, JS, and images).  
Secrets, post-booking guest guides, backups, and internal ops stay **off GitHub**.

---

## What the site does

| Path | Role |
|------|------|
| `/` | Home — stay, events, filming |
| `/hospedagem.html` | Suite, calendar, **final** stay price, WhatsApp |
| `/eventos.html` | Event spaces, **final** event price, confirm on WhatsApp |
| `/filmagens.html` | Location hire (quote on WhatsApp) |
| `/en/` · `/es/` | English / Spanish ad landings |
| `/en/hospedagem.html` · `/en/eventos.html` · `/en/filmagens.html` | Static English money pages |
| `/es/hospedagem.html` · `/es/eventos.html` · `/es/filmagens.html` | Static Spanish money pages |
| `/blog/` | Editorial (Cadernos da Mansão) |

Direct booking is the product. Airbnb and Booking.com are official alternatives with platform protection.

---

## Stack

- Static HTML + CSS (self-hosted Inter / Playfair)
- Vanilla JS: i18n (PT / EN / ES), analytics (GA4 + Ads), calendar, prices
- PHP only for **availability**: merges Airbnb + Booking + Vrbo iCal on the server
- Hostinger + Cloudflare

No Node build is required to open the site.

---

## Preview locally

Open `index.html` in a browser, or serve the folder (needed for `/api/` calendar):

```bash
# example
npx --yes serve -l 4173
```

Calendar blocked nights come from `api/availability.php` in production.

---

## What’s not in this repo

| Kept only on the server / your machine | Why |
|----------------------------------------|-----|
| `api/config.php` | iCal export URLs + refresh key |
| `p/` | Post-booking guides (address, Wi‑Fi, secret URLs) |
| `js/private-guest-i18n.js`, `js/private-events-i18n.js` | Street address for the private guides |
| `02-docs/`, `scripts/`, `01-assets/` | Internal docs, source photos, one-off tools |
| Site / WordPress backups | Dumps must never be public |

Copy `api/config.sample.php` → `api/config.php` locally. Never commit `config.php`.

---

## Deploy (Hostinger `public_html`)

**Upload:** HTML, `blog/`, `css/`, `js/`, `images/`, `fonts/`, `en/`, `es/`, `api/availability.php`, `api/cron.php`, `api/.htaccess`, `data/`, favicons, `robots.txt`, `sitemap.xml`, `llms.txt`, `site.webmanifest`, `.htaccess`.

**Do not upload from Git:** `api/config.php` is created **on the server** from the sample. Keep the existing production `config.php`.

**Do not upload:** `p/` from a public clone (deploy guides separately), `02-docs/`, `scripts/`, backups.

**Private guides:** keep `p/` and `p/js/` on Hostinger. After the guides load scripts from `p/js/`, delete `js/private-*.js` from the public `/js/` folder.

After HTML/JS/CSS changes: purge Cloudflare cache.

---

## Brand

- Green `#0D3B2E` · accent `#1A4D3A` · sand `#F8F5F0`
- Type: Playfair Display + Inter
- Wordmark + monogram `M` in `images/logos/`

---

## Docs in this repo

- [ARCHITECTURE.md](ARCHITECTURE.md) — how pages, i18n, prices, and iCal fit together  
- [SECURITY.md](SECURITY.md) — secrets, `/p/`, and what to rotate  

© Mansão do Lago. All rights reserved.
