/**
 * Mansão do Lago — availability calendar (Airbnb iCal via /api/availability.php)
 * Supports one calendar per page. Wire date fields with:
 *   data-checkin-id / data-checkout-id on #availability-calendar
 *   data-allow-same-day="true" for events/filming (start can equal end)
 */
(function () {
  "use strict";

  var root = document.getElementById("availability-calendar");
  if (!root) return;

  var checkinId = root.getAttribute("data-checkin-id") || "checkin";
  var checkoutId = root.getAttribute("data-checkout-id") || "checkout";
  var allowSameDay = root.getAttribute("data-allow-same-day") === "true";

  var monthLabel = document.getElementById("av-month-label");
  var grid = document.getElementById("av-grid");
  var statusEl = document.getElementById("av-status");
  var legendBusy = document.getElementById("av-legend-busy");
  var prevBtn = document.getElementById("av-prev");
  var nextBtn = document.getElementById("av-next");
  var checkin = document.getElementById(checkinId);
  var checkout = document.getElementById(checkoutId);
  var rangeHint = document.getElementById("av-range-hint");

  var blocked = {};
  var loadFailed = false;
  var loadErrorShown = false;
  var view = new Date();
  view.setDate(1);
  view.setHours(12, 0, 0, 0);

  var selectStart = null;
  var selectEnd = null;

  function t(key, fb) {
    if (window.I18N && window.I18N.t) {
      var v = window.I18N.t(key);
      if (v) return v;
    }
    return fb;
  }

  function pad2(n) {
    n = String(n);
    return n.length < 2 ? "0" + n : n;
  }

  function ymd(d) {
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
  }

  function parseYmd(s) {
    if (!s) return null;
    var p = s.split("-");
    if (p.length !== 3) return null;
    return new Date(+p[0], +p[1] - 1, +p[2], 12, 0, 0, 0);
  }

  function isBusy(key) {
    return !!blocked[key];
  }

  function rangeHasBusy(a, b) {
    var cur = new Date(a.getTime());
    var end = new Date(b.getTime());
    if (end < cur) {
      var tmp = cur;
      cur = end;
      end = tmp;
    }
    /* Same-day: only the single date matters */
    if (cur.getTime() === end.getTime()) {
      return isBusy(ymd(cur));
    }
    /* Nights between start (inclusive) and end (exclusive) for multi-night stays */
    while (cur < end) {
      if (isBusy(ymd(cur))) return true;
      cur.setDate(cur.getDate() + 1);
    }
    return false;
  }

  function setStatus(msg, isError) {
    if (!statusEl) return;
    statusEl.textContent = msg || "";
    statusEl.classList.toggle("is-error", !!isError);
    if (!msg) statusEl.classList.remove("is-error");
  }

  function showLoadErrorOnce() {
    if (!loadFailed || loadErrorShown) return;
    loadErrorShown = true;
    setStatus(
      t(
        "av.error",
        "Could not load live availability. Request dates by form."
      ),
      true
    );
  }

  function pickInMsg() {
    return allowSameDay
      ? t("av.pick_start", "Choose the start date on the calendar")
      : t("av.pick_in", "Choose check-in on the calendar");
  }

  function pickOutMsg() {
    return allowSameDay
      ? t(
          "av.pick_end",
          "Now choose the end date (same day is allowed for single-day use)"
        )
      : t("av.pick_out", "Now choose check-out");
  }

  function apiUrl() {
    var origin = window.location.origin;
    if (!origin || origin === "null" || origin.indexOf("file:") === 0) {
      return "api/availability.php";
    }
    return origin.replace(/\/$/, "") + "/api/availability.php?_=" + Date.now();
  }

  /** Prevents change→fromInputs→render→syncForm infinite loop */
  var syncingFromCalendar = false;

  function syncForm() {
    syncingFromCalendar = true;
    try {
      if (checkin && selectStart) {
        checkin.value = ymd(selectStart);
      }
      if (checkout) {
        checkout.value = selectEnd ? ymd(selectEnd) : "";
      }
    } finally {
      syncingFromCalendar = false;
    }

    if (rangeHint) {
      if (selectStart && selectEnd) {
        if (ymd(selectStart) === ymd(selectEnd)) {
          rangeHint.textContent =
            t("av.range", "Selected:") + " " + ymd(selectStart);
        } else {
          rangeHint.textContent =
            t("av.range", "Selected:") +
            " " +
            ymd(selectStart) +
            " → " +
            ymd(selectEnd);
        }
      } else if (selectStart) {
        rangeHint.textContent = pickOutMsg();
      } else {
        rangeHint.textContent = pickInMsg();
      }
    }

    try {
      document.dispatchEvent(
        new CustomEvent("mdl:booking-dates", {
          detail: {
            checkin: selectStart ? ymd(selectStart) : "",
            checkout: selectEnd ? ymd(selectEnd) : "",
          },
        })
      );
    } catch (e) {
      /* ignore */
    }
  }

  function render() {
    if (!grid || !monthLabel) return;
    var year = view.getFullYear();
    var month = view.getMonth();
    var locale =
      (window.I18N && window.I18N.lang === "en" && "en-US") ||
      (window.I18N && window.I18N.lang === "es" && "es-ES") ||
      "pt-BR";

    monthLabel.textContent = view.toLocaleDateString(locale, {
      month: "long",
      year: "numeric",
    });

    var firstDow = new Date(year, month, 1).getDay();
    var offset = (firstDow + 6) % 7;
    var daysInMonth = new Date(year, month + 1, 0).getDate();
    var today = new Date();
    today.setHours(12, 0, 0, 0);

    var html = "";
    var weekdays =
      locale.indexOf("en") === 0
        ? ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        : locale.indexOf("es") === 0
          ? ["Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"]
          : ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];

    weekdays.forEach(function (w) {
      html += '<span class="av-cal__dow">' + w + "</span>";
    });

    for (var i = 0; i < offset; i++) {
      html += '<span class="av-cal__day is-empty"></span>';
    }

    for (var day = 1; day <= daysInMonth; day++) {
      var d = new Date(year, month, day, 12, 0, 0, 0);
      var key = ymd(d);
      var past = d < today;
      var busy = isBusy(key);
      var classes = ["av-cal__day"];
      if (past) classes.push("is-past");
      if (busy) classes.push("is-busy");
      else if (!past) classes.push("is-free");
      if (selectStart && key === ymd(selectStart)) classes.push("is-start");
      if (selectEnd && key === ymd(selectEnd)) classes.push("is-end");
      if (selectStart && selectEnd && ymd(selectStart) !== ymd(selectEnd)) {
        var a = selectStart < selectEnd ? selectStart : selectEnd;
        var b = selectStart < selectEnd ? selectEnd : selectStart;
        if (d > a && d < b) classes.push("is-in-range");
      }

      var disabled = past || busy;
      html +=
        '<button type="button" class="' +
        classes.join(" ") +
        '" data-date="' +
        key +
        '"' +
        (disabled ? " disabled" : "") +
        ' aria-label="' +
        key +
        (busy ? " blocked" : "") +
        '">' +
        day +
        "</button>";
    }

    grid.innerHTML = html;
    syncForm();
  }

  function onDayClick(key) {
    var d = parseYmd(key);
    if (!d || isBusy(key)) return;

    /* Surface load failure only after the user interacts */
    showLoadErrorOnce();

    if (!selectStart || (selectStart && selectEnd)) {
      selectStart = d;
      selectEnd = null;
      if (!loadFailed) setStatus("");
      render();
      return;
    }

    /* Second click on the same day */
    if (d.getTime() === selectStart.getTime()) {
      if (allowSameDay) {
        selectEnd = new Date(d.getTime());
        if (rangeHasBusy(selectStart, selectEnd)) {
          setStatus(
            t(
              "av.range_busy",
              "That range includes unavailable nights. Please choose other dates."
            ),
            true
          );
          selectEnd = null;
          render();
          return;
        }
        if (!loadFailed) setStatus("");
        render();
      }
      return;
    }

    if (d < selectStart) {
      selectEnd = selectStart;
      selectStart = d;
    } else {
      selectEnd = d;
    }

    if (rangeHasBusy(selectStart, selectEnd)) {
      setStatus(
        t(
          "av.range_busy",
          "That range includes unavailable nights. Please choose other dates."
        ),
        true
      );
      selectEnd = null;
      render();
      return;
    }

    if (!loadFailed) setStatus("");
    render();
  }

  if (grid) {
    grid.addEventListener("click", function (e) {
      var btn = e.target.closest(".av-cal__day[data-date]");
      if (!btn || btn.disabled) return;
      onDayClick(btn.getAttribute("data-date"));
    });
  }

  if (prevBtn) {
    prevBtn.addEventListener("click", function () {
      view.setMonth(view.getMonth() - 1);
      render();
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener("click", function () {
      view.setMonth(view.getMonth() + 1);
      render();
    });
  }

  function fromInputs() {
    if (syncingFromCalendar) return;
    showLoadErrorOnce();
    var a = checkin && checkin.value ? parseYmd(checkin.value) : null;
    var b = checkout && checkout.value ? parseYmd(checkout.value) : null;
    selectStart = a;
    selectEnd = b;
    if (a && b && b < a) {
      selectStart = b;
      selectEnd = a;
    }
    if (
      a &&
      b &&
      !allowSameDay &&
      ymd(a) === ymd(b)
    ) {
      /* Stay calendar: end must be after start */
      selectEnd = null;
      if (checkout) checkout.value = "";
    }
    if (a) {
      view = new Date(a.getFullYear(), a.getMonth(), 1, 12, 0, 0, 0);
    }
    if (selectStart && selectEnd && rangeHasBusy(selectStart, selectEnd)) {
      setStatus(
        t(
          "av.range_busy",
          "That range includes unavailable nights. Please choose other dates."
        ),
        true
      );
    } else if (!loadFailed) {
      setStatus("");
    }
    render();
  }
  if (checkin) checkin.addEventListener("change", fromInputs);
  if (checkout) checkout.addEventListener("change", fromInputs);

  function applyBlockedList(list) {
    blocked = {};
    if (!Array.isArray(list)) return 0;
    list.forEach(function (d) {
      if (typeof d === "string" && /^\d{4}-\d{2}-\d{2}$/.test(d)) {
        blocked[d] = true;
      }
    });
    return Object.keys(blocked).length;
  }

  function formatSources(sources, feedsOk) {
    /* Labels for API source tags only (technical status, not marketing links). */
    var names = {
      airbnb: "Airbnb",
      booking: "Booking.com",
      vrbo: "Vrbo",
    };
    if (Array.isArray(sources) && sources.length) {
      return sources
        .map(function (s) {
          var k = String(s).toLowerCase();
          return names[k] || s;
        })
        .join(" + ");
    }
    if (feedsOk && feedsOk > 1) {
      return t("av.sources_multi", "Synced calendars");
    }
    return t("av.sources_default", "Synced calendars");
  }

  function load() {
    loadFailed = false;
    loadErrorShown = false;
    /* Neutral loading — never show as error */
    setStatus(t("av.loading", "Loading availability…"), false);

    fetch(apiUrl(), { credentials: "same-origin", cache: "no-store" })
      .then(function (r) {
        return r.json().then(function (data) {
          return { httpOk: r.ok, data: data };
        });
      })
      .then(function (res) {
        var data = res.data || {};
        var n = applyBlockedList(data.blocked);

        if (data.error === "ical_not_configured" || data.source === "placeholder") {
          /* Soft notice, not a hard red failure on open */
          loadFailed = true;
          setStatus("");
        } else if (data.ok === false && n === 0) {
          loadFailed = true;
          setStatus("");
        } else {
          loadFailed = false;
          var srcLabel = formatSources(data.sources, data.feeds_ok || data.feeds);
          var base =
            t("av.ready", "Synced with") +
            " " +
            srcLabel +
            " (" +
            n +
            " " +
            t("av.blocked_nights", "blocked nights") +
            ")";
          if (data.stale) {
            base += " — " + t("av.stale", "last good cache");
          }
          setStatus(base, false);
        }

        if (legendBusy) legendBusy.hidden = false;
        render();
      })
      .catch(function () {
        loadFailed = true;
        loadErrorShown = false;
        /* Do not show red error until the user interacts */
        setStatus("");
        render();
      });
  }

  document.addEventListener("mdl:langchange", function () {
    render();
    load();
  });

  /* Initial range hint without error */
  if (rangeHint && !rangeHint.textContent.trim()) {
    rangeHint.textContent = pickInMsg();
  }

  load();
})();
