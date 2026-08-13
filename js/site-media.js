/**
 * Mansão do Lago — Media catalog (single place to swap photos & videos)
 *
 * HOW TO UPDATE MEDIA
 * -------------------
 * 1. Add/replace files under images/ or videos/
 * 2. Change only the paths (and alt text) in this file
 * 3. Reload the page
 */
window.SITE_MEDIA = {
  version: "2026-07-media-overhaul",
  notes:
    "Guest suite keys point only to images/suite/hospedes*. House ambient clips live in videos/home/.",

  shared: {
    poolFacade: {
      src: "images/pool/mansao-do-lago-piscina-fachada-casa-01.jpg",
      alt: "Piscina e fachada da Mansão do Lago",
      altKey: "cap.piscina_e_fachada_da_mansao_do_lago",
    },
    lakeBridge: {
      src: "images/lake/mansao-do-lago-lago-ponte-madeira-01.jpg",
      alt: "Lago e ponte de madeira",
      altKey: "cap.lago_e_ponte_de_madeira",
    },
    nightPool: {
      src: "images/night/mansao-do-lago-piscina-iluminada-noite-01.jpg",
      alt: "Piscina iluminada à noite",
      altKey: "cap.piscina_iluminada_a_noite",
    },
  },

  /* House ambient clips (rooms & grounds — not events/productions) */
  home: {
    videos: [
      {
        id: "home-arrival",
        src: "videos/home/arrival.mp4",
        poster: "images/entrance/mansao-do-lago-entrada-portao-01.webp",
        title: "Chegada",
        titleKey: "home.vid.arrival",
        caption: "Entrada da casa",
        captionKey: "home.vid.arrival.c",
      },
      {
        id: "home-bridge",
        src: "videos/home/bridge.mp4",
        poster: "images/lake/mansao-do-lago-lago-ponte-madeira-01.webp",
        title: "A ponte",
        titleKey: "home.vid.bridge",
        caption: "Lago e ponte",
        captionKey: "home.vid.bridge.c",
      },
      {
        id: "home-fishes",
        src: "videos/home/fishes.mp4",
        poster: "images/lake/mansao-do-lago-lago-vista-geral-01.webp",
        title: "O lago",
        titleKey: "home.vid.fishes",
        caption: "Vida no lago",
        captionKey: "home.vid.fishes.c",
      },
      {
        id: "home-lakegarden",
        src: "videos/home/lakegarden.mp4",
        poster: "images/lakegarden/mansao-do-lago-jardim-lago-01.webp",
        title: "Jardim do lago",
        titleKey: "home.vid.lakegarden",
        caption: "Jardins e água",
        captionKey: "home.vid.lakegarden.c",
      },
      {
        id: "home-lakegarden2",
        src: "videos/home/lakegarde2.mp4",
        poster: "images/lakegarden/mansao-do-lago-jardim-lago-04.webp",
        title: "Jardim do lago",
        titleKey: "home.vid.lakegarden2",
        caption: "Outro ângulo do jardim",
        captionKey: "home.vid.lakegarden2.c",
      },
      {
        id: "home-pub1",
        src: "videos/home/pub1.mp4",
        poster: "images/pub/mansao-do-lago-pub-ingles-sofas-01.webp",
        title: "Pub inglês",
        titleKey: "home.vid.pub1",
        caption: "Ambiente do pub",
        captionKey: "home.vid.pub1.c",
      },
      {
        id: "home-pub2",
        src: "videos/home/pub2.mp4",
        poster: "images/pub/mansao-do-lago-pub-ambiente-01.webp",
        title: "Pub inglês",
        titleKey: "home.vid.pub2",
        caption: "Detalhes do pub",
        captionKey: "home.vid.pub2.c",
      },
      {
        id: "home-gym",
        src: "videos/home/gym.mp4",
        poster: "images/gym-sauna/mansao-do-lago-academia-halteres-01.webp",
        title: "Academia",
        titleKey: "home.vid.gym",
        caption: "Espaço de bem-estar",
        captionKey: "home.vid.gym.c",
      },
    ],
  },

  events: {
    hero: {
      src: "images/events/mansao-do-lago-evento-hero-add3-01.jpg",
      alt: "Celebração na Mansão do Lago",
      altKey: "ev.hero.alt",
    },
    intro: {
      src: "images/gourmet/mansao-do-lago-area-gourmet-mesa-01.jpg",
      alt: "Área gourmet preparada para encontros",
      altKey: "cap.area_gourmet_preparada_para_encontros",
    },
    gallery: [
      {
        src: "images/events/mansao-do-lago-evento-hero-add3-01.jpg",
        alt: "Celebração na Mansão do Lago",
        caption: "Celebração na casa",
      },
      {
        src: "images/events/mansao-do-lago-festa-piscina-iluminada-01.jpg",
        alt: "Festa na piscina iluminada",
        caption: "Celebração na piscina",
      },
      {
        src: "images/events/mansao-do-lago-mesa-festa-aniversario-01.jpg",
        alt: "Mesa de festa",
        caption: "Pequenas celebrações",
      },
      {
        src: "images/pool/mansao-do-lago-piscina-fachada-casa-01.jpg",
        alt: "Piscina e casa",
        caption: "Piscina e área externa",
      },
      {
        src: "images/gourmet/mansao-do-lago-churrasqueira-forno-pizza-01.jpg",
        alt: "Área gourmet",
        caption: "Área gourmet",
      },
      {
        src: "images/pub/mansao-do-lago-pub-ingles-sofas-01.jpg",
        alt: "Pub inglês",
        caption: "Pub inglês",
      },
      {
        src: "images/interiors/mansao-do-lago-sala-jantar-vista-geral-01.jpg",
        alt: "Sala de jantar",
        caption: "Sala de jantar",
      },
      {
        src: "images/varandas/mansao-do-lago-varanda-vista-piscina-01.jpg",
        alt: "Varanda com vista para a piscina",
        caption: "Varandas",
      },
      {
        src: "images/lakegarden/mansao-do-lago-jardim-lago-01.jpg",
        alt: "Jardim junto ao lago",
        caption: "Jardim e lago",
      },
    ],
    videos: [],
  },

  filmings: {
    hero: {
      src: "images/filmings/mansao-do-lago-producao-noite-02.jpg",
      alt: "Produção noturna na Mansão do Lago",
    },
    intro: {
      src: "images/filmings/mansao-do-lago-producao-piscina-noturna-01.jpg",
      alt: "Produção noturna na piscina",
    },
    spaces: [
      {
        src: "images/pool/mansao-do-lago-piscina-vista-aerea-01.jpg",
        alt: "Piscina vista aérea",
        titleKey: "fi.space.1.h",
        textKey: "fi.space.1.p",
        title: "Exteriores & lazer",
        text: "Piscina, cascata, jardins e lago — luz natural e cenários abertos.",
      },
      {
        src: "images/kitchen/mansao-do-lago-cozinha-ilha-sala-jantar-01.jpg",
        alt: "Cozinha e sala de jantar",
        titleKey: "fi.space.2.h",
        textKey: "fi.space.2.p",
        title: "Interiores",
        text: "Salas, jantar, halls e detalhes de arquitetura residencial.",
      },
      {
        src: "images/office/mansao-do-lago-escritorio-presidencial-01.jpg",
        alt: "Escritório",
        titleKey: "fi.space.3.h",
        textKey: "fi.space.3.p",
        title: "Escritório",
        text: "Ambiente sofisticado para cenas de reunião, trabalho ou character.",
      },
      {
        src: "images/pub/mansao-do-lago-pub-mesa-poker-bar-01.jpg",
        alt: "Pub inglês",
        titleKey: "fi.space.4.h",
        textKey: "fi.space.4.p",
        title: "Pub inglês",
        text: "Madeira, iluminação quente e atmosfera intimista.",
      },
    ],
    gallery: [
      {
        src: "images/filmings/mansao-do-lago-producao-pub-ingles-01.jpg",
        alt: "Produção no pub",
        caption: "Produção no pub",
      },
      {
        src: "images/filmings/mansao-do-lago-producao-piscina-noturna-01.jpg",
        alt: "Produção na piscina",
        caption: "Piscina à noite",
      },
      {
        src: "images/filmings/mansao-do-lago-producao-escritorio-elenco-01.jpg",
        alt: "Produção no escritório",
        caption: "Escritório",
      },
      {
        src: "images/filmings/mansao-do-lago-producao-quarto-filmagem-01.jpg",
        alt: "Filmagem em ambiente interno",
        caption: "Ambiente interno",
      },
      {
        src: "images/filmings/mansao-do-lago-producao-sala-jantar-01.jpg",
        alt: "Produção na sala de jantar",
        caption: "Sala de jantar",
      },
      {
        src: "images/filmings/mansao-do-lago-producao-noite-01.jpg",
        alt: "Produção noturna",
        caption: "Noite",
      },
      {
        src: "images/filmings/mansao-do-lago-producao-noite-02.jpg",
        alt: "Produção noturna",
        caption: "Noite",
      },
      {
        src: "images/lake/mansao-do-lago-lago-ponte-madeira-01.jpg",
        alt: "Lago e ponte",
        caption: "Lago e ponte",
      },
      {
        src: "images/night/mansao-do-lago-piscina-iluminada-noite-01.jpg",
        alt: "Piscina à noite",
        caption: "Noite",
      },
    ],
    videos: [],
  },

  suite: {
    photos: [
      {
        src: "images/suite/mansao-do-lago-suite-hospedes1-01.jpg",
        alt: "Suíte para hóspedes",
      },
      {
        src: "images/suite/mansao-do-lago-suite-hospedes1-02.jpg",
        alt: "Suíte com sofá-cama",
      },
      {
        src: "images/suite/mansao-do-lago-suite-hospedes1-03.jpg",
        alt: "Suíte — vista ampla",
      },
      {
        src: "images/suite/mansao-do-lago-banheiro-suite-01.jpg",
        alt: "Banheiro da suíte",
      },
      {
        src: "images/suite/mansao-do-lago-banheiro-suite-02.jpg",
        alt: "Banheiro da suíte",
      },
    ],
  },
};
