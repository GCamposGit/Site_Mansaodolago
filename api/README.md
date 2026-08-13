# Availability API

Merges iCal feeds and returns blocked overnight dates as JSON.

```
GET /api/availability.php
```

Success (shape):

```json
{
  "ok": true,
  "blocked": ["2026-08-15", "2026-08-16"],
  "sources": ["airbnb", "booking", "vrbo"],
  "feeds_ok": 3,
  "count": 2
}
```

## Config (not in Git)

```bash
cp config.sample.php config.php
# edit ical_urls + refresh_key
```

Force refresh (production):

```
/api/availability.php?refresh=1&key=YOUR_REFRESH_KEY&diag=1
```

Never put real export URLs in front-end JavaScript.
