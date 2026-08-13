<?php
/**
 * Mansão do Lago — availability API (multi-iCal merge)
 *
 * Feeds (config ical_urls): Airbnb, Booking.com, Vrbo, any other ICS export.
 * A night is blocked if it appears on ANY successful feed (union).
 *
 * Web:
 *   GET /api/availability.php
 *   GET /api/availability.php?refresh=1&key=REFRESH_KEY
 *   GET /api/availability.php?diag=1
 *
 * Hostinger Cron (recommended — no URL/key/shell escaping):
 *   /usr/bin/php /home/USER/public_html/api/availability.php
 *   (CLI always force-refreshes all iCal feeds)
 */
$isCli = (php_sapi_name() === 'cli' || PHP_SAPI === 'cli' || defined('MDL_FORCE_CLI'));

if ($isCli) {
  // Hostinger "Ver resultado" needs non-empty stdout
  echo 'MansaoDoLago availability CLI ' . date('c') . "\n";
}

if (!$isCli) {
  header('Content-Type: application/json; charset=utf-8');
  header('Cache-Control: no-store, no-cache, must-revalidate');
  header('Pragma: no-cache');
  header('Access-Control-Allow-Origin: *');
}

$configPath = __DIR__ . '/config.php';
$cachePath = dirname(__DIR__) . '/data/availability.json';

if (!is_file($configPath)) {
  if (!$isCli) {
    http_response_code(500);
  }
  $err = [
    'ok' => false,
    'error' => 'missing_config',
    'message' => 'Create api/config.php from config.sample.php and add your Airbnb iCal URL.',
    'blocked' => [],
    'count' => 0,
  ];
  echo json_out($err);
  if ($isCli) {
    echo "\nSUMMARY: fail missing_config\n";
  }
  exit(1);
}

$config = require $configPath;
if (!is_array($config)) {
  if (!$isCli) {
    http_response_code(500);
  }
  $err = [
    'ok' => false,
    'error' => 'invalid_config',
    'message' => 'api/config.php must return an array.',
    'blocked' => [],
    'count' => 0,
  ];
  echo json_out($err);
  cli_summary($err);
  exit(1);
}

$urls = isset($config['ical_urls']) ? $config['ical_urls'] : [];
if (!is_array($urls)) {
  $urls = $urls ? [$urls] : [];
}
if (empty($urls) && !empty($config['ical_url'])) {
  $urls = [$config['ical_url']];
}
if (empty($urls) && !empty($config['airbnb_ical'])) {
  $urls = [$config['airbnb_ical']];
}

$ttl = isset($config['cache_ttl']) ? (int) $config['cache_ttl'] : 900;
if ($ttl < 60) {
  $ttl = 60;
}
$refreshKey = isset($config['refresh_key']) ? (string) $config['refresh_key'] : '';

$diag = !$isCli && isset($_GET['diag']) && $_GET['diag'] === '1';
// CLI (Hostinger cron): always re-fetch iCals — no key needed in the command line
$force = $isCli;
if (!$force && isset($_GET['refresh']) && $_GET['refresh'] === '1') {
  $key = isset($_GET['key']) ? (string) $_GET['key'] : '';
  // Allow URL-encoded keys; trim whitespace from panel pastes
  $key = rawurldecode(trim($key));
  if ($refreshKey !== '' && hash_equals($refreshKey, $key)) {
    $force = true;
  }
}

$cached = load_cache($cachePath);
$cacheIsPlaceholder = is_placeholder_cache($cached);
$cacheAge = is_file($cachePath) ? (time() - filemtime($cachePath)) : PHP_INT_MAX;

// Cache hit only if we have a real multi-night list (or empty ok from known empty ical)
$cacheFresh = !$force
  && !$cacheIsPlaceholder
  && is_file($cachePath)
  && $cacheAge < $ttl
  && is_array($cached)
  && isset($cached['blocked'])
  && is_array($cached['blocked'])
  && !empty($cached['ok']);

if ($cacheFresh) {
  $cached['cache'] = 'hit';
  $cached['age_seconds'] = $cacheAge;
  if ($diag) {
    $cached['diag'] = ['note' => 'Served from cache. Add &refresh=1&key=... to re-fetch.'];
  }
  echo json_out($cached);
  cli_summary($cached);
  exit(0);
}

$validUrls = [];
foreach ($urls as $u) {
  $u = trim((string) $u);
  // strip wrapping quotes people paste from docs
  $u = trim($u, " \t\"'");
  if ($u === '' || is_placeholder_url($u)) {
    continue;
  }
  if (!preg_match('#^https?://#i', $u)) {
    continue;
  }
  $validUrls[] = $u;
}

if (!$validUrls) {
  if (!$isCli) {
    http_response_code(503);
  }
  $err = [
    'ok' => false,
    'error' => 'ical_not_configured',
    'message' => 'Add the real Airbnb export URL in api/config.php under ical_urls (https://...ics?s=...).',
    'blocked' => [],
    'count' => 0,
    'source' => 'none',
  ];
  echo json_out($err);
  cli_summary($err);
  exit(1);
}

$blockedSet = [];
$errors = [];
$diagFeeds = [];

$feedLabels = [];
$feedOk = 0;

foreach ($validUrls as $idx => $url) {
  $meta = [];
  $ics = fetch_url($url, $meta);
  $host = (string) parse_url($url, PHP_URL_HOST);
  $label = feed_label_from_host($host);
  $feed = [
    'index' => $idx,
    'label' => $label,
    'host' => $host,
    'http_code' => isset($meta['http_code']) ? $meta['http_code'] : null,
    'bytes' => $ics !== null ? strlen($ics) : 0,
  ];

  if ($ics === null || $ics === '') {
    $errors[] = 'fetch_failed:' . $label;
    $feed['error'] = 'fetch_failed';
    if (!empty($meta['curl_error'])) {
      $feed['curl_error'] = $meta['curl_error'];
    }
    $diagFeeds[] = $feed;
    continue;
  }

  // Strip UTF-8 BOM
  if (substr($ics, 0, 3) === "\xEF\xBB\xBF") {
    $ics = substr($ics, 3);
  }

  if (stripos($ics, 'BEGIN:VCALENDAR') === false) {
    $errors[] = 'invalid_ics:' . $label;
    $feed['error'] = 'invalid_ics';
    $feed['body_start'] = substr(preg_replace('/\s+/', ' ', $ics), 0, 160);
    $diagFeeds[] = $feed;
    continue;
  }

  $parsed = parse_ics_blocked($ics);
  $feed['vevents'] = $parsed['vevents'];
  $feed['freebusy'] = $parsed['freebusy'];
  $feed['rrule_expanded'] = $parsed['rrule_expanded'];
  $feed['skipped'] = $parsed['skipped'];
  $feed['raw_samples'] = $parsed['raw_samples'];
  $feed['days'] = count($parsed['days']);
  $feed['sample_days'] = array_slice($parsed['days'], 0, 12);
  $feed['ok'] = true;
  $feedOk++;
  $feedLabels[] = $label;

  foreach ($parsed['days'] as $day) {
    $blockedSet[$day] = true;
  }
  $diagFeeds[] = $feed;
}

$blocked = array_keys($blockedSet);
sort($blocked);

// Unique labels preserving order
$feedLabels = array_values(array_unique($feedLabels));

$payload = [
  'ok' => true,
  'blocked' => $blocked,
  'updated' => gmdate('c'),
  'source' => 'ical',
  // e.g. ["airbnb","booking","vrbo"] — status only (no public OTA links required)
  'sources' => $feedLabels,
  'feeds' => count($validUrls),
  'feeds_ok' => $feedOk,
  'count' => count($blocked),
  'cache' => 'miss',
  'via' => $isCli ? 'cli' : 'http',
];

if ($errors) {
  $payload['warnings'] = array_values(array_unique($errors));
  if (empty($blocked)) {
    $payload['ok'] = false;
    $payload['error'] = 'ical_fetch_failed';
    $payload['message'] = 'Could not download or parse the iCal feed.';
  }
}

// Suspicious: feed downloaded but almost no nights while many VEVENTs exist
$totalVevents = 0;
foreach ($diagFeeds as $f) {
  if (isset($f['vevents'])) {
    $totalVevents += (int) $f['vevents'];
  }
}
if ($totalVevents >= 5 && count($blocked) <= 2) {
  $payload['ok'] = false;
  $payload['error'] = 'parse_suspiciously_low';
  $payload['message'] = 'iCal has many events but almost no nights were parsed. Check diag=1 samples. Upload latest availability.php.';
  $payload['warnings'] = array_values(array_unique(array_merge(
    isset($payload['warnings']) ? $payload['warnings'] : [],
    ['parse_suspiciously_low']
  )));
}

if ($diag) {
  $payload['diag'] = [
    'feeds' => $diagFeeds,
    'force' => $force,
    'ttl' => $ttl,
    'php' => PHP_VERSION,
  ];
}

// Stale fallback
if (empty($blocked) && $errors && !$cacheIsPlaceholder && !empty($cached['blocked'])) {
  $cached['stale'] = true;
  $cached['ok'] = true;
  $cached['warnings'] = array_values(array_unique($errors));
  $cached['message'] = 'Serving last good cache; live iCal fetch failed.';
  if ($diag) {
    $cached['diag'] = ['feeds' => $diagFeeds, 'served' => 'stale_cache'];
  }
  echo json_out($cached);
  cli_summary($cached);
  exit(!empty($cached['ok']) ? 0 : 1);
}

// Persist only sensible results
if (!empty($blocked) || (empty($errors) && empty($payload['error']))) {
  @file_put_contents($cachePath, json_out($payload));
}

echo json_out($payload);
cli_summary($payload);
exit(!empty($payload['ok']) ? 0 : 1);

/* ================= helpers ================= */

function cli_summary($data)
{
  global $isCli, $cachePath;
  if (empty($isCli) || !is_array($data)) {
    return;
  }
  $count = isset($data['count']) ? $data['count'] : (isset($data['blocked']) ? count($data['blocked']) : 0);
  $ok = !empty($data['ok']) ? 'ok' : 'fail';
  $sources = '?';
  if (!empty($data['sources']) && is_array($data['sources'])) {
    $sources = implode('+', $data['sources']);
  }
  $err = isset($data['error']) ? $data['error'] : '';
  echo "\nSUMMARY: {$ok} count={$count} sources={$sources}" . ($err ? " error={$err}" : '') . "\n";

  $logDir = dirname($cachePath);
  if (!is_dir($logDir)) {
    @mkdir($logDir, 0755, true);
  }
  @file_put_contents(
    $logDir . '/cron-last-run.txt',
    date('c') . " SUMMARY: {$ok} count={$count} sources={$sources}\n"
  );
}

function json_out($data)
{
  return json_encode($data, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
}

/** Map host → short label for UI (airbnb | booking | vrbo | other) */
function feed_label_from_host($host)
{
  $h = strtolower((string) $host);
  if (strpos($h, 'airbnb.') !== false) {
    return 'airbnb';
  }
  if (strpos($h, 'booking.') !== false) {
    return 'booking';
  }
  /* Vrbo / Expedia Group / HomeAway iCal hosts */
  if (
    strpos($h, 'vrbo.') !== false ||
    strpos($h, 'homeaway.') !== false ||
    strpos($h, 'expedia.') !== false
  ) {
    return 'vrbo';
  }
  return $h !== '' ? $h : 'ical';
}

function is_placeholder_url($u)
{
  $u = strtolower($u);
  if (strpos($u, 'paste_airbnb') !== false) return true;
  if (strpos($u, 'your_listing') !== false) return true;
  if (strpos($u, 'your_secret') !== false) return true;
  if (strpos($u, 'example.com') !== false) return true;
  if (preg_match('/your_[a-z0-9_]+/', $u)) return true;
  return false;
}

function is_placeholder_cache($cached)
{
  if (!$cached || !is_array($cached)) return true;
  if (isset($cached['source']) && $cached['source'] === 'placeholder') return true;
  if (isset($cached['message']) && stripos((string) $cached['message'], 'Will be filled') !== false) {
    return true;
  }
  // Old broken cache that only has "today" + "today+1y" is useless
  if (!empty($cached['blocked']) && is_array($cached['blocked']) && count($cached['blocked']) <= 2) {
    $today = gmdate('Y-m-d');
    $nextY = gmdate('Y-m-d', strtotime('+1 year'));
    $b = $cached['blocked'];
    if (in_array($today, $b, true) || in_array($nextY, $b, true)) {
      return true;
    }
  }
  return false;
}

function load_cache($cachePath)
{
  if (!is_file($cachePath)) return null;
  $raw = @file_get_contents($cachePath);
  if ($raw === false || $raw === '') return null;
  $data = json_decode($raw, true);
  return is_array($data) ? $data : null;
}

function fetch_url($url, &$meta = null)
{
  $meta = ['http_code' => 0];
  $headers = [
    'Accept: text/calendar, text/plain, application/octet-stream, */*',
    'Accept-Language: en-US,en;q=0.9,pt-BR;q=0.8',
  ];

  if (function_exists('curl_init')) {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
      CURLOPT_RETURNTRANSFER => true,
      CURLOPT_FOLLOWLOCATION => true,
      CURLOPT_MAXREDIRS => 8,
      CURLOPT_TIMEOUT => 45,
      CURLOPT_CONNECTTIMEOUT => 15,
      CURLOPT_USERAGENT => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      CURLOPT_HTTPHEADER => $headers,
      CURLOPT_SSL_VERIFYPEER => true,
      CURLOPT_SSL_VERIFYHOST => 2,
      CURLOPT_ENCODING => '',
    ]);
    $body = curl_exec($ch);
    $meta['http_code'] = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err = curl_error($ch);
    curl_close($ch);
    if ($body === false || $meta['http_code'] >= 400) {
      $meta['curl_error'] = $err;
      return null;
    }
    return $body;
  }

  $ctx = stream_context_create([
    'http' => [
      'timeout' => 45,
      'header' => "User-Agent: Mozilla/5.0\r\n" . implode("\r\n", $headers) . "\r\n",
      'follow_location' => 1,
    ],
    'ssl' => [
      'verify_peer' => true,
      'verify_peer_name' => true,
    ],
  ]);
  $body = @file_get_contents($url, false, $ctx);
  if ($body === false) {
    return null;
  }
  $meta['http_code'] = 200;
  return $body;
}

/**
 * Full ICS parse → blocked overnight dates (Y-m-d).
 * Supports VEVENT (+ RRULE) and VFREEBUSY.
 */
function parse_ics_blocked($ics)
{
  $ics = str_replace(["\r\n", "\r"], "\n", $ics);
  // Unfold continued lines (RFC 5545)
  $ics = preg_replace("/\n[ \t]/", '', $ics);

  $lines = explode("\n", $ics);
  $days = [];
  $vevents = 0;
  $freebusy = 0;
  $rruleExpanded = 0;
  $skipped = 0;
  $rawSamples = [];

  $inEvent = false;
  $inFreebusy = false;
  $props = [];

  $flushEvent = function () use (&$props, &$days, &$vevents, &$rruleExpanded, &$skipped, &$rawSamples) {
    if (empty($props)) {
      return;
    }
    $vevents++;

    $status = isset($props['STATUS']) ? strtoupper($props['STATUS']) : '';
    if ($status === 'CANCELLED') {
      $skipped++;
      $props = [];
      return;
    }

    $startRaw = isset($props['DTSTART']) ? $props['DTSTART'] : null;
    $endRaw = isset($props['DTEND']) ? $props['DTEND'] : null;
    $durRaw = isset($props['DURATION']) ? $props['DURATION'] : null;
    $rrule = isset($props['RRULE']) ? $props['RRULE'] : null;

    if (count($rawSamples) < 8) {
      $rawSamples[] = [
        'DTSTART' => $startRaw,
        'DTEND' => $endRaw,
        'DURATION' => $durRaw,
        'RRULE' => $rrule ? substr($rrule, 0, 80) : null,
        'SUMMARY' => isset($props['SUMMARY']) ? substr($props['SUMMARY'], 0, 40) : null,
      ];
    }

    $start = parse_ical_date_value($startRaw);
    if (!$start) {
      $skipped++;
      $props = [];
      return;
    }

    $end = parse_ical_date_value($endRaw);
    if (!$end && $durRaw) {
      $end = add_ical_duration($start, $durRaw);
    }

    $rangeDays = expand_night_range($start, $end);
    if ($rrule) {
      $extra = expand_rrule_nights($start, $end, $rrule);
      $rruleExpanded += count($extra);
      $rangeDays = array_merge($rangeDays, $extra);
    }

    foreach ($rangeDays as $d) {
      $days[$d] = true;
    }
    $props = [];
  };

  foreach ($lines as $line) {
    $line = trim($line);
    if ($line === '') {
      continue;
    }

    $upper = strtoupper($line);

    if ($upper === 'BEGIN:VEVENT') {
      $inEvent = true;
      $props = [];
      continue;
    }
    if ($upper === 'END:VEVENT') {
      if ($inEvent) {
        $flushEvent();
      }
      $inEvent = false;
      $props = [];
      continue;
    }
    if ($upper === 'BEGIN:VFREEBUSY') {
      $inFreebusy = true;
      continue;
    }
    if ($upper === 'END:VFREEBUSY') {
      $inFreebusy = false;
      continue;
    }

    if ($inEvent) {
      // PROP;param=x:value  OR  PROP:value
      if (preg_match('/^([A-Za-z0-9-]+)((?:;[^:]*)*):(.*)$/', $line, $m)) {
        $name = strtoupper($m[1]);
        // Ignore parameters for storage; keep raw value string
        $value = $m[3];
        // Prefer first DTSTART/DTEND only
        if (!isset($props[$name])) {
          $props[$name] = $value;
        }
        // Also keep params for DATE detection if value is bare
        if ($name === 'DTSTART' || $name === 'DTEND') {
          $props[$name . '_PARAMS'] = strtoupper($m[2]);
        }
      }
      continue;
    }

    if ($inFreebusy && preg_match('/^FREEBUSY(?:;[^:]*)?:(.+)$/i', $line, $m)) {
      $freebusy++;
      // FREEBUSY:20260724T000000Z/20260727T000000Z  (can be comma-separated)
      $periods = preg_split('/,/', $m[1]);
      foreach ($periods as $period) {
        $period = trim($period);
        if (strpos($period, '/') === false) {
          continue;
        }
        list($a, $b) = explode('/', $period, 2);
        $start = parse_ical_date_value($a);
        $end = parse_ical_date_value($b);
        foreach (expand_night_range($start, $end) as $d) {
          $days[$d] = true;
        }
      }
    }
  }

  // If file ended mid-event
  if ($inEvent && !empty($props)) {
    $flushEvent();
  }

  $list = array_keys($days);
  sort($list);

  return [
    'days' => $list,
    'vevents' => $vevents,
    'freebusy' => $freebusy,
    'rrule_expanded' => $rruleExpanded,
    'skipped' => $skipped,
    'raw_samples' => $rawSamples,
  ];
}

/**
 * Parse iCal date/datetime value to DateTime at local calendar date (00:00).
 * Accepts: 20260724 | 20260724T150000 | 20260724T150000Z | 2026-07-24
 */
function parse_ical_date_value($raw)
{
  if ($raw === null || $raw === '') {
    return null;
  }
  $raw = trim($raw);
  $raw = preg_replace('/\s+/', '', $raw);
  $raw = trim($raw, "\"'");

  // Keep only useful chars
  if (!preg_match('/^\d{4}-?\d{2}-?\d{2}(T\d{2}:?\d{2}:?\d{2}Z?)?$/i', $raw)
    && !preg_match('/^\d{8}(T\d{6}Z?)?$/i', $raw)) {
    // Try extract first 8 digits as YYYYMMDD
    if (preg_match('/(\d{8})/', $raw, $m)) {
      $raw = $m[1];
    } else {
      return null;
    }
  }

  $isZ = (bool) preg_match('/Z$/i', $raw);
  $raw = rtrim($raw, 'Zz');

  // Dashed date
  if (preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $raw, $m)) {
    return datetime_ymd((int) $m[1], (int) $m[2], (int) $m[3]);
  }

  // Compact date
  if (preg_match('/^(\d{4})(\d{2})(\d{2})$/', $raw, $m)) {
    return datetime_ymd((int) $m[1], (int) $m[2], (int) $m[3]);
  }

  // Compact datetime
  if (preg_match('/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$/', $raw, $m)) {
    // Use calendar date in property's nominal timezone; for Zulu use UTC date
    if ($isZ) {
      try {
        $dt = new DateTime(
          sprintf('%04d-%02d-%02d %02d:%02d:%02d', $m[1], $m[2], $m[3], $m[4], $m[5], $m[6]),
          new DateTimeZone('UTC')
        );
        // Convert to São Paulo for "which night" semantics for Brazil property
        $dt->setTimezone(new DateTimeZone('America/Sao_Paulo'));
        return datetime_ymd((int) $dt->format('Y'), (int) $dt->format('m'), (int) $dt->format('d'));
      } catch (Exception $e) {
        return datetime_ymd((int) $m[1], (int) $m[2], (int) $m[3]);
      }
    }
    return datetime_ymd((int) $m[1], (int) $m[2], (int) $m[3]);
  }

  // Dashed datetime
  if (preg_match('/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/', $raw, $m)) {
    return datetime_ymd((int) $m[1], (int) $m[2], (int) $m[3]);
  }

  return null;
}

function datetime_ymd($y, $m, $d)
{
  if ($y < 2000 || $y > 2100 || $m < 1 || $m > 12 || $d < 1 || $d > 31) {
    return null;
  }
  try {
    $dt = new DateTime('now', new DateTimeZone('UTC'));
    $dt->setDate($y, $m, $d);
    $dt->setTime(0, 0, 0);
    // Validate (e.g. Feb 31)
    if ((int) $dt->format('Y') !== $y || (int) $dt->format('n') !== $m || (int) $dt->format('j') !== $d) {
      return null;
    }
    return $dt;
  } catch (Exception $e) {
    return null;
  }
}

/**
 * Airbnb all-day: DTEND exclusive.
 * Timed checkout next day: nights from start date inclusive to end date exclusive.
 */
function expand_night_range($start, $end)
{
  $out = [];
  if (!$start) {
    return $out;
  }
  $startDay = clone $start;
  $startDay->setTime(0, 0, 0);

  if (!$end) {
    $out[] = $startDay->format('Y-m-d');
    return $out;
  }

  $endDay = clone $end;
  $endDay->setTime(0, 0, 0);

  if ($endDay <= $startDay) {
    // Same day or inverted → block start night only
    $out[] = $startDay->format('Y-m-d');
    return $out;
  }

  $cursor = clone $startDay;
  $guard = 0;
  while ($cursor < $endDay && $guard < 800) {
    $out[] = $cursor->format('Y-m-d');
    $cursor->modify('+1 day');
    $guard++;
  }
  return $out;
}

function add_ical_duration(DateTime $start, $duration)
{
  $duration = trim($duration);
  // P2D / P1DT5H / PT5H
  $days = 0;
  $hours = 0;
  if (preg_match('/^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/i', $duration, $m)) {
    $days = isset($m[1]) && $m[1] !== '' ? (int) $m[1] : 0;
    $hours = isset($m[2]) && $m[2] !== '' ? (int) $m[2] : 0;
  } else {
    return null;
  }
  $end = clone $start;
  if ($days) {
    $end->modify('+' . $days . ' days');
  }
  if ($hours) {
    $end->modify('+' . $hours . ' hours');
  }
  return $end;
}

/**
 * Expand simple RRULE for a window: past 30 days → +24 months.
 * Supports FREQ=DAILY|WEEKLY|YEARLY with COUNT/UNTIL/INTERVAL.
 */
function expand_rrule_nights(DateTime $start, $end, $rrule)
{
  $out = [];
  $parts = [];
  foreach (explode(';', $rrule) as $bit) {
    if (strpos($bit, '=') === false) {
      continue;
    }
    list($k, $v) = explode('=', $bit, 2);
    $parts[strtoupper(trim($k))] = strtoupper(trim($v));
  }
  if (empty($parts['FREQ'])) {
    return $out;
  }

  $freq = $parts['FREQ'];
  $interval = isset($parts['INTERVAL']) ? max(1, (int) $parts['INTERVAL']) : 1;
  $count = isset($parts['COUNT']) ? (int) $parts['COUNT'] : 200;
  if ($count > 400) {
    $count = 400;
  }

  $windowStart = new DateTime('today', new DateTimeZone('UTC'));
  $windowStart->modify('-30 days');
  $windowEnd = new DateTime('today', new DateTimeZone('UTC'));
  $windowEnd->modify('+24 months');

  $until = null;
  if (!empty($parts['UNTIL'])) {
    $until = parse_ical_date_value($parts['UNTIL']);
  }

  $durationNights = 1;
  if ($end) {
    $tmp = expand_night_range($start, $end);
    $durationNights = max(1, count($tmp));
  }

  $cursor = clone $start;
  $cursor->setTime(0, 0, 0);
  $n = 0;

  while ($n < $count && $cursor <= $windowEnd) {
    if ($until && $cursor > $until) {
      break;
    }
    if ($cursor >= $windowStart) {
      $segEnd = clone $cursor;
      $segEnd->modify('+' . $durationNights . ' days');
      foreach (expand_night_range($cursor, $segEnd) as $d) {
        $out[] = $d;
      }
    }
    $n++;
    if ($freq === 'DAILY') {
      $cursor->modify('+' . $interval . ' days');
    } elseif ($freq === 'WEEKLY') {
      $cursor->modify('+' . (7 * $interval) . ' days');
    } elseif ($freq === 'MONTHLY') {
      $cursor->modify('+' . $interval . ' months');
    } elseif ($freq === 'YEARLY') {
      $cursor->modify('+' . $interval . ' years');
    } else {
      break;
    }
  }

  return $out;
}
