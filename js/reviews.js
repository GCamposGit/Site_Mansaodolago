/**
 * Renders curated guest reviews as a multi-card carousel with flag icons.
 * Requires js/reviews-data.js first.
 *
 * Desktop/tablet: 3 cards side-by-side; advance 1 card per click.
 * Mobile: 1 card visible; advance 1.
 */
(function () {
  "use strict";

  var data = window.SITE_REVIEWS;
  if (!data) return;

  /** Colored flag icon (flagcdn) from ISO country code */
  function flagImg(cc, title) {
    if (!cc || String(cc).length !== 2) return "";
    var c = String(cc).toLowerCase();
    var t = escapeHtml(title || c.toUpperCase());
    return (
      '<img class="review-card__flag" src="https://flagcdn.com/w40/' +
      c +
      '.png" srcset="https://flagcdn.com/w80/' +
      c +
      '.png 2x" width="22" height="16" alt="' +
      t +
      '" title="' +
      t +
      '" loading="lazy" decoding="async">'
    );
  }

  function t(key, fallback) {
    if (window.I18N && typeof window.I18N.t === "function") {
      var v = window.I18N.t(key);
      if (v && v !== key) return v;
    }
    return fallback || key;
  }

  function getLang() {
    if (window.I18N && window.I18N.lang) return window.I18N.lang;
    try {
      var stored = localStorage.getItem("mdl_lang");
      if (stored) return stored;
    } catch (e) {}
    var htmlLang = (document.documentElement.lang || "").toLowerCase();
    if (htmlLang.indexOf("en") === 0) return "en";
    if (htmlLang.indexOf("es") === 0) return "es";
    return "pt";
  }

  /** Pick review body for current language (PT default, EN/ES overrides). */
  function reviewText(it) {
    var lang = getLang();
    if (lang === "en" && it.textEn) return it.textEn;
    if (lang === "es" && it.textEs) return it.textEs;
    if (it.textKey) return t(it.textKey, it.text || "");
    return it.text || "";
  }

  function reviewLocation(it) {
    var lang = getLang();
    if (lang === "en" && it.locationEn) return it.locationEn;
    if (lang === "es" && it.locationEs) return it.locationEs;
    return it.location || "";
  }

  /** International guests first (non-BR), keep relative order within each group. */
  function sortInternationalFirst(items) {
    var intl = [];
    var local = [];
    items.forEach(function (it) {
      if (String(it.country || "").toUpperCase() === "BR") local.push(it);
      else intl.push(it);
    });
    return intl.concat(local);
  }

  function stars(n, scale) {
    scale = scale || 5;
    var full;
    if (scale === 10) {
      full = Math.round((Number(n) || 10) / 2);
    } else {
      full = Math.round(Number(n) || 5);
    }
    if (full < 1) full = 5;
    if (full > 5) full = 5;
    var s = "";
    for (var i = 0; i < 5; i++) s += i < full ? "★" : "☆";
    return s;
  }

  function formatRating(n, decimals) {
    var x = Number(n);
    if (!isFinite(x)) return "—";
    if (decimals === 0) return String(Math.round(x));
    var d = decimals != null ? decimals : 2;
    var s = x.toFixed(d);
    /* EN uses decimal point; PT/ES keep comma */
    if (getLang() === "en") return s;
    return s.replace(".", ",");
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function viaLabel(source) {
    if (source === "Booking") return t("rev.via_booking", "via Booking");
    return t("rev.via", "via Airbnb");
  }

  /** Numeric score badge: 5/5 (Airbnb) or 10/10 (Booking) */
  function scoreBadge(it) {
    var scale = it.scale || 5;
    var r = it.rating != null ? it.rating : scale === 10 ? 10 : 5;
    var shown = scale === 10 ? r : r;
    var max = scale === 10 ? 10 : 5;
    var label =
      scale === 10
        ? formatRating(shown, 0)
        : formatRating(shown, Number.isInteger(Number(shown)) ? 0 : 1);
    return (
      '<span class="review-card__score" aria-label="' +
      t("rev.score_aria", "Nota") +
      " " +
      label +
      "/" +
      max +
      '">' +
      label +
      "<small>/" +
      max +
      "</small></span>"
    );
  }

  function cardHtml(it) {
    var text = reviewText(it);
    var name = escapeHtml(it.name || t("rev.guest", "Hóspede"));
    var country = (it.country || "").toUpperCase();
    var loc = escapeHtml(reviewLocation(it));
    var date = escapeHtml(it.date || "");
    var source = it.source || "Airbnb";
    var scale = it.scale || 5;
    var r = it.rating != null ? it.rating : scale === 10 ? 10 : 5;

    var metaBits = [];
    if (loc) metaBits.push(loc);
    if (date) metaBits.push(date);

    return (
      '<article class="review-card" data-source="' +
      escapeHtml(source) +
      '">' +
      '<div class="review-card__top">' +
      scoreBadge(it) +
      '<div class="review-card__stars" aria-hidden="true">' +
      stars(r, scale) +
      "</div>" +
      "</div>" +
      '<blockquote class="review-card__text">“' +
      escapeHtml(text) +
      '”</blockquote>' +
      '<footer class="review-card__meta">' +
      '<div class="review-card__guest">' +
      flagImg(country, loc || country) +
      "<strong>" +
      name +
      "</strong>" +
      "</div>" +
      (metaBits.length
        ? '<span class="review-card__sub">' + metaBits.join(" · ") + "</span>"
        : "") +
      '<span class="review-card__source">' +
      viaLabel(source) +
      "</span>" +
      "</footer></article>"
    );
  }

  function getPerView() {
    var w = window.innerWidth || 1024;
    if (w < 700) return 1;
    if (w < 1024) return 2;
    return 3;
  }

  function bindCarousel(root, track, prevBtn, nextBtn, dotsEl, n) {
    var index = 0;
    var timer = null;
    var perView = getPerView();

    function maxIndex() {
      return Math.max(0, n - perView);
    }

    function applySlideWidth() {
      /* CSS [data-per-view] sets slide flex — no per-element style writes */
      perView = getPerView();
      root.setAttribute("data-per-view", String(perView));
    }

    function rebuildDots() {
      if (!dotsEl) return;
      dotsEl.innerHTML = "";
      dotsEl.setAttribute("role", "group");
      dotsEl.setAttribute(
        "aria-label",
        t("rev.dots", "Páginas das avaliações")
      );
      var pages = maxIndex() + 1;
      for (var d = 0; d < pages; d++) {
        (function (di) {
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className =
            "reviews-carousel__dot" + (di === index ? " is-active" : "");
          btn.setAttribute(
            "aria-label",
            t("rev.slide", "Avaliação") + " " + (di + 1)
          );
          /* aria-current (not aria-selected) — valid on plain buttons */
          if (di === index) btn.setAttribute("aria-current", "true");
          else btn.removeAttribute("aria-current");
          btn.addEventListener("click", function () {
            go(di);
            restart();
          });
          dotsEl.appendChild(btn);
        })(d);
      }
    }

    function go(i) {
      var max = maxIndex();
      index = Math.max(0, Math.min(i, max));
      var pct = (100 / perView) * index;
      /* Single write in rAF to reduce layout thrash with concurrent DOM updates */
      var idx = index;
      requestAnimationFrame(function () {
        track.style.transform = "translateX(-" + pct + "%)";
        if (dotsEl) {
          dotsEl.querySelectorAll("button").forEach(function (b, bi) {
            var active = bi === idx;
            b.classList.toggle("is-active", active);
            if (active) b.setAttribute("aria-current", "true");
            else b.removeAttribute("aria-current");
          });
        }
        if (prevBtn) prevBtn.disabled = idx <= 0;
        if (nextBtn) nextBtn.disabled = idx >= max;
      });
    }

    function next() {
      var max = maxIndex();
      if (index >= max) go(0);
      else go(index + 1);
    }
    function prev() {
      var max = maxIndex();
      if (index <= 0) go(max);
      else go(index - 1);
    }

    if (prevBtn) prevBtn.addEventListener("click", prev);
    if (nextBtn) nextBtn.addEventListener("click", next);

    var startX = 0;
    var dx = 0;
    track.addEventListener(
      "touchstart",
      function (e) {
        startX = e.changedTouches[0].screenX;
        dx = 0;
        stop();
      },
      { passive: true }
    );
    track.addEventListener(
      "touchmove",
      function (e) {
        dx = e.changedTouches[0].screenX - startX;
      },
      { passive: true }
    );
    track.addEventListener(
      "touchend",
      function () {
        if (Math.abs(dx) > 50) {
          if (dx < 0) next();
          else prev();
        }
        restart();
      },
      { passive: true }
    );

    function stop() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    }
    function restart() {
      stop();
      if (maxIndex() > 0) {
        timer = setInterval(next, 7000);
      }
    }

    var resizeTimer = null;
    function onResize() {
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        var old = perView;
        applySlideWidth();
        if (old !== perView) {
          rebuildDots();
        }
        go(Math.min(index, maxIndex()));
      }, 120);
    }

    window.addEventListener("resize", onResize);
    root.addEventListener("mouseenter", stop);
    root.addEventListener("mouseleave", restart);
    root.addEventListener("focusin", stop);
    root.addEventListener("focusout", restart);

    applySlideWidth();
    rebuildDots();
    go(0);
    restart();
  }

  function render(root) {
    var items = Array.isArray(data.items)
      ? data.items.filter(function (it) {
          return it && (it.text || it.textEn || it.textEs || it.textKey);
        })
      : [];
    items = sortInternationalFirst(items);
    var url =
      data.listingUrl ||
      (window.SITE_CONFIG &&
        window.SITE_CONFIG.listings &&
        window.SITE_CONFIG.listings.airbnb) ||
      "#";
    var bookingUrl =
      data.bookingUrl ||
      (window.SITE_CONFIG &&
        window.SITE_CONFIG.listings &&
        window.SITE_CONFIG.listings.booking) ||
      "#";

    var hl = (data.highlights || [])
      .map(function (h) {
        var label = h.label || "";
        if (h.key) label = t(h.key, label);
        return '<li class="reviews-hl__item">' + label + "</li>";
      })
      .join("");

    var badges = "";
    if (data.guestFavorite) {
      badges +=
        '<span class="reviews-badge">' +
        t("rev.guest_favorite", "Preferido dos hóspedes") +
        "</span>";
    }
    if (data.superhost) {
      badges +=
        '<span class="reviews-badge reviews-badge--soft">' +
        t("rev.superhost", "Superhost") +
        "</span>";
    }

    var slides = items
      .map(function (it) {
        return (
          '<div class="reviews-carousel__slide" role="group" aria-roledescription="slide">' +
          cardHtml(it) +
          "</div>"
        );
      })
      .join("");

    var overall = formatRating(data.rating, 2);

    var carousel =
      items.length === 0
        ? '<p class="reviews-empty">' +
          t(
            "rev.empty",
            "Leia as avaliações completas de hóspedes reais no Airbnb."
          ) +
          "</p>"
        : '<div class="reviews-carousel" data-reviews-carousel>' +
          '<div class="reviews-carousel__viewport">' +
          '<div class="reviews-carousel__track">' +
          slides +
          "</div></div>" +
          '<div class="reviews-carousel__controls">' +
          '<button type="button" class="reviews-carousel__btn" data-reviews-prev aria-label="' +
          t("rev.prev", "Anterior") +
          '">‹</button>' +
          '<div class="reviews-carousel__dots" data-reviews-dots></div>' +
          '<button type="button" class="reviews-carousel__btn" data-reviews-next aria-label="' +
          t("rev.next", "Próxima") +
          '">›</button>' +
          "</div></div>";

    root.innerHTML =
      '<div class="reviews-summary">' +
      '<div class="reviews-summary__score">' +
      '<p class="reviews-summary__rating" aria-label="' +
      t("rev.rating_aria", "Nota média") +
      " " +
      overall +
      '/5">' +
      overall +
      "<small class=\"reviews-summary__of\">/5</small>" +
      "</p>" +
      '<p class="reviews-summary__stars" aria-hidden="true">' +
      stars(5) +
      "</p>" +
      '<p class="reviews-summary__count">' +
      t("rev.based_on", "Baseado em") +
      " <strong>" +
      (data.count || items.length) +
      "</strong> " +
      t("rev.reviews_n", "avaliações no Airbnb") +
      "</p>" +
      '<div class="reviews-summary__badges">' +
      badges +
      "</div>" +
      "</div>" +
      '<div class="reviews-summary__main">' +
      (hl
        ? '<div class="reviews-hl"><p class="reviews-hl__label">' +
          t("rev.highlights", "O que os hóspedes destacam") +
          '</p><ul class="reviews-hl__list">' +
          hl +
          "</ul></div>"
        : "") +
      '<p class="reviews-cta">' +
      '<a class="btn-secondary reviews-cta__airbnb" href="' +
      url +
      '" target="_blank" rel="noopener">' +
      t("rev.read_all", "Ver no Airbnb") +
      "</a>" +
      '<a class="btn-secondary reviews-cta__booking" href="' +
      bookingUrl +
      '" target="_blank" rel="noopener">' +
      t("rev.read_booking", "Ver no Booking") +
      "</a></p>" +
      "</div>" +
      "</div>" +
      carousel;

    var car = root.querySelector("[data-reviews-carousel]");
    if (car && items.length) {
      bindCarousel(
        car,
        car.querySelector(".reviews-carousel__track"),
        car.querySelector("[data-reviews-prev]"),
        car.querySelector("[data-reviews-next]"),
        car.querySelector("[data-reviews-dots]"),
        items.length
      );
    }
  }

  function mountAll() {
    document.querySelectorAll("[data-reviews-root]").forEach(render);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAll);
  } else {
    mountAll();
  }
  document.addEventListener("mdl:langchange", mountAll);
})();
