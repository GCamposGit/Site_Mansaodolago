/**
 * Prefer regular WhatsApp (com.whatsapp) over WhatsApp Business (com.whatsapp.w4b).
 * Safe standalone: works on private /p/ pages that do not load analytics.js.
 * Public pages also use the same logic in analytics.js / site.js.
 */
(function () {
  "use strict";

  function preferConsumerWhatsApp(href) {
    if (!href) return href;
    var lower = String(href).toLowerCase();
    var isWa =
      lower.indexOf("wa.me") !== -1 ||
      lower.indexOf("api.whatsapp.com") !== -1 ||
      lower.indexOf("web.whatsapp.com") !== -1 ||
      lower.indexOf("whatsapp:") === 0;
    if (!isWa) return href;

    var phone = "";
    var text = "";
    try {
      if (lower.indexOf("whatsapp:") === 0) {
        var q = href.split("?")[1] || "";
        q.split("&").forEach(function (pair) {
          var kv = pair.split("=");
          var k = decodeURIComponent(kv[0] || "");
          var v = decodeURIComponent((kv[1] || "").replace(/\+/g, " "));
          if (k === "phone") phone = v;
          if (k === "text") text = v;
        });
      } else {
        var u = new URL(href, window.location.href);
        if (u.hostname.indexOf("wa.me") !== -1) {
          phone = (u.pathname || "").replace(/\//g, "");
          text = u.searchParams.get("text") || "";
        } else {
          phone = u.searchParams.get("phone") || "";
          text = u.searchParams.get("text") || "";
        }
      }
    } catch (e) {
      return href;
    }

    phone = String(phone || "").replace(/\D/g, "");
    if (!phone) return href;

    var web =
      "https://api.whatsapp.com/send?phone=" +
      encodeURIComponent(phone) +
      (text ? "&text=" + encodeURIComponent(text) : "");

    if (/Android/i.test(navigator.userAgent || "")) {
      return (
        "intent://send/?phone=" +
        phone +
        (text ? "&text=" + encodeURIComponent(text) : "") +
        "#Intent;scheme=whatsapp;package=com.whatsapp;S.browser_fallback_url=" +
        encodeURIComponent(web) +
        ";end"
      );
    }
    return web;
  }

  if (typeof window.MDL_preferConsumerWhatsApp !== "function") {
    window.MDL_preferConsumerWhatsApp = preferConsumerWhatsApp;
  }

  document.addEventListener(
    "click",
    function (e) {
      if (e.defaultPrevented) return;
      if (e.button !== 0) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      /* analytics.js already owns public-page interception when present */
      if (window.MDL_track) return;

      var a = e.target.closest && e.target.closest("a[href]");
      if (!a) return;
      var href = a.getAttribute("href") || "";
      var next = preferConsumerWhatsApp(href);
      if (!next || next === href) return;

      e.preventDefault();
      if (String(next).indexOf("intent:") === 0) {
        window.location.href = next;
        return;
      }
      var target = (a.getAttribute("target") || "").toLowerCase();
      if (target === "_blank") {
        var win = window.open(next, "_blank", "noopener,noreferrer");
        if (!win) window.location.href = next;
      } else {
        window.location.href = next;
      }
    },
    true
  );
})();
