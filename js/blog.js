/**
 * Renders blog hub cards from SITE_BLOG.
 * Load after blog-data.js on blog/index.html only.
 */
(function () {
  "use strict";
  var data = window.SITE_BLOG;
  if (!data || !Array.isArray(data.posts)) return;

  var grid = document.querySelector("[data-blog-grid]");
  var filters = document.querySelector("[data-blog-filters]");
  if (!grid) return;

  var active = "all";

  function catLabel(id) {
    var cats = data.categories || [];
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
    /* "Todos" and every category: always a list of article cards (title + excerpt),
       never a single full-bleed “property photo” hero layout. */
    var posts = data.posts.filter(function (p) {
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
        return (
          '<a class="blog-card" href="' +
          href +
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

  function renderFilters() {
    if (!filters) return;
    var cats = data.categories || [{ id: "all", label: "Todos" }];
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
    filters.querySelectorAll("[data-blog-cat]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        active = btn.getAttribute("data-blog-cat") || "all";
        filters.querySelectorAll(".blog-filter").forEach(function (b) {
          b.classList.toggle(
            "is-active",
            b.getAttribute("data-blog-cat") === active
          );
        });
        renderCards();
      });
    });
  }

  renderFilters();
  renderCards();
})();
