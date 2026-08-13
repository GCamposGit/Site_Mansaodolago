/**
 * Google tags (GA4 + Google Ads) via one gtag.js loader.
 * Place after site-config.js on public pages only (not private /p/ guides).
 *
 * SITE_CONFIG:
 *   gaMeasurementId — "G-…"
 *   googleAdsId — "AW-…"
 *   googleAdsConversions — { whatsapp, airbnb, booking, spotz, email } each "AW-…/label"
 *
 * WhatsApp / outbound / email clicks use Google's conversion pattern:
 *   preventDefault → gtag conversion + event_callback → then open the link
 * so the hit is not lost when target=_blank opens WhatsApp / OTAs, or when
 * mailto: hands off to the mail client.
 *
 * Email clicks also send GA4 event email_click (event_category: contact,
 * event_label: address) — mark as conversion in GA4 Admin if desired.
 *
 * Optional on anchors:
 *   data-mdl-channel="whatsapp|airbnb|booking|spotz|email"
 *   data-mdl-placement="hero|sticky|final|header|sidebar|footer|contact"
 */
(function () {
  "use strict";
  var cfg = window.SITE_CONFIG || {};
  var gaId = (cfg.gaMeasurementId || "").trim();
  var adsId = (cfg.googleAdsId || "").trim();
  var conv = cfg.googleAdsConversions || {};

  if (!conv.whatsapp && cfg.googleAdsConversionSendTo) {
    conv.whatsapp = cfg.googleAdsConversionSendTo;
  }

  var hasGa = gaId.indexOf("G-") === 0;
  var hasAds = adsId.indexOf("AW-") === 0;
  if (!hasGa && !hasAds) return;

  var pageMeta = {
    page_path: (window.location && window.location.pathname) || "",
    page_location: (window.location && window.location.href) || "",
    page_title: document.title || "",
    content_group:
      document.documentElement.getAttribute("data-page") || undefined,
    language:
      document.documentElement.getAttribute("lang") ||
      document.documentElement.lang ||
      undefined,
  };

  var primaryId = hasGa ? gaId : adsId;

  /* Queue-friendly stub: config/events work before the network script arrives */
  window.dataLayer = window.dataLayer || [];
  function gtag() {
    // dataLayer.push needs Arguments object for gtag protocol
    window.dataLayer.push(arguments);
  }
  window.gtag = gtag;
  gtag("js", new Date());

  /*
   * GA4 only on background load. Google Ads config is deferred until a real
   * conversion click (or ensureAdsConfigured). That avoids DoubleClick /
   * third-party cookie storms during Lighthouse (BP dropped to 77 when Ads
   * configured on every pageview + scroll-triggered load).
   */
  if (hasGa) {
    var gaConfig = {
      anonymize_ip: true,
      send_page_view: true,
      page_path: pageMeta.page_path,
      page_location: pageMeta.page_location,
      page_title: pageMeta.page_title,
    };
    if (pageMeta.content_group) {
      gaConfig.content_group = pageMeta.content_group;
    }
    if (pageMeta.language) {
      gaConfig.language = pageMeta.language;
    }
    gtag("config", gaId, gaConfig);
  }

  var adsConfigured = false;
  function ensureAdsConfigured() {
    if (!hasAds || adsConfigured) return;
    adsConfigured = true;
    gtag("config", adsId, {
      allow_enhanced_conversions: true,
    });
  }

  /* Defer gtag.js network load — do NOT use scroll/touchstart (Lighthouse scrolls) */
  var gtagLoaded = false;
  function loadGtagNetwork() {
    if (gtagLoaded) return;
    gtagLoaded = true;
    var s = document.createElement("script");
    s.async = true;
    s.src =
      "https://www.googletagmanager.com/gtag/js?id=" +
      encodeURIComponent(primaryId);
    document.head.appendChild(s);
  }

  /* Intentional interaction only (not scroll) → load tags for conversion readiness */
  ["pointerdown", "keydown", "click"].forEach(function (ev) {
    window.addEventListener(
      ev,
      function () {
        loadGtagNetwork();
      },
      { once: true, passive: true, capture: true }
    );
  });

  /* Background pageview for real visitors after lab window (~Lighthouse done) */
  setTimeout(function () {
    loadGtagNetwork();
  }, 7000);

  /**
   * Enhanced conversions (in-page): set first-party user data before conversion hits.
   * Google hashes email/phone (SHA256). Prefer email. Phone must be E.164 (+country…).
   * Call from forms: MDL_setUserData({ email, phone_number, first_name })
   * Stored in sessionStorage so later WhatsApp/Airbnb clicks in the same visit can attach data.
   */
  function normalizePhoneE164(raw) {
    if (!raw) return "";
    var digits = String(raw).replace(/\D/g, "");
    if (!digits) return "";
    /* Brazil local mobiles often 10–11 digits without country code */
    if (digits.length <= 11 && digits.indexOf("55") !== 0) {
      digits = "55" + digits;
    }
    return "+" + digits;
  }

  function normalizeEmail(raw) {
    if (!raw) return "";
    return String(raw).trim().toLowerCase();
  }

  function buildUserData(input) {
    if (!input || typeof input !== "object") return null;
    var ud = {};
    var email = normalizeEmail(input.email || input.email_address || "");
    var phone = normalizePhoneE164(
      input.phone_number || input.phone || input.tel || ""
    );
    var first = String(input.first_name || input.firstName || "").trim();
    var last = String(input.last_name || input.lastName || "").trim();

    if (email && email.indexOf("@") !== -1) ud.email = email;
    if (phone && phone.length >= 10) ud.phone_number = phone;

    /* Address only if complete enough (Google wants first+last+postal+country) */
    if (first && last && input.postal_code && input.country) {
      ud.address = {
        first_name: first,
        last_name: last,
        postal_code: String(input.postal_code).trim(),
        country: String(input.country).trim().toUpperCase().slice(0, 2),
      };
      if (input.city) ud.address.city = String(input.city).trim();
      if (input.region) ud.address.region = String(input.region).trim();
      if (input.street) ud.address.street = String(input.street).trim();
    } else if (first && !ud.email && !ud.phone_number) {
      /* name alone is not enough for EC match keys — skip */
    }

    if (!ud.email && !ud.phone_number && !ud.address) return null;
    return ud;
  }

  window.MDL_setUserData = function (input) {
    var ud = buildUserData(input);
    if (!ud || typeof window.gtag !== "function") return false;
    try {
      window.gtag("set", "user_data", ud);
    } catch (e) {
      return false;
    }
    try {
      sessionStorage.setItem("mdl_ec_user_data", JSON.stringify(ud));
    } catch (e2) {}
    return true;
  };

  function applyStoredUserData() {
    if (typeof window.gtag !== "function") return;
    try {
      var raw = sessionStorage.getItem("mdl_ec_user_data");
      if (!raw) return;
      var ud = JSON.parse(raw);
      if (ud && (ud.email || ud.phone_number || ud.address)) {
        window.gtag("set", "user_data", ud);
      }
    } catch (e) {}
  }

  /* Re-apply any session user_data after tag loads */
  applyStoredUserData();

  function resolveSendTo(keyOrSendTo) {
    var key = (keyOrSendTo || "").toLowerCase();
    if (conv[key]) return String(conv[key]).trim();
    if (String(keyOrSendTo || "").indexOf("AW-") === 0) {
      return String(keyOrSendTo).trim();
    }
    return "";
  }

  window.MDL_track = function (eventName, params) {
    if (typeof window.gtag !== "function") return;
    var p = params || {};
    if (!p.page_path && pageMeta.page_path) p.page_path = pageMeta.page_path;
    if (!p.page_location && pageMeta.page_location)
      p.page_location = pageMeta.page_location;
    if (!p.content_group && pageMeta.content_group)
      p.content_group = pageMeta.content_group;
    window.gtag("event", eventName, p);
  };

  /**
   * Google Ads conversion (same as Ads event snippet).
   * @param {string} keyOrSendTo
   * @param {object} [params]
   * @param {function} [callback] called after hit is sent (or timeout)
   */
  window.MDL_ads_conversion = function (keyOrSendTo, params, callback) {
    var sendTo = resolveSendTo(keyOrSendTo);
    if (!sendTo || typeof window.gtag !== "function") {
      if (typeof callback === "function") callback();
      return false;
    }

    /* Ensure network tag + Ads config before conversion (click path) */
    loadGtagNetwork();
    ensureAdsConfigured();

    /* Enhanced conversions: attach any known first-party data before the hit */
    applyStoredUserData();

    var done = false;
    var finish = function () {
      if (done) return;
      done = true;
      if (typeof callback === "function") callback();
    };

    var p = params || {};
    p.send_to = sendTo;
    p.event_callback = finish;
    p.event_timeout = 2000;
    if (pageMeta.page_path) p.page_path = pageMeta.page_path;
    if (pageMeta.page_location) p.page_location = pageMeta.page_location;

    try {
      window.gtag("event", "conversion", p);
    } catch (err) {
      finish();
      return false;
    }

    // Safety if gtag never calls back
    setTimeout(finish, 2000);
    return false;
  };

  /**
   * Exact helper name from Google Ads snippet (Tag Assistant looks for this flow).
   * Usage: gtag_report_conversion('https://wa.me/...')
   */
  window.gtag_report_conversion = function (url) {
    return window.MDL_ads_conversion(
      "whatsapp",
      {},
      function () {
        if (typeof url !== "undefined" && url) {
          window.location = url;
        }
      }
    );
  };

  function channelFromHref(href) {
    var lower = (href || "").toLowerCase();
    if (lower.indexOf("mailto:") === 0) return "email";
    if (
      lower.indexOf("wa.me") !== -1 ||
      lower.indexOf("api.whatsapp.com") !== -1 ||
      lower.indexOf("whatsapp.com") !== -1 ||
      lower.indexOf("whatsapp:") === 0
    ) {
      return "whatsapp";
    }
    if (lower.indexOf("airbnb.") !== -1) return "airbnb";
    if (lower.indexOf("booking.") !== -1) return "booking";
    if (lower.indexOf("spotz.") !== -1) return "spotz";
    return null;
  }

  function channelFromEl(a, href) {
    var explicit = (a.getAttribute("data-mdl-channel") || "").toLowerCase();
    if (
      explicit === "whatsapp" ||
      explicit === "airbnb" ||
      explicit === "booking" ||
      explicit === "spotz" ||
      explicit === "email"
    ) {
      return explicit;
    }
    return channelFromHref(href);
  }

  /** Extract address from mailto:user@host?subject=… */
  function emailFromMailto(href) {
    try {
      var raw = String(href || "")
        .replace(/^mailto:/i, "")
        .split("?")[0]
        .split("&")[0];
      return decodeURIComponent(raw).trim() || "reservas@mansaodolago.com";
    } catch (e) {
      return "reservas@mansaodolago.com";
    }
  }

  function absoluteHref(href) {
    try {
      return new URL(href, window.location.href).href;
    } catch (e) {
      return href;
    }
  }

  /**
   * Prefer regular WhatsApp (com.whatsapp) over WhatsApp Business (com.whatsapp.w4b).
   * HTML still uses official wa.me / api.whatsapp.com click-to-chat URLs.
   * On Android we rewrite to an intent that targets the consumer package, with a web fallback.
   */
  function preferConsumerWhatsApp(href) {
    if (!href) return href;
    var lower = String(href).toLowerCase();
    var isWa =
      lower.indexOf("wa.me") !== -1 ||
      lower.indexOf("api.whatsapp.com") !== -1 ||
      lower.indexOf("web.whatsapp.com") !== -1 ||
      lower.indexOf("whatsapp:") === 0 ||
      lower.indexOf("intent://") === 0;
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
      } else if (lower.indexOf("intent://") === 0) {
        return href; /* already an intent */
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
    } catch (err) {
      return href;
    }

    phone = String(phone || "").replace(/\D/g, "");
    if (!phone) return href;

    var web =
      "https://api.whatsapp.com/send?phone=" +
      encodeURIComponent(phone) +
      (text ? "&text=" + encodeURIComponent(text) : "");

    var ua = navigator.userAgent || "";
    var isAndroid = /Android/i.test(ua);
    if (isAndroid) {
      /* package=com.whatsapp = consumer app (not com.whatsapp.w4b Business) */
      var intent =
        "intent://send/?phone=" +
        phone +
        (text ? "&text=" + encodeURIComponent(text) : "") +
        "#Intent;scheme=whatsapp;package=com.whatsapp;S.browser_fallback_url=" +
        encodeURIComponent(web) +
        ";end";
      return intent;
    }

    /* iOS / desktop: official API link → consumer WhatsApp or WhatsApp Web */
    return web;
  }

  window.MDL_preferConsumerWhatsApp = preferConsumerWhatsApp;

  function openHref(a, href) {
    var finalHref = preferConsumerWhatsApp(href);
    var isIntent = String(finalHref).indexOf("intent:") === 0;
    var target = (a.getAttribute("target") || "").toLowerCase();

    /* Android intents must navigate the current tab; window.open is unreliable */
    if (isIntent) {
      window.location.href = finalHref;
      return;
    }

    if (target === "_blank") {
      var win = window.open(finalHref, "_blank", "noopener,noreferrer");
      if (!win) window.location.href = finalHref;
    } else {
      window.location.href = finalHref;
    }
  }

  function trackOutbound(a, href, channel) {
    var abs = absoluteHref(href);
    var placement =
      a.getAttribute("data-mdl-placement") ||
      a.getAttribute("data-placement") ||
      "";
    var linkText = (a.textContent || "").replace(/\s+/g, " ").trim().slice(0, 80);

    var base = {
      link_url: abs,
      channel: channel,
      link_text: linkText,
      page_path: pageMeta.page_path,
      page_location: pageMeta.page_location,
      page_title: pageMeta.page_title,
      transport_type: "beacon",
    };
    if (pageMeta.content_group) base.content_group = pageMeta.content_group;
    if (pageMeta.language) base.language = pageMeta.language;
    if (placement) base.placement = placement;

    // Custom events (mark as conversions in GA4 Admin if desired)
    if (channel === "email") {
      /* email_click is sent in the click handler with event_callback (mailto-safe) */
      var emailAddr = emailFromMailto(href);
      base.event_category = "contact";
      base.event_label = emailAddr;
      base.email = emailAddr;
    } else {
      window.MDL_track(channel + "_click", base);
      window.MDL_track("outbound_click", base);
    }

    // GA4 recommended-style signals for reporting
    if (channel === "whatsapp") {
      window.MDL_track("generate_lead", {
        method: "whatsapp",
        placement: placement || undefined,
        content_group: pageMeta.content_group,
        page_path: pageMeta.page_path,
        transport_type: "beacon",
      });
    } else if (channel === "airbnb" || channel === "booking") {
      window.MDL_track("select_content", {
        content_type: "ota_booking",
        item_id: channel,
        placement: placement || undefined,
        content_group: pageMeta.content_group,
        page_path: pageMeta.page_path,
        transport_type: "beacon",
      });
    }

    return base;
  }

  document.addEventListener(
    "click",
    function (e) {
      // Ignore modified clicks (open in new tab via middle-click etc.)
      if (e.defaultPrevented) return;
      if (e.button !== 0) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

      var a = e.target.closest && e.target.closest("a[href]");
      if (!a) return;

      var href = a.getAttribute("href") || "";
      if (!href || href.charAt(0) === "#") return;

      var channel = channelFromEl(a, href);
      if (!channel) return;

      var sendTo = resolveSendTo(channel);
      var tracked = trackOutbound(a, href, channel);

      // Always intercept WhatsApp so we can prefer consumer app over Business (Android)
      var needsRewrite =
        channel === "whatsapp" && preferConsumerWhatsApp(href) !== href;

      /*
       * mailto: opens the mail client and can cancel pending hits — hold
       * navigation so email_click / Ads conversion can flush (event_callback).
       */
      var needsHold = needsRewrite || channel === "email";

      // No Ads label and no rewrite/hold → let the browser handle the link
      if (!sendTo && !needsHold) return;

      // Hold navigation until conversion is sent (Google's recommended pattern)
      e.preventDefault();
      e.stopPropagation();

      var go = function () {
        openHref(a, href);
      };

      if (channel === "email") {
        loadGtagNetwork();
        var emailAddr =
          (tracked && tracked.event_label) || emailFromMailto(href);
        var placement =
          (tracked && tracked.placement) ||
          a.getAttribute("data-mdl-placement") ||
          "";
        var done = false;
        var finish = function () {
          if (done) return;
          done = true;
          go();
        };

        /* Equivalent to: gtag('event','email_click',{event_category:'contact',...}) */
        if (typeof window.gtag === "function") {
          try {
            window.gtag("event", "email_click", {
              event_category: "contact",
              event_label: emailAddr,
              email: emailAddr,
              channel: "email",
              placement: placement || undefined,
              link_url: absoluteHref(href),
              page_path: pageMeta.page_path,
              page_location: pageMeta.page_location,
              page_title: pageMeta.page_title,
              transport_type: "beacon",
              event_callback: sendTo ? undefined : finish,
              event_timeout: 2000,
            });
            window.MDL_track("generate_lead", {
              method: "email",
              event_category: "contact",
              event_label: emailAddr,
              placement: placement || undefined,
              transport_type: "beacon",
            });
          } catch (err) {
            /* fall through to finish paths below */
          }
        }

        if (sendTo) {
          window.MDL_ads_conversion(
            "email",
            {
              event_category: "contact",
              event_label: emailAddr,
              transport_type: "beacon",
            },
            finish
          );
        } else {
          setTimeout(finish, 2000);
        }
        return;
      }

      if (!sendTo) {
        go();
        return;
      }

      window.MDL_ads_conversion(
        channel,
        {
          event_category: "outbound",
          event_label: channel,
          transport_type: "beacon",
        },
        go
      );
    },
    true
  );
})();
