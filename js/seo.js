/**
 * Injects verification meta, canonical, hreflang, OG helpers, and JSON-LD.
 * Load after site-config.js (reviews-data.js optional, for aggregateRating).
 *
 * i18n + SEO:
 * - Clean path = Portuguese / x-default (canonical without ?lang=)
 * - ?lang=en and ?lang=es must be self-canonical (same URL as hreflang alternate)
 *   otherwise Google treats EN/ES as duplicates of PT and drops them.
 * - Static /en/… folders keep path-based canonicals (no ?lang= forced on them).
 */
(function () {
  "use strict";
  var cfg = window.SITE_CONFIG;
  if (!cfg) return;

  var base = (cfg.siteUrl || "").replace(/\/$/, "");
  var path = window.location.pathname || "/";
  /* Prefer clean URLs: /index.html → /  and  /en/index.html → /en/ */
  path = path.replace(/\/index\.html$/i, "/");
  if (!path || path === "/index.html") path = "/";
  if (path.charAt(0) !== "/") path = "/" + path;

  var file = path.split("/").filter(Boolean).pop() || "";
  if (file.indexOf("\\") !== -1) file = file.split("\\").pop();
  /* Root or language folder index → no breadcrumb list */
  var isHomePath =
    path === "/" ||
    path === "" ||
    (path.slice(-1) === "/" && file.indexOf(".html") === -1);

  /* Static language folders (e.g. /en/) — not the querystring i18n system */
  function folderLangFromPath(p) {
    var segs = String(p || "").replace(/\\/g, "/").split("/");
    for (var i = 0; i < segs.length; i++) {
      var s = segs[i];
      if (!s || /:$/.test(s)) continue;
      if (/^en$/i.test(s)) return "en";
      if (/^es$/i.test(s)) return "es";
    }
    return null;
  }
  var isStaticLangPath = !!folderLangFromPath(path);

  /* Clean page URL (no query) — PT / x-default identity for dynamic pages */
  var pageUrlClean = base + (path === "/" ? "/" : path);
  /* Backward-compatible alias used later in breadcrumbs */
  var pageUrl = pageUrlClean;

  function ensureMeta(attr, key, value) {
    if (!value) return;
    var sel =
      attr === "property"
        ? 'meta[property="' + key + '"]'
        : 'meta[name="' + key + '"]';
    var el = document.querySelector(sel);
    if (!el) {
      el = document.createElement("meta");
      el.setAttribute(attr, key);
      document.head.appendChild(el);
    }
    el.setAttribute("content", value);
  }

  function ensureLink(rel, href, hreflang) {
    if (!href) return;
    var sel = 'link[rel="' + rel + '"]';
    if (hreflang) sel += '[hreflang="' + hreflang + '"]';
    else if (rel === "canonical") sel = 'link[rel="canonical"]';
    var el = document.querySelector(sel);
    if (!el) {
      el = document.createElement("link");
      el.rel = rel;
      if (hreflang) el.hreflang = hreflang;
      document.head.appendChild(el);
    }
    el.href = href;
  }

  function normalizeLang(raw) {
    if (!raw) return null;
    var q = String(raw).toLowerCase();
    if (q === "pt-br" || q === "pt_br") return "pt";
    if (q === "en" || q === "es" || q === "pt") return q;
    return null;
  }

  function langFromQuery() {
    try {
      return normalizeLang(
        new URLSearchParams(window.location.search || "").get("lang")
      );
    } catch (e) {
      return null;
    }
  }

  function langFromPath() {
    return folderLangFromPath(path);
  }

  function withLangQuery(cleanUrl, lang) {
    if (!cleanUrl) return cleanUrl;
    if (!lang || lang === "pt") return cleanUrl;
    var join = cleanUrl.indexOf("?") >= 0 ? "&" : "?";
    return cleanUrl + join + "lang=" + lang;
  }

  /**
   * Canonical must match the language version Google is evaluating.
   * PT (default / ?lang=pt) → clean URL
   * EN / ES via ?lang= → self-referential URL including the param
   * Static /en/… → clean folder path (no query)
   */
  function canonicalForLang(lang) {
    if (isStaticLangPath || !base) return pageUrlClean;
    lang = normalizeLang(lang) || "pt";
    if (lang === "en" || lang === "es") return withLangQuery(pageUrlClean, lang);
    return pageUrlClean;
  }

  function ogLocaleForLang(lang) {
    lang = normalizeLang(lang) || "pt";
    if (lang === "en") return "en_US";
    if (lang === "es") return "es_ES";
    return cfg.locale || "pt_BR";
  }

  function applyUrlSeo(lang) {
    if (!base) return;
    lang = normalizeLang(lang) || langFromQuery() || "pt";
    var canonical = canonicalForLang(lang);
    pageUrl = canonical;
    ensureLink("canonical", canonical);
    ensureMeta("property", "og:url", canonical);
    ensureMeta("property", "og:locale", ogLocaleForLang(lang));
  }

  /* hreflang cluster for dynamic (query) pages — each alternate is self-consistent */
  function applyHreflangCluster() {
    if (!base || isStaticLangPath) return;
    ensureLink("alternate", pageUrlClean, "pt-BR");
    ensureLink("alternate", withLangQuery(pageUrlClean, "en"), "en");
    ensureLink("alternate", withLangQuery(pageUrlClean, "es"), "es");
    ensureLink("alternate", pageUrlClean, "x-default");
  }

  /* Static /en/ and /es/ LPs: folder-based hreflang cluster */
  function applyStaticLangHreflang() {
    if (!base || !isStaticLangPath) return;
    var ptPath = path.replace(/^\/(en|es)/i, "") || "/";
    if (ptPath.charAt(0) !== "/") ptPath = "/" + ptPath;
    var ptUrl = base + (ptPath === "/" ? "/" : ptPath);
    var enUrl;
    var esUrl;
    if (ptPath === "/") {
      enUrl = base + "/en/";
      esUrl = base + "/es/";
    } else {
      enUrl = base + "/en" + ptPath;
      esUrl = base + "/es" + ptPath;
    }
    ensureLink("alternate", ptUrl, "pt-BR");
    ensureLink("alternate", enUrl, "en");
    ensureLink("alternate", esUrl, "es");
    ensureLink("alternate", ptUrl, "x-default");
  }

  /* Google Search Console verification */
  if (cfg.googleSiteVerification) {
    ensureMeta("name", "google-site-verification", cfg.googleSiteVerification);
  }

  /* Canonical + hreflang (fixed international SEO) */
  applyUrlSeo(langFromQuery() || langFromPath() || "pt");
  if (isStaticLangPath) applyStaticLangHreflang();
  else applyHreflangCluster();

  /* Keep canonical in sync when the language switcher uses history.replaceState */
  document.addEventListener("mdl:langchange", function (ev) {
    var lang =
      (ev && ev.detail && ev.detail.lang) ||
      langFromQuery() ||
      "pt";
    applyUrlSeo(lang);
  });

  window.MDL_seo = {
    applyUrlSeo: applyUrlSeo,
    canonicalForLang: canonicalForLang,
    pageUrlClean: pageUrlClean,
  };

  /* Absolute OG image if relative */
  var ogImg = document.querySelector('meta[property="og:image"]');
  if (ogImg && base) {
    var content = ogImg.getAttribute("content") || "";
    if (content && content.indexOf("http") !== 0) {
      ogImg.setAttribute(
        "content",
        base + "/" + content.replace(/^\//, "")
      );
    }
  } else if (base && cfg.defaultOgImage) {
    ensureMeta(
      "property",
      "og:image",
      base + "/" + String(cfg.defaultOgImage).replace(/^\//, "")
    );
  }

  /* Mirror description into OG/Twitter when missing */
  var pageDesc = document.querySelector('meta[name="description"]');
  var descContent = pageDesc ? pageDesc.getAttribute("content") : "";
  if (descContent) {
    if (!document.querySelector('meta[property="og:description"]')) {
      ensureMeta("property", "og:description", descContent);
    }
    if (!document.querySelector('meta[name="twitter:description"]')) {
      ensureMeta("name", "twitter:description", descContent);
    }
  }
  var pageTitle = document.title || "";
  if (pageTitle && !document.querySelector('meta[name="twitter:title"]')) {
    ensureMeta("name", "twitter:title", pageTitle);
  }

  if (base) {
    /* og:url + og:locale already set by applyUrlSeo; keep site-wide OG defaults */
    ensureMeta("property", "og:site_name", cfg.siteName || "Mansão do Lago");
    ensureMeta("property", "og:type", "website");
    ensureMeta("name", "twitter:card", "summary_large_image");
    /* Multiple og:locale:alternate tags */
    ["en_US", "es_ES", "pt_BR"].forEach(function (loc) {
      var exists = Array.prototype.some.call(
        document.querySelectorAll('meta[property="og:locale:alternate"]'),
        function (m) {
          return m.getAttribute("content") === loc;
        }
      );
      if (exists) return;
      /* Skip alternate that matches current og:locale */
      var cur = document.querySelector('meta[property="og:locale"]');
      if (cur && cur.getAttribute("content") === loc) return;
      var el = document.createElement("meta");
      el.setAttribute("property", "og:locale:alternate");
      el.setAttribute("content", loc);
      document.head.appendChild(el);
    });
  }

  /* JSON-LD: LodgingBusiness + WebSite (+ optional rating / FAQ) */
  var biz = cfg.business || {};
  var contact = cfg.contact || {};
  var listings = cfg.listings || {};
  var img = biz.image || cfg.defaultOgImage || "";
  if (img && img.indexOf("http") !== 0 && base) {
    img = base + "/" + img.replace(/^\//, "");
  }

  var logoPath = biz.logo || cfg.logo || "images/logos/mansao-logo-google-512.png";
  var logoUrl = logoPath;
  if (logoUrl && logoUrl.indexOf("http") !== 0 && base) {
    logoUrl = base + "/" + logoUrl.replace(/^\//, "");
  }

  var sameAs = [listings.airbnb, listings.booking, listings.spotz].filter(
    Boolean
  );

  var lodging = {
    "@context": "https://schema.org",
    "@type": "LodgingBusiness",
    name: biz.name || cfg.siteName,
    description: biz.description || "",
    url: base || undefined,
    image: img || undefined,
    logo: logoUrl || undefined,
    telephone: contact.whatsappDisplay || undefined,
    priceRange: biz.priceRange || undefined,
    address: {
      "@type": "PostalAddress",
      addressLocality: contact.city || "São Paulo",
      addressRegion: contact.region || "SP",
      addressCountry: contact.country || "BR",
      addressNeighborhood: contact.neighborhood || "Perdizes",
    },
    geo: {
      "@type": "GeoCoordinates",
      /* Approximate center of Perdizes — not exact property */
      latitude: -23.5365,
      longitude: -46.6805,
    },
    amenityFeature: (biz.amenities || []).map(function (a) {
      return { "@type": "LocationFeatureSpecification", name: a };
    }),
    sameAs: sameAs.length ? sameAs : undefined,
  };

  /* Aggregate rating: SITE_REVIEWS if loaded, else site-config.reviews */
  var rev = window.SITE_REVIEWS;
  var revCfg = cfg.reviews || {};
  var ratingVal =
    rev && typeof rev.rating === "number" ? rev.rating : revCfg.ratingValue;
  var ratingCount =
    rev && rev.count != null ? rev.count : revCfg.reviewCount;
  if (ratingVal != null && ratingCount) {
    lodging.aggregateRating = {
      "@type": "AggregateRating",
      ratingValue: String(ratingVal),
      reviewCount: String(ratingCount),
      bestRating: String(
        (rev && rev.bestRating) || revCfg.bestRating || 5
      ),
      worstRating: "1",
    };
  }

  var website = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: cfg.siteName,
    url: base || undefined,
    inLanguage: ["pt-BR", "en", "es"],
    publisher: {
      "@type": "Organization",
      name: cfg.siteName,
      url: base || undefined,
      logo: logoUrl
        ? {
            "@type": "ImageObject",
            url: logoUrl,
          }
        : undefined,
    },
  };

  function inject(data) {
    var s = document.createElement("script");
    s.type = "application/ld+json";
    s.textContent = JSON.stringify(data);
    document.head.appendChild(s);
  }

  inject(lodging);
  inject(website);

  /* FAQPage schema from visible Q&A (faq.html). Rebuild after i18n. */
  var page = document.documentElement.getAttribute("data-page") || "";
  function injectFaqSchema() {
    if (page !== "faq") return;
    var old = document.querySelector("script[data-mdl-faq-schema]");
    if (old) old.parentNode.removeChild(old);
    var entities = [];
    document.querySelectorAll(".faq-item").forEach(function (item) {
      var qEl = item.querySelector("summary");
      var aEl = item.querySelector(".faq-answer");
      if (!qEl || !aEl) return;
      var q = (qEl.textContent || "").replace(/\s+/g, " ").trim();
      var a = (aEl.textContent || "").replace(/\s+/g, " ").trim();
      if (!q || !a) return;
      entities.push({
        "@type": "Question",
        name: q,
        acceptedAnswer: {
          "@type": "Answer",
          text: a,
        },
      });
    });
    if (!entities.length) return;
    var s = document.createElement("script");
    s.type = "application/ld+json";
    s.setAttribute("data-mdl-faq-schema", "1");
    s.textContent = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: entities,
    });
    document.head.appendChild(s);
  }
  injectFaqSchema();
  document.addEventListener("mdl:langchange", injectFaqSchema);

  /* BreadcrumbList for inner pages (not site root) */
  if (base && path !== "/" && file && !isHomePath) {
    var h1 = document.querySelector("h1");
    var title =
      document.title.split("|")[0].trim() ||
      (h1 && h1.textContent ? h1.textContent.trim() : "") ||
      file;
    inject({
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        {
          "@type": "ListItem",
          position: 1,
          name: cfg.siteName || "Mansão do Lago",
          item: base + "/",
        },
        {
          "@type": "ListItem",
          position: 2,
          name: title,
          item: pageUrl,
        },
      ],
    });
  }
})();
