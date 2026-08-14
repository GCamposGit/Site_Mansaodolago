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

## Deploy (GitHub Actions → Hostinger)

Push to `master` (or run **Actions → Deploy to Hostinger → Run workflow**).  
The workflow `.github/workflows/deploy-hostinger.yml` uploads over **FTPS** into `public_html/`.

**GitHub secrets** (Settings → Secrets and variables → Actions):

| Secret | Value |
|--------|--------|
| `FTP_SERVER` | FTP hostname from hPanel → Files → FTP Accounts |
| `FTP_USERNAME` | FTP user |
| `FTP_PASSWORD` | FTP password |
| `FTP_SERVER_DIR` | Optional **variable** (not secret). Default `domains/mansaodolago.com/public_html/`. Use `./` if the FTP user already opens inside the live site folder. |

**Never overwritten on the server:** `api/config.php`, `p/` (guest guides), `js/private-*.js`.

**Not uploaded:** `02-docs/`, `scripts/`, `01-assets/`, backups, repo markdown, preview videos.

After HTML/JS/CSS changes: purge the Cloudflare cache.

First run uploads the whole public site (can take 20–60 min). Later runs only sync files that changed.

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
