/**
 * Mansão do Lago — shared site interactions
 * Mobile menu, header scroll, lightbox, forms, media catalog hydration
 *
 * Load after js/site-media.js when using data-media attributes.
 */
(function () {
  "use strict";

  var WA = "5511988228936";

  /**
   * Prefer regular WhatsApp over WhatsApp Business when both apps are installed.
   * Public pages usually load analytics.js (same helper). This covers forms + pages without ads tag.
   */
  function preferConsumerWhatsApp(href) {
    if (typeof window.MDL_preferConsumerWhatsApp === "function") {
      return window.MDL_preferConsumerWhatsApp(href);
    }
    if (!href) return href;
    var lower = String(href).toLowerCase();
    if (
      lower.indexOf("wa.me") === -1 &&
      lower.indexOf("api.whatsapp.com") === -1 &&
      lower.indexOf("whatsapp:") !== 0
    ) {
      return href;
    }
    try {
      var phone = "";
      var text = "";
      if (lower.indexOf("whatsapp:") === 0) {
        return href;
      }
      var u = new URL(href, window.location.href);
      if (u.hostname.indexOf("wa.me") !== -1) {
        phone = (u.pathname || "").replace(/\//g, "");
        text = u.searchParams.get("text") || "";
      } else {
        phone = u.searchParams.get("phone") || "";
        text = u.searchParams.get("text") || "";
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
    } catch (e) {
      return href;
    }
  }

  /* —— Media catalog helpers —— */
  function resolveMediaSrc(src) {
    if (!src) return src;
    var s = String(src);
    if (
      /^(https?:)?\/\//i.test(s) ||
      s.charAt(0) === "/" ||
      s.indexOf("data:") === 0
    ) {
      return s;
    }
    if (!/^(images|videos|fonts)\//i.test(s)) return s;
    /* Relative to the HTML file — never "/images/…".
       A leading slash breaks file:// and Live Server when the
       workspace root is not the site folder. */
    var p = (window.location.pathname || "").replace(/\\/g, "/");
    if (/\/(en|es|blog)\//i.test(p)) return "../" + s;
    return s;
  }

  function mediaGet(path) {
    if (!window.SITE_MEDIA || !path) return null;
    var parts = String(path).replace(/\[(\d+)\]/g, ".$1").split(".");
    var node = window.SITE_MEDIA;
    for (var i = 0; i < parts.length; i++) {
      if (node == null) return null;
      node = node[parts[i]];
    }
    return node;
  }

  function mediaItem(value) {
    if (!value) return null;
    if (typeof value === "string") return { src: value, alt: "" };
    return value;
  }

  /** Apply catalog to [data-media], [data-media-gallery], [data-media-video-list] */
  function hydrateMedia() {
    if (!window.SITE_MEDIA) return;

    document.querySelectorAll("[data-media]").forEach(function (el) {
      var item = mediaItem(mediaGet(el.getAttribute("data-media")));
      if (!item || !item.src) return;
      var src = resolveMediaSrc(item.src);
      if (el.tagName === "IMG") {
        el.src = src;
        if (item.alt) el.alt = item.alt;
      } else {
        var img = el.querySelector("img");
        if (img) {
          img.src = src;
          if (item.alt) img.alt = item.alt;
        } else {
          el.style.backgroundImage = 'url("' + src + '")';
        }
      }
      if (item.caption && el.getAttribute("data-caption") === null) {
        el.setAttribute("data-caption", item.caption);
      }
    });

    document.querySelectorAll("[data-media-gallery]").forEach(function (host) {
      var list = mediaGet(host.getAttribute("data-media-gallery"));
      if (!Array.isArray(list) || !list.length) return;
      var wideEvery = parseInt(host.getAttribute("data-wide-every") || "0", 10);
      host.innerHTML = "";
      list.forEach(function (raw, i) {
        var item = mediaItem(raw);
        if (!item || !item.src) return;
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className =
          "gallery-item" +
          (wideEvery && i % wideEvery === 0 ? " gallery-item--wide" : "");
        btn.setAttribute("data-lightbox", "");
        var cap = item.caption || item.alt || item.title || "";
        if (window.I18N && item.captionKey) {
          cap = window.I18N.t(item.captionKey) || cap;
        } else if (window.I18N && item.altKey) {
          cap = window.I18N.t(item.altKey) || cap;
        }
        btn.setAttribute("data-caption", cap);
        if (item.captionKey) btn.setAttribute("data-i18n-caption", item.captionKey);
        var img = document.createElement("img");
        img.src = resolveMediaSrc(item.src);
        var altText = item.alt || item.caption || "";
        if (window.I18N && item.altKey) altText = window.I18N.t(item.altKey) || altText;
        else if (window.I18N && item.captionKey)
          altText = window.I18N.t(item.captionKey) || altText;
        img.alt = altText;
        img.loading = "lazy";
        btn.appendChild(img);
        host.appendChild(btn);
      });
    });

    document.querySelectorAll("[data-media-spaces]").forEach(function (host) {
      var list = mediaGet(host.getAttribute("data-media-spaces"));
      if (!Array.isArray(list) || !list.length) return;
      host.innerHTML = "";
      list.forEach(function (raw) {
        var item = mediaItem(raw);
        if (!item || !item.src) return;
        var title = item.title || "";
        var text = item.text || "";
        if (window.I18N && item.titleKey) {
          title = window.I18N.t(item.titleKey) || title;
        }
        if (window.I18N && item.textKey) {
          text = window.I18N.t(item.textKey) || text;
        }
        var altText = item.alt || title || "";
        if (window.I18N && item.altKey) {
          altText = window.I18N.t(item.altKey) || altText;
        }
        var card = document.createElement("article");
        card.className = "media-card";
        card.innerHTML =
          '<img src="' +
          resolveMediaSrc(item.src) +
          '" alt="' +
          altText.replace(/"/g, "&quot;") +
          '" loading="lazy">' +
          '<div class="media-card__body">' +
          '<h3 class="text-xl mb-2 text-[#0D3B2E] heading-serif">' +
          title +
          "</h3>" +
          '<p class="text-sm text-[#5A5A5A]">' +
          text +
          "</p></div>";
        host.appendChild(card);
      });
    });

    document.querySelectorAll("[data-media-video-list]").forEach(function (host) {
      var list = mediaGet(host.getAttribute("data-media-video-list"));
      if (!Array.isArray(list) || !list.length) return;
      host.innerHTML = "";
      list.forEach(function (v) {
        if (!v) return;
        var wrap = document.createElement("div");
        wrap.className = "video-slot";
        var vTitle = v.title || "";
        if (window.I18N && v.titleKey) {
          vTitle = window.I18N.t(v.titleKey) || vTitle;
        }
        if (!vTitle) {
          vTitle = (window.I18N && window.I18N.t("common.video")) || "Video";
        }
        var vCap = v.caption || "";
        if (window.I18N && v.captionKey) {
          vCap = window.I18N.t(v.captionKey) || vCap;
        }
        if (!vCap) {
          vCap =
            (window.I18N && window.I18N.t("common.video_soon")) ||
            "Video coming soon";
        }
        if (v.src) {
          wrap.innerHTML =
            '<video controls playsinline preload="none" poster="' +
            resolveMediaSrc(v.poster || "") +
            '" src="' +
            resolveMediaSrc(v.src) +
            '"></video>' +
            '<p class="video-slot__caption">' +
            vTitle +
            (vCap ? " — " + vCap : "") +
            "</p>";
        } else {
          wrap.innerHTML =
            '<div class="video-slot__placeholder" style="background-image:url(\'' +
            resolveMediaSrc(v.poster || "") +
            "')\">" +
            '<span class="video-slot__badge">' +
            ((window.I18N && window.I18N.t("common.video_soon")) ||
              "Video coming soon") +
            "</span>" +
            "<strong>" +
            vTitle +
            "</strong>" +
            "<p>" +
            vCap +
            "</p></div>";
        }
        host.appendChild(wrap);
      });
    });
  }

  hydrateMedia();
  document.addEventListener("mdl:langchange", function () {
    hydrateMedia();
    var lbEl = document.querySelector(".lightbox");
    if (lbEl && window.I18N) {
      var closeB = lbEl.querySelector(".lightbox__close");
      var prevB = lbEl.querySelector(".lightbox__prev");
      var nextB = lbEl.querySelector(".lightbox__next");
      if (closeB) closeB.setAttribute("aria-label", window.I18N.t("ui.close") || "Close");
      if (prevB) prevB.setAttribute("aria-label", window.I18N.t("ui.prev") || "Previous");
      if (nextB) nextB.setAttribute("aria-label", window.I18N.t("ui.next") || "Next");
      lbEl.setAttribute("aria-label", window.I18N.t("ui.lightbox") || "Image view");
    }
  });

  /* —— Header scroll (mobile top bar) —— */
  var header = document.querySelector(".site-header");
  if (header) {
    var scrollQueued = false;
    var onScroll = function () {
      if (scrollQueued) return;
      scrollQueued = true;
      requestAnimationFrame(function () {
        scrollQueued = false;
        header.classList.toggle("is-scrolled", window.scrollY > 12);
      });
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* —— Sidebar navigation (desktop fixed / mobile drawer) —— */
  var sidebar = document.getElementById("site-sidebar");
  var backdrop = document.getElementById("sidebar-backdrop");
  var toggle = document.querySelector(".menu-toggle");
  var mobileNav = document.querySelector(".mobile-nav");
  var scrollLockY = 0;

  function isMobileNav() {
    return window.matchMedia("(max-width: 1023px)").matches;
  }

  function setSidebarOpen(open) {
    if (!sidebar) return;
    open = !!open;
    sidebar.classList.toggle("is-open", open);
    if (backdrop) backdrop.classList.toggle("is-visible", open);
    if (toggle) toggle.setAttribute("aria-expanded", open ? "true" : "false");
    document.body.classList.toggle("sidebar-open", open);

    // iOS Safari: lock/unlock body scroll (overflow:hidden alone fails)
    if (isMobileNav()) {
      if (open) {
        scrollLockY = window.pageYOffset || document.documentElement.scrollTop || 0;
        document.body.style.top = "-" + scrollLockY + "px";
      } else {
        document.body.style.top = "";
        window.scrollTo(0, scrollLockY);
      }
    } else {
      document.body.style.top = "";
    }
  }

  if (toggle && sidebar) {
    // iOS Safari: prefer pointerup when available; fall back to click.
    // Never bind both touchend + click (fires twice → open then immediate close).
    if (!toggle.getAttribute("type")) toggle.setAttribute("type", "button");
    toggle.setAttribute("aria-controls", "site-sidebar");

    var lastToggleAt = 0;
    function onMenuToggle(e) {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      var now = Date.now();
      if (now - lastToggleAt < 350) return; // debounce double-fire
      lastToggleAt = now;
      setSidebarOpen(!sidebar.classList.contains("is-open"));
    }

    // click = keyboard + most browsers; pointerup helps flaky iOS hit-testing.
    // Debounce prevents open→close when both fire.
    toggle.addEventListener("click", onMenuToggle);
    if (window.PointerEvent) {
      toggle.addEventListener("pointerup", function (e) {
        if (e.pointerType === "mouse" && e.button !== 0) return;
        onMenuToggle(e);
      });
    }
  }
  if (backdrop) {
    function closeMenu(e) {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      setSidebarOpen(false);
    }
    backdrop.addEventListener("click", closeMenu);
    if (window.PointerEvent) {
      backdrop.addEventListener("pointerup", closeMenu);
    }
  }
  if (sidebar) {
    sidebar.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        if (isMobileNav()) {
          setSidebarOpen(false);
        }
      });
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setSidebarOpen(false);
  });
  window.addEventListener(
    "resize",
    function () {
      if (!isMobileNav() && sidebar && sidebar.classList.contains("is-open")) {
        // Leaving mobile drawer mode: clear body lock without jump
        document.body.classList.remove("sidebar-open");
        document.body.style.top = "";
      }
    },
    { passive: true }
  );

  /* Legacy full-screen mobile nav (if present on old pages) */
  if (toggle && mobileNav && !sidebar) {
    toggle.addEventListener("click", function () {
      var open = !mobileNav.classList.contains("is-open");
      mobileNav.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      document.body.style.overflow = open ? "hidden" : "";
    });
    mobileNav.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        mobileNav.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
        document.body.style.overflow = "";
      });
    });
  }

  /* —— Booking form → WhatsApp (stay) —— */
  var bookingForm = document.getElementById("booking-form");
  if (bookingForm) {
    bookingForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var checkin = document.getElementById("checkin");
      var checkout = document.getElementById("checkout");
      var guests = document.getElementById("guests");
      var prefix =
        (window.I18N && window.I18N.t("wa.booking_prefix")) ||
        "Olá! Gostaria de verificar disponibilidade na Mansão do Lago.";
      var labelIn =
        (window.I18N && window.I18N.t("hosp.checkin")) || "Check-in";
      var labelOut =
        (window.I18N && window.I18N.t("hosp.checkout")) || "Check-out";
      var labelGuests =
        (window.I18N && window.I18N.t("hosp.guests")) || "Hóspedes";
      var msg =
        prefix +
        "\n" +
        labelIn +
        ": " +
        (checkin ? checkin.value : "") +
        "\n" +
        labelOut +
        ": " +
        (checkout ? checkout.value : "");
      if (guests && guests.value) {
        msg += "\n" + labelGuests + ": " + guests.value;
      }
      var est = window.MDL_lastPriceEstimate;
      if (est && est.total > 0 && window.MDL_formatPrice) {
        var labelPrice =
          (window.I18N && window.I18N.t("price.estimate")) || "Total";
        var labelNights =
          (window.I18N && window.I18N.t("price.nights")) || "noites";
        msg +=
          "\n" +
          labelPrice +
          ": " +
          window.MDL_formatPrice(est.total) +
          " (" +
          est.nights +
          " " +
          labelNights +
          ")";
      }
      openWhatsAppChat(WA, msg);
    });
  }

  function openWhatsAppChat(phone, msg) {
    var href =
      "https://api.whatsapp.com/send?phone=" +
      encodeURIComponent(String(phone).replace(/\D/g, "")) +
      (msg ? "&text=" + encodeURIComponent(msg) : "");
    var finalHref = preferConsumerWhatsApp(href);
    if (String(finalHref).indexOf("intent:") === 0) {
      window.location.href = finalHref;
      return;
    }
    var win = window.open(finalHref, "_blank", "noopener,noreferrer");
    if (!win) window.location.href = finalHref;
  }

  /* —— Event / filming request forms → WhatsApp —— */
  function bindUseForm(formId, prefixKey, fallbackPrefix) {
    var form = document.getElementById(formId);
    if (!form) return;
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var start = form.querySelector('[name="date_start"]');
      var end = form.querySelector('[name="date_end"]');
      var people = form.querySelector('[name="people"]');
      var notes = form.querySelector('[name="notes"]');
      var prefix =
        (window.I18N && window.I18N.t(prefixKey)) || fallbackPrefix;
      var labelIn =
        (window.I18N && window.I18N.t("av.date_start")) || "Data início";
      var labelOut =
        (window.I18N && window.I18N.t("av.date_end")) || "Data fim";
      var labelPeople =
        (window.I18N && window.I18N.t("av.people")) || "Pessoas / equipe";
      var msg =
        prefix +
        "\n" +
        labelIn +
        ": " +
        (start ? start.value : "") +
        "\n" +
        labelOut +
        ": " +
        (end ? end.value : "");
      if (people && people.value) {
        msg += "\n" + labelPeople + ": " + people.value;
      }
      /* Event form: include final on-site price when calculator ran */
      if (form.id === "event-request-form" && window.MDL_lastEventPrice) {
        var ep = window.MDL_lastEventPrice;
        var priceLabel =
          (window.I18N && window.I18N.t("ev.price.total")) || "Total do evento";
        var priceStr =
          typeof window.MDL_formatEventPrice === "function"
            ? window.MDL_formatEventPrice(ep.total)
            : "R$ " + Math.round(ep.total);
        msg += "\n" + priceLabel + ": " + priceStr;
        if (ep.days) {
          msg +=
            " (" +
            ep.days +
            " " +
            (ep.days === 1
              ? (window.I18N && window.I18N.t("ev.price.day_one")) || "dia"
              : (window.I18N && window.I18N.t("ev.price.days")) || "dias") +
            ")";
        }
      }
      if (notes && notes.value.trim()) {
        msg += "\n\n" + notes.value.trim();
      }
      openWhatsAppChat(WA, msg);
    });
  }
  bindUseForm(
    "event-request-form",
    "wa.event_request_prefix",
    "Olá! Gostaria de confirmar a reserva do evento na Mansão do Lago."
  );
  bindUseForm(
    "film-request-form",
    "wa.film_request_prefix",
    "Olá! Gostaria de solicitar datas para uma produção na Mansão do Lago."
  );

  /* —— Contact form → WhatsApp (+ enhanced conversions user_data) —— */
  var contactForm = document.getElementById("contact-form");
  if (contactForm) {
    contactForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var name = (document.getElementById("cf-name") || {}).value || "";
      var email = (document.getElementById("cf-email") || {}).value || "";
      var phone = (document.getElementById("cf-phone") || {}).value || "";
      var interestEl = document.getElementById("cf-interest");
      var interest = "—";
      if (interestEl) {
        // Use visible option label (translated) for the message
        var opt = interestEl.options[interestEl.selectedIndex];
        interest = (opt && opt.textContent) || interestEl.value || "—";
      }
      var message = (document.getElementById("cf-message") || {}).value || "";
      var dates = (document.getElementById("cf-dates") || {}).value || "";
      var people = (document.getElementById("cf-people") || {}).value || "";

      /* Google Ads enhanced conversions — in-page user_data (email preferred) */
      if (typeof window.MDL_setUserData === "function") {
        var nameParts = name.trim().split(/\s+/);
        window.MDL_setUserData({
          email: email,
          phone_number: phone,
          first_name: nameParts[0] || "",
          last_name: nameParts.length > 1 ? nameParts.slice(1).join(" ") : "",
        });
      }

      var tpl =
        (window.I18N && window.I18N.t("wa.contact_prefix")) ||
        "Hello, my name is {name}.\nInterest: {interest}.\n";
      var msg = tpl
        .replace("{name}", name.trim())
        .replace("{interest}", interest);
      if (email) msg += "Email: " + email.trim() + "\n";
      if (phone) msg += "Phone: " + phone.trim() + "\n";
      if (dates) msg += dates + "\n";
      if (people) msg += people + "\n";
      if (message) msg += "\n" + message.trim();

      var success = document.getElementById("contact-success");
      if (success) success.classList.add("is-visible");

      openWhatsAppChat(WA, msg);
    });

    var interestSelect = document.getElementById("cf-interest");
    var extraFields = document.getElementById("contact-extra-fields");
    if (interestSelect && extraFields) {
      var syncExtra = function () {
        var v = interestSelect.value;
        extraFields.hidden = !(
          v === "Hospedagem" ||
          v === "Evento" ||
          v === "Filmagem"
        );
        var datesLabel = document.querySelector('label[for="cf-dates"]');
        var peopleLabel = document.querySelector('label[for="cf-people"]');
        var tr = function (k, fb) {
          return (window.I18N && window.I18N.t(k)) || fb;
        };
        if (datesLabel) {
          datesLabel.textContent =
            v === "Hospedagem"
              ? tr("ct.form.dates", "Datas desejadas")
              : v === "Evento"
                ? tr("ct.form.dates_event", "Data do evento")
                : tr("ct.form.dates_film", "Data pretendida");
        }
        if (peopleLabel) {
          peopleLabel.textContent =
            v === "Hospedagem"
              ? tr("ct.form.people", "Número de hóspedes")
              : v === "Evento"
                ? tr("ct.form.people_event", "Número de convidados")
                : tr("ct.form.people_film", "Tamanho da equipe");
        }
      };
      interestSelect.addEventListener("change", syncExtra);
      document.addEventListener("mdl:langchange", syncExtra);
      syncExtra();
    }
  }

  /* —— Gallery filters —— */
  var filters = document.querySelectorAll(".gallery-filter");
  var sections = document.querySelectorAll(".gallery-section");
  if (filters.length && sections.length) {
    filters.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var cat = btn.getAttribute("data-filter");
        filters.forEach(function (b) {
          b.classList.toggle("is-active", b === btn);
        });
        sections.forEach(function (sec) {
          if (cat === "all") {
            sec.hidden = false;
          } else {
            sec.hidden = sec.getAttribute("data-category") !== cat;
          }
        });
      });
    });
  }

  /* —— Lightbox (event delegation — works after media rehydrate / lang change) —— */
  function lbLabel(key, fb) {
    return (window.I18N && window.I18N.t(key)) || fb;
  }

  var lb = document.createElement("div");
  lb.className = "lightbox";
  lb.setAttribute("role", "dialog");
  lb.setAttribute("aria-modal", "true");
  lb.setAttribute("aria-label", lbLabel("ui.lightbox", "Image view"));
  lb.innerHTML =
    '<button type="button" class="lightbox__close" aria-label="' +
    lbLabel("ui.close", "Close") +
    '">&times;</button>' +
    '<button type="button" class="lightbox__prev" aria-label="' +
    lbLabel("ui.prev", "Previous") +
    '">&#8249;</button>' +
    '<img class="lightbox__img" alt="">' +
    '<button type="button" class="lightbox__next" aria-label="' +
    lbLabel("ui.next", "Next") +
    '">&#8250;</button>' +
    '<p class="lightbox__caption"></p>';
  document.body.appendChild(lb);

  var imgEl = lb.querySelector(".lightbox__img");
  var capEl = lb.querySelector(".lightbox__caption");
  var index = 0;

  function lightboxItems() {
    return Array.prototype.slice.call(
      document.querySelectorAll("[data-lightbox]")
    );
  }

  function openAt(i) {
    var items = lightboxItems();
    if (!items.length) return;
    index = ((i % items.length) + items.length) % items.length;
    var el = items[index];
    var inner = el.tagName === "IMG" ? el : el.querySelector("img");
    var src =
      el.getAttribute("data-full") ||
      (inner && (inner.getAttribute("data-full") || inner.getAttribute("src"))) ||
      el.getAttribute("src") ||
      "";
    var caption =
      el.getAttribute("data-caption") ||
      (inner && inner.getAttribute("alt")) ||
      "";
    imgEl.src = src;
    imgEl.alt = caption;
    capEl.textContent = caption;
    lb.classList.add("is-open");
    document.body.classList.add("lightbox-open");
  }

  function close() {
    lb.classList.remove("is-open");
    document.body.classList.remove("lightbox-open");
    imgEl.src = "";
  }

  document.addEventListener("click", function (e) {
    var el = e.target.closest("[data-lightbox]");
    if (!el || lb.contains(el)) return;
    e.preventDefault();
    var items = lightboxItems();
    var i = items.indexOf(el);
    if (i < 0) return;
    openAt(i);
  });

  lb.querySelector(".lightbox__close").addEventListener("click", close);
  lb.querySelector(".lightbox__prev").addEventListener("click", function () {
    openAt(index - 1);
  });
  lb.querySelector(".lightbox__next").addEventListener("click", function () {
    openAt(index + 1);
  });
  lb.addEventListener("click", function (e) {
    if (e.target === lb) close();
  });
  document.addEventListener("keydown", function (e) {
    if (!lb.classList.contains("is-open")) return;
    if (e.key === "Escape") close();
    if (e.key === "ArrowLeft") openAt(index - 1);
    if (e.key === "ArrowRight") openAt(index + 1);
  });

  /* —— Home hero looping video (muted autoplay; respect reduced motion) —— */
  (function initHomeHeroVideo() {
    var video = document.querySelector(".home-hero__video");
    if (!video) return;
    var reduce =
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      try {
        video.pause();
      } catch (e) {}
      video.removeAttribute("autoplay");
      video.style.display = "none";
      return;
    }
    video.muted = true;
    video.defaultMuted = true;
    video.playsInline = true;
    video.setAttribute("playsinline", "");
    video.setAttribute("webkit-playsinline", "");
    video.setAttribute("muted", "");
    var tryPlay = function () {
      var p = video.play();
      if (p && typeof p.catch === "function") {
        p.catch(function () {
          /* Retry once after a short delay (some browsers need user gesture / buffer) */
          setTimeout(function () {
            video.muted = true;
            video.play().catch(function () {});
          }, 400);
        });
      }
    };
    if (video.readyState >= 2) tryPlay();
    else {
      video.addEventListener("loadeddata", tryPlay, { once: true });
      video.addEventListener("canplay", tryPlay, { once: true });
    }
    /* If the tab becomes visible again, ensure playback continues */
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && video.paused && !reduce) tryPlay();
    });
  })();
})();
