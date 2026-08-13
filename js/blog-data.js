/**
 * Mansão do Lago — Blog registry
 *
 * published: true = blog live (indexable; Allow /blog/ in robots; listed in sitemap)
 * If taking offline again: published false + noindex + Disallow /blog/ + remove sitemap URLs.
 *
 * Add each new post at the TOP of `posts` (newest first).
 */
window.SITE_BLOG = {
  /** Master switch: keep false until first publish campaign */
  published: true,

  siteName: "Mansão do Lago",
  siteUrl: "https://www.mansaodolago.com",
  defaultAuthor: "Cintia & Guilherme",
  defaultAuthorRole: "Anfitriões da Mansão do Lago",

  categories: [
    { id: "all", label: "Todos", labelEn: "All", labelEs: "Todos" },
    { id: "hospedagem", label: "Hospedagem", labelEn: "Stay", labelEs: "Hospedaje" },
    { id: "filmagens", label: "Filmagens", labelEn: "Filming", labelEs: "Filmaciones" },
    { id: "eventos", label: "Eventos", labelEn: "Events", labelEs: "Eventos" },
    { id: "mansao", label: "A Mansão", labelEn: "The Estate", labelEs: "La Mansión" },
  ],

  /**
   * @typedef {Object} BlogPost
   * @property {string} slug - filename without .html
   * @property {string} title
   * @property {string} excerpt - card teaser (~140–180 chars)
   * @property {string} category - category id
   * @property {string} date - ISO YYYY-MM-DD
   * @property {string} [dateLabel] - display date PT
   * @property {string} [image] - relative from blog/ or site root path
   * @property {string} [imageAlt]
   * @property {boolean} [featured]
   * @property {string[]} [keywords]
   */
  posts: [
    {
      slug: "eventos-corporativos-residencia-perdizes",
      title:
        "Eventos corporativos em residência: quando o offsite cabe em uma casa (e quando não)",
      excerpt:
        "Offsites e confraternizações enxutas em casas: o que hotel não resolve, que critérios usar e quando a residência é o fit certo em São Paulo.",
      category: "eventos",
      date: "2026-08-05",
      dateLabel: "5 de agosto de 2026",
      image: "../images/gourmet/mansao-do-lago-area-gourmet-mesa-01.jpg",
      imageAlt: "Área de refeições e convívio em residência em São Paulo",
      featured: false,
      keywords: [
        "eventos corporativos residência São Paulo",
        "offsite Perdizes",
        "confraternização pequena SP",
      ],
    },
    {
      slug: "locacao-clipe-musical-casa-sao-paulo",
      title:
        "Locação para clipe musical em casa: o que muda quando o cenário é uma residência real",
      excerpt:
        "Como escolher casa para videoclipe em SP: briefing, tamanho de equipe, ruído e o fit entre música e cenário residencial.",
      category: "filmagens",
      date: "2026-08-05",
      dateLabel: "5 de agosto de 2026",
      image: "../images/filmings/mansao-do-lago-producao-piscina-noturna-01.jpg",
      imageAlt: "Produção audiovisual em área externa de residência em São Paulo",
      featured: false,
      keywords: [
        "locação clipe musical São Paulo",
        "filmagem videoclipe casa",
        "locação residencial Perdizes",
      ],
    },
    {
      slug: "suite-privativa-em-residencia-perdizes",
      title:
        "Suíte privativa em residência: por que escolher uma casa em vez de hotel, pousada ou flat",
      excerpt:
        "Hotel, flat, pousada ou casa inteira? O que muda quando a estadia acontece dentro de uma residência real em bairro calmo de São Paulo.",
      category: "hospedagem",
      date: "2026-08-01",
      dateLabel: "5 de agosto de 2026",
      image: "../images/suite/mansao-do-lago-suite-hospedes1-01.webp",
      imageAlt: "Suíte privativa com luz natural em residência em Perdizes, São Paulo",
      featured: false,
      keywords: [
        "suíte privativa Perdizes",
        "hospedagem residência São Paulo",
        "hotel vs casa Perdizes",
        "onde ficar Perdizes",
      ],
    },
  ],
};
