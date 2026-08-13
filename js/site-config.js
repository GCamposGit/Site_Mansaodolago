/**
 * Mansão do Lago — site-wide configuration
 *
 * BEFORE GO-LIVE (you edit only these):
 * 1. Confirm siteUrl matches the live domain (canonical: https://www.mansaodolago.com)
 * 2. Paste GA4 Measurement ID into gaMeasurementId (e.g. "G-XXXXXXXXXX")
 * 3. Paste Google Search Console meta verification into googleSiteVerification
 *    (only the content= value, not the full HTML tag)
 *
 * Leave gaMeasurementId / googleSiteVerification as "" until you have the codes.
 * Empty GA = no tracking script is loaded.
 */
window.SITE_CONFIG = {
  siteName: "Mansão do Lago",
  /** Canonical production URL — no trailing slash. Must match robots.txt + sitemap.xml */
  siteUrl: "https://www.mansaodolago.com",
  locale: "pt_BR",
  themeColor: "#0D3B2E",

  /* Google Analytics 4 — e.g. "G-ABC123XYZ" (empty = disabled) */
  gaMeasurementId: "G-M4Z64YJ7DJ",

  /**
   * Google Ads / Google tag (gtag) — e.g. "AW-18323812647"
   * Loaded together with GA4 via js/analytics.js (one gtag per page).
   */
  googleAdsId: "AW-18323812647",

  /**
   * Google Ads conversion labels (send_to).
   * Create 4 website conversions in Google Ads → paste each "AW-…/xxxxx" below.
   * Leave "" until you have the label. Format example: "AW-18323812647/AbCdEfGhIj"
   *
   * Bidding tip: mark only WhatsApp as Primary in Google Ads; others as Secondary.
   */
  googleAdsConversions: {
    whatsapp: "AW-18323812647/tA0sCNOznNEcEKfivKFE", // primary — Site: WhatsApp click
    airbnb: "AW-18323812647/IvTACPOPmdEcEKfivKFE", // secondary — Clique Airbnb
    booking: "AW-18323812647/jH_oCNepndEcEKfivKFE", // secondary — Click Booking
    spotz: "AW-18323812647/BNpaCLm1ndEcEKfivKFE", // secondary — Click Spotz
    /* Optional: create “Email click” in Google Ads and paste AW-…/label here */
    email: "",
  },

  /* Search Console HTML-tag verification — paste content value only */
  googleSiteVerification: "y-2G-QRNdawmb3jzSzGzD6OhuRx_TD9ZonbZfRBzwEI",

  contact: {
    whatsappE164: "5511988228936",
    whatsappDisplay: "+55 11 98822-8936",
    email: "reservas@mansaodolago.com",
    city: "São Paulo",
    neighborhood: "Perdizes",
    region: "SP",
    country: "BR",
  },

  listings: {
    airbnb: "https://www.airbnb.com.br/rooms/1178179281806962432",
    booking:
      "https://www.booking.com/hotel/br/suite-privativa-em-lindo-casarao-sao-paulo",
    spotz: "https://spotz.co/s/lindo-casarao-com-piscina-em-perdizes",
  },

  /* Default social share image (relative to site root) */
  defaultOgImage: "images/hero/mansao-do-lago-hero-lago-ponte-01.jpg",

  /**
   * Public review summary for schema.org (keep in sync with js/reviews-data.js).
   * Used even on pages that do not load reviews-data.js.
   */
  reviews: {
    ratingValue: 4.92,
    reviewCount: 36,
    bestRating: 5,
  },

  /**
   * Brand logo for Google / schema / Knowledge Graph
   * Canonical monogram “M” (images/logos). Keep root favicon.* in sync.
   */
  logo: "images/logos/mansao-logo-google-512.png",
  logoSvg: "images/logos/mansao-logo-m.svg",

  /* Schema.org LodgingBusiness — no street address (privacy) */
  business: {
    name: "Mansão do Lago",
    description:
      "Hospede-se na Mansão do Lago em Perdizes, São Paulo: suíte privativa em residência com lago, jardins e piscina. Reserva direta a partir de R$ 389 por noite. Eventos e filmagens sob consulta.",
    image: "images/hero/mansao-do-lago-hero-lago-ponte-01.jpg",
    logo: "images/logos/mansao-logo-google-512.png",
    priceRange: "R$389+",
    amenities: [
      "Pool",
      "Garden",
      "FreeParking",
      "Wifi",
      "Sauna",
      "Gym",
      "PetsAllowed",
    ],
  },
};
