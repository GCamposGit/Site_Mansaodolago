/**
 * Event booking price (final) from MDL_PRICE_TABLE.
 *
 * Formula per day:
 *   1-guest weekday rate + eventFeeFlat + eventFeePerExtraGuest × (guests − 1)
 * Multi-day: sum each day from start to end inclusive.
 *
 * Form: #event-request-form · #ev-date-start · #ev-date-end · #ev-people
 * Output: #event-price-estimate
 */
(function () {
  "use strict";

  var table = window.MDL_PRICE_TABLE;
  if (!table || !table.nights) return;

  var form = document.getElementById("event-request-form");
  var startEl = document.getElementById("ev-date-start");
  var endEl = document.getElementById("ev-date-end");
  var peopleEl = document.getElementById("ev-people");
  var out = document.getElementById("event-price-estimate");
  if (!form || !startEl || !endEl || !peopleEl || !out) return;

  var DOW = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
  var FLAT = table.eventFeeFlat != null ? table.eventFeeFlat : 400;
  var PER_EXTRA =
    table.eventFeePerExtraGuest != null ? table.eventFeePerExtraGuest : 70;
  var MAX_G = table.eventMaxGuests != null ? table.eventMaxGuests : 35;
  var MIN_G = 1;

  function t(key, fb) {
    if (window.I18N && window.I18N.t) {
      var v = window.I18N.t(key);
      if (v) return v;
    }
    return fb;
  }

  function parseYmd(s) {
    if (!s) return null;
    var p = String(s).split("-");
    if (p.length !== 3) return null;
    var d = new Date(+p[0], +p[1] - 1, +p[2], 12, 0, 0, 0);
    return isNaN(d.getTime()) ? null : d;
  }

  function addDays(d, n) {
    var x = new Date(d.getTime());
    x.setDate(x.getDate() + n);
    return x;
  }

  function baseGuest1(date) {
    var key = DOW[date.getDay()];
    var row = table.nights[key];
    if (!row || !row.length) return 0;
    return row[0] || 0;
  }

  function parseGuests(raw) {
    var n = parseInt(String(raw || "").replace(/\D/g, ""), 10);
    if (!n || n < MIN_G) return null;
    if (n > MAX_G) n = MAX_G;
    return n;
  }

  /**
   * @returns {null|{days:number, guests:number, total:number, perDay:Array}}
   */
  function calculate(startStr, endStr, guestsRaw) {
    var start = parseYmd(startStr);
    var end = parseYmd(endStr);
    var guests = parseGuests(guestsRaw);
    if (!start || !end || !guests) return null;
    if (end < start) return null;

    var perDay = [];
    var cur = new Date(start.getTime());
    var total = 0;
    while (cur <= end) {
      var base = baseGuest1(cur);
      var dayTotal = base + FLAT + PER_EXTRA * (guests - 1);
      perDay.push({
        date: new Date(cur.getTime()),
        dow: DOW[cur.getDay()],
        base: base,
        total: dayTotal,
      });
      total += dayTotal;
      cur = addDays(cur, 1);
    }
    if (!perDay.length) return null;

    return {
      days: perDay.length,
      guests: guests,
      total: total,
      perDay: perDay,
      flat: FLAT,
      perExtra: PER_EXTRA,
    };
  }

  function formatBRL(n) {
    try {
      return (
        (table.currencySymbol || "R$") +
        "\u00a0" +
        Math.round(n).toLocaleString("pt-BR")
      );
    } catch (e) {
      return (table.currencySymbol || "R$") + " " + Math.round(n);
    }
  }

  function render(result) {
    if (!result) {
      out.hidden = true;
      out.innerHTML = "";
      out.removeAttribute("data-total");
      return;
    }

    var daysLabel =
      result.days === 1
        ? t("ev.price.day_one", "dia")
        : t("ev.price.days", "dias");
    var guestsLabel = t("ev.price.guests", "convidados");
    var totalLabel = t("ev.price.total", "Total do evento");
    var note = t(
      "ev.price.note",
      "Preço final da reserva. Confirme as datas e o valor pelo WhatsApp."
    );

    out.hidden = false;
    out.setAttribute("data-total", String(result.total));
    out.setAttribute("data-days", String(result.days));
    out.setAttribute("data-guests", String(result.guests));
    out.innerHTML =
      '<div class="price-estimate__inner">' +
      '<p class="price-estimate__label">' +
      totalLabel +
      "</p>" +
      '<p class="price-estimate__total">' +
      formatBRL(result.total) +
      "</p>" +
      '<p class="price-estimate__meta">' +
      result.days +
      " " +
      daysLabel +
      " · " +
      result.guests +
      " " +
      guestsLabel +
      "</p>" +
      '<p class="price-estimate__note">' +
      note +
      "</p>" +
      "</div>";
  }

  function update() {
    try {
      var result = calculate(startEl.value, endEl.value, peopleEl.value);
      render(result);
      window.MDL_lastEventPrice = result;
    } catch (err) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("event-price-calculator:", err);
      }
      window.MDL_lastEventPrice = null;
      render(null);
    }
  }

  window.MDL_calcEventPrice = calculate;
  window.MDL_formatEventPrice = formatBRL;

  ["change", "input"].forEach(function (ev) {
    startEl.addEventListener(ev, update);
    endEl.addEventListener(ev, update);
    peopleEl.addEventListener(ev, update);
  });

  document.addEventListener("mdl:booking-dates", update);
  document.addEventListener("mdl:langchange", update);

  /* Self-test (dev): Sat + 20 guests = 2339 */
  try {
    var probe = calculate("2026-08-15", "2026-08-15", "20");
    if (probe && probe.total !== 2339 && typeof console !== "undefined") {
      console.warn(
        "event-price-calculator: expected Sat×20 = 2339, got",
        probe.total
      );
    }
  } catch (e) {}

  update();
})();
