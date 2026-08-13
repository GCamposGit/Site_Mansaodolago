/**
 * Mansão do Lago — direct booking rates (BRL)
 * Source of truth mirrored from js/price-table.md
 *
 * Columns: paying guests (ages 2+), 1–5
 * Rows: night of stay by weekday
 *   mon–thu (2a–5a), fri (6a), sat (S), sun (D)
 * Weekly package: exactly 7 consecutive nights (or each full week in longer stays)
 *
 * Brazilian table uses "." as thousands separator (e.g. 2.638 → 2638).
 */
window.MDL_PRICE_TABLE = {
  currency: "BRL",
  currencySymbol: "R$",
  minGuests: 1,
  maxGuests: 5,
  freeUnderYears: 2,
  /** Per-night rates: [guest1, guest2, guest3, guest4, guest5] */
  nights: {
    mon: [389, 494, 551, 608, 665],
    tue: [389, 494, 551, 608, 665],
    wed: [389, 494, 551, 608, 665],
    thu: [389, 494, 551, 608, 665],
    fri: [489, 569, 626, 683, 740],
    sat: [609, 672, 732, 792, 852],
    sun: [449, 508, 568, 628, 688],
  },
  /** 7-night package by paying guests */
  week7: [2638, 3166, 3511, 3855, 4199],
  /**
   * Events pricing (final on-site total):
   *   per day = nights[dow][0]  (1-guest rate for that weekday)
   *             + eventFeeFlat
   *             + eventFeePerExtraGuest * (guests - 1)
   * Multi-day: sum each calendar day from start to end inclusive.
   * Test: Sat + 20 guests → 609 + 400 + 70*19 = 2339
   */
  eventFeeFlat: 400,
  eventFeePerExtraGuest: 70,
  eventMaxGuests: 35,
  /** Labels for docs / debugging */
  labels: {
    mon: "2a",
    tue: "3a",
    wed: "4a",
    thu: "5a",
    fri: "6a",
    sat: "S",
    sun: "D",
    week7: "7 dias",
  },
};
