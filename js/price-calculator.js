/**
 * Direct-booking price estimate from MDL_PRICE_TABLE.
 * Listens to #checkin, #checkout, #guests on #booking-form.
 * Guest count 1–5 for the rate table. Infants under 2 do not pay (shown in note)
 * but still count toward the hard max of 5 people in the suite.
 */
(function () {
  "use strict";

  var table = window.MDL_PRICE_TABLE;
  if (!table) return;

  var form = document.getElementById("booking-form");
  var checkinEl = document.getElementById("checkin");
  var checkoutEl = document.getElementById("checkout");
  var guestsEl = document.getElementById("guests");
  var out = document.getElementById("price-estimate");
  if (!form || !checkinEl || !checkoutEl || !guestsEl || !out) return;

  var DOW = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

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

  function guestIndex(n) {
    var g = Math.max(table.minGuests, Math.min(table.maxGuests, n | 0));
    return g - 1;
  }

  function nightRate(date, payingGuests) {
    var key = DOW[date.getDay()];
    var row = table.nights[key];
    if (!row) return 0;
    return row[guestIndex(payingGuests)] || 0;
  }

  function weekRate(payingGuests) {
    return table.week7[guestIndex(payingGuests)] || 0;
  }

  /**
   * @returns {null|{nights:number, payingGuests:number, total:number, breakdown:Array, usedWeeklyPackages:number, nightlySubtotal:number}}
   */
  function calculate(checkinStr, checkoutStr, payingGuests) {
    var start = parseYmd(checkinStr);
    var end = parseYmd(checkoutStr);
    if (!start || !end || end <= start) return null;

    var paying = Math.max(
      table.minGuests,
      Math.min(table.maxGuests, parseInt(payingGuests, 10) || 1)
    );

    var nights = [];
    var cur = new Date(start.getTime());
    while (cur < end) {
      nights.push({
        date: new Date(cur.getTime()),
        rate: nightRate(cur, paying),
        dow: DOW[cur.getDay()],
      });
      cur = addDays(cur, 1);
    }
    if (!nights.length) return null;

    var nightlySubtotal = nights.reduce(function (s, n) {
      return s + n.rate;
    }, 0);

    var fullWeeks = Math.floor(nights.length / 7);
    var remCount = nights.length % 7;
    var usedWeekly = 0;
    var total = nightlySubtotal;

    if (fullWeeks > 0) {
      var packagePart = fullWeeks * weekRate(paying);
      var remPart = 0;
      /* Remaining nights after full weeks (chronological tail) */
      for (var i = fullWeeks * 7; i < nights.length; i++) {
        remPart += nights[i].rate;
      }
      var packageTotal = packagePart + remPart;
      if (packageTotal <= nightlySubtotal) {
        total = packageTotal;
        usedWeekly = fullWeeks;
      }
    }

    return {
      nights: nights.length,
      payingGuests: paying,
      total: total,
      breakdown: nights,
      usedWeeklyPackages: usedWeekly,
      nightlySubtotal: nightlySubtotal,
      remNights: remCount,
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
      out.removeAttribute("data-nights");
      return;
    }

    var nightsLabel = t("price.nights", "noites");
    if (result.nights === 1) nightsLabel = t("price.night_one", "noite");

    var guestsLabel = t("price.paying_guests", "hóspedes");
    var totalLabel = t("price.estimate", "Total");
    var note = t("price.note", "Preço da reserva direta.");
    var freeNote = t(
      "price.infants",
      "Crianças até 2 anos não pagam, mas contam no limite de 5."
    );

    var weekNote = "";
    if (result.usedWeeklyPackages > 0) {
      weekNote =
        '<p class="price-estimate__week">' +
        t(
          "price.week_applied",
          "Pacote de 7 noites aplicado quando for mais vantajoso."
        ) +
        "</p>";
    }

    out.hidden = false;
    out.setAttribute("data-total", String(result.total));
    out.setAttribute("data-nights", String(result.nights));
    out.setAttribute("data-guests", String(result.payingGuests));
    out.innerHTML =
      '<div class="price-estimate__inner">' +
      '<p class="price-estimate__label">' +
      totalLabel +
      "</p>" +
      '<p class="price-estimate__total">' +
      formatBRL(result.total) +
      "</p>" +
      '<p class="price-estimate__meta">' +
      result.nights +
      " " +
      nightsLabel +
      " · " +
      result.payingGuests +
      " " +
      guestsLabel +
      "</p>" +
      weekNote +
      '<p class="price-estimate__note">' +
      freeNote +
      " " +
      note +
      "</p>" +
      "</div>";
  }

  function update() {
    try {
      var result = calculate(
        checkinEl.value,
        checkoutEl.value,
        guestsEl.value
      );
      render(result);
      window.MDL_lastPriceEstimate = result;
    } catch (err) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("price-calculator:", err);
      }
      window.MDL_lastPriceEstimate = null;
    }
  }

  window.MDL_calcPrice = calculate;
  window.MDL_formatPrice = formatBRL;

  ["change", "input"].forEach(function (ev) {
    checkinEl.addEventListener(ev, update);
    checkoutEl.addEventListener(ev, update);
    guestsEl.addEventListener(ev, update);
  });

  /* Fired by availability-calendar after date pick (no change-loop) */
  document.addEventListener("mdl:booking-dates", update);
  document.addEventListener("mdl:langchange", update);

  update();
})();
