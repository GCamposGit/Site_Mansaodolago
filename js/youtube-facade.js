/**
 * YouTube music videos:
 * - Desktop (wide): static thumbnail → opens YouTube in a new tab (no embed / no Error 153)
 * - Mobile (narrow / touch phones): click embeds in place via same-origin relay
 */
(function () {
  "use strict";

  function isMobilePlay() {
    // Prefer layout width; also treat iPhone/iPod as mobile even if "desktop site"
    var narrow =
      window.matchMedia && window.matchMedia("(max-width: 900px)").matches;
    var ua = navigator.userAgent || "";
    var phone = /iPhone|iPod|Android.+Mobile|webOS|BlackBerry|IEMobile|Opera Mini/i.test(
      ua
    );
    return narrow || phone;
  }

  function playInCard(el) {
    var id = el.getAttribute("data-yt-id");
    if (!id || !/^[A-Za-z0-9_-]{6,20}$/.test(id)) return;

    var card = el.closest(".yt-card");
    if (!card) return;

    var wrap = document.createElement("div");
    wrap.className = "yt-card__frame";

    var iframe = document.createElement("iframe");
    iframe.src = "youtube-embed.html?v=" + encodeURIComponent(id);
    iframe.title = el.getAttribute("aria-label") || "YouTube video";
    iframe.allow =
      "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
    iframe.setAttribute("allowfullscreen", "");
    iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    iframe.loading = "eager";

    wrap.appendChild(iframe);
    card.innerHTML = "";
    card.appendChild(wrap);
  }

  document.querySelectorAll(".yt-card__play[data-yt-id]").forEach(function (el) {
    el.addEventListener("click", function (e) {
      if (!isMobilePlay()) {
        // Desktop: let the <a href> open YouTube (default)
        return;
      }
      // Mobile: embed in page
      e.preventDefault();
      playInCard(el);
    });
  });
})();
