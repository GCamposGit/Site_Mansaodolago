/**
 * Mansão do Lago — i18n runtime (PT / EN / ES)
 * Load after i18n-data.js. Prefer before site.js if WhatsApp messages depend on lang.
 *
 * Usage in HTML:
 *   data-i18n="key"           → textContent
 *   data-i18n-html="key"      → innerHTML
 *   data-i18n-placeholder="key"
 *   data-i18n-aria="key"      → aria-label
 *   data-i18n-alt="key"       → img alt
 *   data-i18n-title="key"     → title attribute
 *   data-i18n-wa="wa.plan"    → WhatsApp ?text= message (href updated)
 *   data-page="home"          → on <html> for meta titles
 *
 * URL: ?lang=en | en | es | pt   or localStorage mdl_lang
 */
(function () {
  "use strict";

  var SUPPORTED = ["pt", "en", "es"];
  var STORAGE = "mdl_lang";

  function getStrings() {
    return window.I18N_STRINGS || {};
  }

  function detect() {
    var params = new URLSearchParams(window.location.search);
    var q = (params.get("lang") || "").toLowerCase();
    if (SUPPORTED.indexOf(q) !== -1) return q;
    try {
      var stored = localStorage.getItem(STORAGE);
      if (SUPPORTED.indexOf(stored) !== -1) return stored;
    } catch (e) {}
    var nav = (navigator.language || "pt").toLowerCase();
    if (nav.indexOf("es") === 0) return "es";
    if (nav.indexOf("en") === 0) return "en";
    return "pt";
  }

  function t(key, lang) {
    lang = lang || window.I18N.lang || "pt";
    var strings = getStrings();
    var pack = strings[lang] || strings.pt || {};
    if (pack[key] != null) return pack[key];
    if (strings.pt && strings.pt[key] != null) return strings.pt[key];
    return null;
  }

  function setHtmlLang(lang) {
    var map = { pt: "pt-BR", en: "en", es: "es" };
    document.documentElement.lang = map[lang] || "pt-BR";
    document.documentElement.setAttribute("data-lang", lang);
  }

  function applyMeta(lang) {
    var page = document.documentElement.getAttribute("data-page") || "";
    if (!page) return;
    var title = t("meta." + page + ".title", lang);
    var desc = t("meta." + page + ".desc", lang);
    if (title) {
      document.title = title;
      var ogt = document.querySelector('meta[property="og:title"]');
      if (ogt) ogt.setAttribute("content", title);
    }
    if (desc) {
      var md = document.querySelector('meta[name="description"]');
      if (md) md.setAttribute("content", desc);
      var ogd = document.querySelector('meta[property="og:description"]');
      if (ogd) ogd.setAttribute("content", desc);
    }
  }

  function applyWaHref(el, key, lang) {
    var msg = t(key, lang);
    if (!msg) return;
    var href = el.getAttribute("href") || "";
    var base = href.split("?")[0];
    if (base.indexOf("wa.me") === -1 && href.indexOf("whatsapp") === -1) {
      base = "https://wa.me/5511988228936";
    }
    el.setAttribute("href", base + "?text=" + encodeURIComponent(msg));
  }

  function apply(lang) {
    lang = SUPPORTED.indexOf(lang) !== -1 ? lang : "pt";
    window.I18N.lang = lang;
    try {
      localStorage.setItem(STORAGE, lang);
    } catch (e) {}
    setHtmlLang(lang);

    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var key = el.getAttribute("data-i18n");
      var val = t(key, lang);
      if (val == null) return;
      el.textContent = val;
    });

    document.querySelectorAll("[data-i18n-html]").forEach(function (el) {
      var key = el.getAttribute("data-i18n-html");
      var val = t(key, lang);
      if (val == null) return;
      el.innerHTML = val;
    });

    document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
      var key = el.getAttribute("data-i18n-placeholder");
      var val = t(key, lang);
      if (val == null) return;
      el.setAttribute("placeholder", val);
    });

    document.querySelectorAll("[data-i18n-aria]").forEach(function (el) {
      var key = el.getAttribute("data-i18n-aria");
      var val = t(key, lang);
      if (val == null) return;
      el.setAttribute("aria-label", val);
    });

    document.querySelectorAll("[data-i18n-alt]").forEach(function (el) {
      var key = el.getAttribute("data-i18n-alt");
      var val = t(key, lang);
      if (val == null) return;
      el.setAttribute("alt", val);
    });

    document.querySelectorAll("[data-i18n-title]").forEach(function (el) {
      var key = el.getAttribute("data-i18n-title");
      var val = t(key, lang);
      if (val == null) return;
      el.setAttribute("title", val);
    });


    document.querySelectorAll("[data-i18n-caption]").forEach(function (el) {
      var key = el.getAttribute("data-i18n-caption");
      var val = t(key, lang);
      if (val == null) return;
      el.setAttribute("data-caption", val);
      var img = el.tagName === "IMG" ? el : el.querySelector("img");
      if (img && !img.getAttribute("data-i18n-alt")) {
        img.setAttribute("alt", val);
      }
    });

    document.querySelectorAll("[data-i18n-wa]").forEach(function (el) {
      applyWaHref(el, el.getAttribute("data-i18n-wa"), lang);
    });

    // Option labels in selects
    document.querySelectorAll("option[data-i18n]").forEach(function (el) {
      var key = el.getAttribute("data-i18n");
      var val = t(key, lang);
      if (val != null) el.textContent = val;
    });

    applyMeta(lang);
    syncSwitcher(lang);

    document.dispatchEvent(
      new CustomEvent("mdl:langchange", { detail: { lang: lang } })
    );
  }

  function syncSwitcher(lang) {
    document.querySelectorAll(".lang-switch [data-set-lang]").forEach(function (btn) {
      var active = btn.getAttribute("data-set-lang") === lang;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function injectSwitchers() {
    var html =
      '<div class="lang-switch" role="group" aria-label="Language">' +
      '<button type="button" class="lang-switch__btn" data-set-lang="pt" title="Português">PT</button>' +
      '<button type="button" class="lang-switch__btn" data-set-lang="en" title="English">EN</button>' +
      '<button type="button" class="lang-switch__btn" data-set-lang="es" title="Español">ES</button>' +
      "</div>";

    var brand = document.querySelector(".site-sidebar__brand");
    if (brand && !brand.querySelector(".lang-switch")) {
      brand.insertAdjacentHTML("beforeend", html);
    }
    var headerRight = document.querySelector(".site-header__right");
    if (headerRight && !headerRight.querySelector(".lang-switch")) {
      var toggle = headerRight.querySelector(".menu-toggle");
      if (toggle) {
        toggle.insertAdjacentHTML("beforebegin", html);
      } else {
        headerRight.insertAdjacentHTML("beforeend", html);
      }
    }
    var privateActions = document.querySelector(".private-header__actions");
    if (privateActions && !privateActions.querySelector(".lang-switch")) {
      privateActions.insertAdjacentHTML("afterbegin", html);
    }

    document.querySelectorAll("[data-set-lang]").forEach(function (btn) {
      if (btn.getAttribute("data-lang-bound") === "1") return;
      btn.setAttribute("data-lang-bound", "1");
      btn.addEventListener("click", function () {
        var lang = btn.getAttribute("data-set-lang");
        var url = new URL(window.location.href);
        url.searchParams.set("lang", lang);
        window.history.replaceState({}, "", url.toString());
        apply(lang);
      });
    });
  }

  window.I18N = {
    lang: "pt",
    t: t,
    apply: apply,
    detect: detect,
    supported: SUPPORTED,
  };

  function boot() {
    injectSwitchers();
    apply(detect());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
