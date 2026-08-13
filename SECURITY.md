# Security

This is a public marketing repo. Treat anything committed as **world-readable**.

## Never commit

| Item | Where it lives |
|------|----------------|
| iCal export URLs + `refresh_key` | `api/config.php` (server + your PC only) |
| Post-booking guides (address, Wi‑Fi, tokens) | `p/` on Hostinger only |
| Guest/event i18n (street address) | `js/private-*.js` locally; prefer `p/js/` on the server |
| HTTP basic-auth password files | `p/.htpasswd` |
| Backups, SQL dumps, raw photo libraries | local disks |

`api/config.sample.php` is the only config template in Git.

## If Git is (or will be) public

1. Confirm `git status` does **not** list `api/config.php`, `p/`, or `js/private-*.js`.
2. **Rotate** Airbnb / Booking / Vrbo **export** calendar links (new secret in each OTA dashboard → paste into server `config.php`). Old export URLs in chats then stop working.
3. Use a long random `refresh_key` (not a dictionary word). Update Hostinger `config.php` to match.
4. If a `/p/g-…` (or e-/f-) URL was ever in a commit or chat log, **rename the folder** on the server and send the new link only to current guests.
5. After `/p/` pages load scripts from `p/js/`, **delete** `js/private-guest-i18n.js` and `js/private-events-i18n.js` from public `/js/` on Hostinger (those files currently expose the street address to anyone who guesses the filename).
6. Optional: enable HTTP Basic Auth in `p/.htaccess`.

Google Ads / GA4 IDs in `js/site-config.js` appear in the live HTML anyway; they are not calendar secrets.

## Production hardening already in place

- `api/.htaccess` denies HTTP access to `config.php` and `cron.php`
- Root `.htaccess` does **not** 403 `p/` — confirmed guests must open the guides. `robots.txt` has `Disallow: /p/`
- Root `.htaccess` **403**s `scripts/`, `02-docs/`, `01-assets/`, and backup folders if someone uploads them by mistake

## Reporting

If you found a secret in this repository, do not open a public issue with the value. Email **reservas@mansaodolago.com**.
