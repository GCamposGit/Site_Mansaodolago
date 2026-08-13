<?php
/**
 * Copy this file to config.php on Hostinger and paste your export URLs.
 * NEVER put real URLs in front-end JS or commit config.php publicly.
 *
 * WHY MULTIPLE FEEDS?
 * Each OTA’s export can omit nights blocked only on another platform.
 * The site merges ALL feeds: a night is unavailable if it appears on ANY calendar.
 *
 * —— Airbnb export ——
 * Listing → Calendar → Availability → Connect calendars → Export calendar
 * Copy the link (must look like …/calendar/ical/….ics?s=… or …?t=…)
 *
 * —— Booking.com export ——
 * Extranet → Rates & Availability (or Calendar) → Sync calendars / iCal
 * → Export calendar → copy the link (often ical.booking.com or …/ical.html?t=…)
 *
 * —— Vrbo export ——
 * Calendar → Export / iCal → copy the .ics link (often …/icalendar/….ics?…)
 * Technical sync only — no need to show Vrbo on the public site.
 *
 * After editing config.php, force refresh:
 *   /api/availability.php?refresh=1&key=YOUR_REFRESH_KEY&diag=1
 */
return [
  // One or more iCal export URLs (order does not matter)
  'ical_urls' => [
    // 1) Airbnb (recommended)
    'https://www.airbnb.com/calendar/ical/YOUR_LISTING_ID.ics?s=YOUR_SECRET',

    // 2) Booking.com — uncomment and paste your export link
    // 'https://ical.booking.com/v1/export?t=YOUR_TOKEN',

    // 3) Vrbo — uncomment and paste your export link
    // 'https://www.vrbo.com/icalendar/YOUR_FEED_ID.ics?nonTentative',
  ],

  // How long to keep a local cache before re-fetching (seconds)
  'cache_ttl' => 900, // 15 minutes

  // Secret for manual refresh: /api/availability.php?refresh=1&key=…
  'refresh_key' => 'change-me-to-a-long-random-string',
];
