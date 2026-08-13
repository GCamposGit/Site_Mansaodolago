<?php
/**
 * Hostinger Cron — prints a clear result (avoids empty "Saída Cron").
 *
 * Use ONE of these commands (check full path in File Manager):
 *
 *   /usr/bin/php /home/u728095317/domains/mansaodolago.com/public_html/api/cron.php
 *   /usr/bin/php /home/u728095317/public_html/api/cron.php
 *   php /home/u728095317/domains/mansaodolago.com/public_html/api/cron.php
 *
 * Schedule: 0 * * * *
 */
error_reporting(E_ALL);
ini_set('display_errors', '1');

$started = date('c');
echo "MansaoDoLago cron start {$started}\n";
echo "PHP " . PHP_VERSION . " SAPI=" . PHP_SAPI . "\n";
echo "Dir: " . __DIR__ . "\n";

$availability = __DIR__ . '/availability.php';
if (!is_file($availability)) {
  echo "ERROR: availability.php not found at {$availability}\n";
  exit(1);
}

$php = (defined('PHP_BINARY') && PHP_BINARY) ? PHP_BINARY : '/usr/bin/php';
// On some hosts PHP_BINARY is empty or points to php-fpm — fall back
if ($php === '' || stripos($php, 'fpm') !== false) {
  $php = '/usr/bin/php';
}

$cmd = escapeshellarg($php) . ' ' . escapeshellarg($availability) . ' 2>&1';
echo "Running: {$cmd}\n";
echo "---\n";

$exitCode = 0;
passthru($cmd, $exitCode);

echo "\n---\n";
echo "Exit code: {$exitCode}\n";

// Also log for File Manager check
$logDir = dirname(__DIR__) . '/data';
if (!is_dir($logDir)) {
  @mkdir($logDir, 0755, true);
}
@file_put_contents(
  $logDir . '/cron-last-run.txt',
  $started . " exit={$exitCode} php={$php}\n"
);

exit($exitCode);
