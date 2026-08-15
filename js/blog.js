/**
 * Blog hub: cards live in blog/index.html so a stale blog-data.js cannot
 * empty the listing. This script only wires filters (show/hide). It rebuilds
 * the grid from SITE_BLOG only when the HTML shipped with no cards.
 */
(function () {
  "use strict";
  var data = window.SITE_BLOG;
  var grid = document.querySelector("[data-blog-grid]");
  var filters = document.querySelector("[data-blog-filters]");
  if (!grid) return;

  var active = "all";
  var cats = (data && data.categories) || [
    { id: "all", label: "Todos" },
    { id: "hospedagem", label: "Hospedagem" },
    { id: "filmagens", label: "Filmagens" },
    { id: "eventos", label: "Eventos" },
    { id: "mansao", label: "A Mansão" },
  ];

  function catLabel(id) {
    for (var i = 0; i < cats.length; i++) {
      if (cats[i].id === id) return cats[i].label || id;
    }
    return id;
  }

  function formatDate(iso, label) {
    if (label) return label;
    if (!iso) return "";
    try {
      var d = new Date(iso + "T12:00:00");
      return d.toLocaleDateString("pt-BR", {
        day: "numeric",
        month: "long",
        year: "numeric",
      });
    } catch (e) {
      return iso;
    }
  }

  function renderCards() {
    var posts = (data && data.posts) || [];
    posts = posts.filter(function (p) {
      return active === "all" || p.category === active;
    });
    if (!posts.length) {
      grid.innerHTML =
        '<p class="blog-empty" data-i18n="blog.empty">Nenhum artigo nesta categoria ainda.</p>';
      return;
    }
    grid.innerHTML = posts
      .map(function (p, idx) {
        var href = p.slug + ".html";
        var img =
          p.image ||
          "../images/hero/mansao-do-lago-hero-lago-ponte-loop-poster-800w.webp";
        if (img.charAt(0) === "/") img = ".." + img;
        var alt = p.imageAlt || p.title;
        var featured = idx === 0 && active === "all" ? " blog-card--featured" : "";
        return (
          '<a class="blog-card' +
          featured +
          '" href="' +
          href +
          '" data-cat="' +
          (p.category || "") +
          '">' +
          '<div class="blog-card__media">' +
          '<img src="' +
          img +
          '" alt="' +
          alt.replace(/"/g, "&quot;") +
          '" width="800" height="500" loading="' +
          (idx === 0 ? "eager" : "lazy") +
          '" decoding="async">' +
          "</div>" +
          '<div class="blog-card__body">' +
          '<div class="blog-card__meta">' +
          '<span class="blog-card__cat">' +
          catLabel(p.category) +
          "</span>" +
          "<span>" +
          formatDate(p.date, p.dateLabel) +
          "</span>" +
          "</div>" +
          '<h2 class="blog-card__title">' +
          p.title +
          "</h2>" +
          '<p class="blog-card__excerpt">' +
          (p.excerpt || "") +
          "</p>" +
          '<span class="blog-card__more">Ler artigo</span>' +
          "</div></a>"
        );
      })
      .join("");
  }

  function ensureEmptyEl() {
    var empty = grid.querySelector(".blog-empty");
    if (empty) return empty;
    empty = document.createElement("p");
    empty.className = "blog-empty";
    empty.setAttribute("data-i18n", "blog.empty");
    empty.textContent = "Nenhum artigo nesta categoria ainda.";
    empty.hidden = true;
    grid.appendChild(empty);
    return empty;
  }

  function applyFilter() {
    var cards = grid.querySelectorAll(".blog-card");
    if (!cards.length) {
      if (data && Array.isArray(data.posts)) renderCards();
      return;
    }
    var shown = 0;
    for (var i = 0; i < cards.length; i++) {
      var cat = cards[i].getAttribute("data-cat") || "";
      var show = active === "all" || cat === active;
      cards[i].hidden = !show;
      if (show) shown += 1;
    }
    var empty = ensureEmptyEl();
    empty.hidden = shown > 0;
  }

  function bindFilters() {
    if (!filters) return;
    filters.querySelectorAll("[data-blog-cat]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        active = btn.getAttribute("data-blog-cat") || "all";
        filters.querySelectorAll(".blog-filter").forEach(function (b) {
          b.classList.toggle(
            "is-active",
            b.getAttribute("data-blog-cat") === active
          );
        });
        applyFilter();
      });
    });
  }

  function renderFilters() {
    if (!filters) return;
    if (!filters.querySelector("[data-blog-cat]")) {
      filters.innerHTML = cats
        .map(function (c) {
          return (
            '<button type="button" class="blog-filter' +
            (c.id === active ? " is-active" : "") +
            '" data-blog-cat="' +
            c.id +
            '">' +
            (c.label || c.id) +
            "</button>"
          );
        })
        .join("");
    }
    bindFilters();
  }

  renderFilters();
  applyFilter();
})();
