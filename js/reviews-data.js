/**
 * Mansão do Lago — curated guest reviews (Airbnb + Booking)
 *
 * HOW TO UPDATE
 * 1. Add objects to `items`
 * 2. country: ISO 3166-1 alpha-2 (BR, ES, NL, FR, …)
 * 3. source: "Airbnb" | "Booking"
 * 4. rating: 1–5 for Airbnb-style stars; scale: "10" + rating 10 for Booking notes
 * 5. text = PT default; textEn / textEs for translations
 * 6. location = PT; locationEn / locationEs for display
 * 7. International guests (country !== "BR") are shown first in the carousel
 * 8. Re-upload this file to Hostinger
 */
window.SITE_REVIEWS = {
  source: "Airbnb",
  listingUrl: "https://www.airbnb.com.br/rooms/1178179281806962432",
  bookingUrl:
    "https://www.booking.com/hotel/br/suite-privativa-em-lindo-casarao-sao-paulo",
  rating: 4.92,
  count: 36,
  guestFavorite: true,
  superhost: true,
  highlights: [
    { key: "rev.hl.pool", label: "Piscina" },
    { key: "rev.hl.host", label: "Hospitalidade" },
    { key: "rev.hl.comfort", label: "Conforto" },
    { key: "rev.hl.space", label: "Espaço" },
    { key: "rev.hl.clean", label: "Limpeza" },
    { key: "rev.hl.location", label: "Localização" },
  ],
  /* Order: international first, then Brazilian (carousel also re-sorts by country) */
  items: [
    {
      name: "Alvaro",
      country: "ES",
      location: "Espanha",
      locationEn: "Spain",
      locationEs: "España",
      date: "2025-02-16",
      rating: 10,
      scale: 10,
      source: "Booking",
      text:
        "Gostei de tudo. As fotos refletem fielmente o lugar. Além disso, os proprietários são muito prestativos e facilitam tudo para você.",
      textEn:
        "I liked everything. The photos faithfully reflect the place. On top of that, the owners are very helpful and make everything easy for you.",
      textEs:
        "Me gustó todo. Las fotos reflejan fielmente el lugar. Además, los propietarios son muy atentos y lo facilitan todo.",
    },
    {
      name: "David",
      country: "NL",
      location: "Países Baixos",
      locationEn: "Netherlands",
      locationEs: "Países Bajos",
      date: "2025-04",
      rating: 10,
      scale: 10,
      source: "Booking",
      text:
        "Incrível. O apartamento está localizado numa área muito agradável e tranquila. Fica perto da Vila Madalena, que é uma área perfeita para sair e ouvir samba. Os proprietários são muito gentis e acolhedores.",
      textEn:
        "Incredible. The apartment is in a very pleasant, quiet area. It is close to Vila Madalena, perfect for going out and hearing samba. The owners are very kind and welcoming.",
      textEs:
        "Increíble. El apartamento está en una zona muy agradable y tranquila. Queda cerca de Vila Madalena, ideal para salir y escuchar samba. Los propietarios son muy amables y acogedores.",
    },
    {
      name: "Cassandra",
      country: "FR",
      location: "França",
      locationEn: "France",
      locationEs: "Francia",
      date: "2025-10",
      rating: 10,
      scale: 10,
      source: "Booking",
      text:
        "Excepcional. Adorei tudo! Nossa recepção e simpatia estavam lá. A localização é ótima e a vila é incrível! Ótimo custo-benefício! Teremos o maior prazer em voltar!",
      textEn:
        "Exceptional. I loved everything! The welcome and warmth were there. The location is great and the estate is incredible! Great value! We would be delighted to come back!",
      textEs:
        "Excepcional. ¡Me encantó todo! La recepción y la simpatía estaban presentes. La ubicación es excelente y la casa es increíble. ¡Muy buena relación calidad-precio! Volveremos con mucho gusto.",
    },
    {
      name: "Ana Paula",
      country: "BR",
      location: "Brasil",
      locationEn: "Brazil",
      locationEs: "Brasil",
      date: "2026-02",
      rating: 5,
      scale: 5,
      source: "Airbnb",
      text:
        "Eu daria 10 estrelas para os três, casa, Guilherme e Cintia que nos receberam muito bem, nos mostraram todas as áreas que podíamos usufruir. Tudo impecável, bem aconchegante e lindo.",
      textEn:
        "I would give 10 stars to all three: the house, Guilherme and Cintia, who welcomed us so well and showed us every area we could enjoy. Everything was impeccable, cozy, and beautiful.",
      textEs:
        "Daría 10 estrellas a los tres: la casa, Guilherme y Cintia, que nos recibieron muy bien y nos mostraron todas las áreas que podíamos disfrutar. Todo impecable, acogedor y hermoso.",
    },
    {
      name: "Nadia",
      country: "BR",
      location: "Brasil",
      locationEn: "Brazil",
      locationEs: "Brasil",
      date: "2025-10",
      rating: 5,
      scale: 5,
      source: "Airbnb",
      text:
        "A estadia foi perfeita! O espaço é maravilhoso, melhor que nas fotos. Tudo é muito limpo e organizado. O quarto é grande e arejado, o jardim perto da piscina muito bem cuidado, dá pra sentir a atenção em cada detalhe, o que tornou nossa hospedagem perfeita.",
      textEn:
        "The stay was perfect! The space is wonderful, even better than the photos. Everything is very clean and organized. The room is large and airy, the garden by the pool is beautifully kept. You can feel the care in every detail, which made our stay perfect.",
      textEs:
        "¡La estadía fue perfecta! El espacio es maravilloso, mejor que en las fotos. Todo muy limpio y organizado. La habitación es grande y aireada, el jardín junto a la piscina está muy bien cuidado. Se nota la atención en cada detalle, lo que hizo perfecta nuestra hospedaje.",
    },
    {
      name: "Matheus",
      country: "BR",
      location: "Brasil",
      locationEn: "Brazil",
      locationEs: "Brasil",
      date: "2025-07",
      rating: 5,
      scale: 5,
      source: "Airbnb",
      text:
        "A experiência foi maravilhosa do começo ao fim! O lugar é ainda melhor do que nas fotos! Super aconchegante, muito limpo, bem decorado e com tudo o que a gente precisa pra uma estadia confortável. Dá pra ver que cada detalhe foi pensado com carinho. Os anfitriões foram incríveis!",
      textEn:
        "The experience was wonderful from start to finish! The place is even better than the photos! Super cozy, very clean, well decorated, and with everything you need for a comfortable stay. You can see that every detail was thoughtfully planned. The hosts were incredible!",
      textEs:
        "¡La experiencia fue maravillosa de principio a fin! ¡El lugar es aún mejor que en las fotos! Muy acogedor, limpio, bien decorado y con todo lo necesario para una estancia cómoda. Se nota que cada detalle se pensó con cariño. ¡Los anfitriones fueron increíbles!",
    },
  ],
};
