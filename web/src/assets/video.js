// The showcase video loads only when the visitor presses play: until then the page shows a poster image from this
// site, and nothing is requested from anywhere else. Without JavaScript the play button is a plain link to the file.
(() => {
  "use strict";
  function play(frame) {
    const provider = frame.dataset.provider;
    let player;
    if (provider === "youtube") {
      // youtube-nocookie.com, loaded only after this click; the button's label says it loads YouTube.
      player = document.createElement("iframe");
      player.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(frame.dataset.youtubeId)}?autoplay=1&rel=0`;
      player.title = frame.dataset.title || "Video";
      player.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
      player.referrerPolicy = "strict-origin-when-cross-origin";
    } else {
      player = document.createElement("video");
      player.controls = true;
      player.playsInline = true;
      player.preload = "auto";
      player.poster = frame.querySelector("img")?.src || "";
      const source = document.createElement("source");
      source.src = frame.dataset.src;
      source.type = "video/mp4";
      player.appendChild(source);
      if (frame.dataset.captions) {
        const track = document.createElement("track");
        track.kind = "captions";
        track.srclang = "en";
        track.label = "English";
        track.src = frame.dataset.captions;
        track.default = true;
        player.appendChild(track);
      }
    }
    frame.replaceChildren(player);
    if (player.tagName === "VIDEO") {
      player.play().catch(() => {});
      player.focus();
    }
  }

  function init() {
    // Short silent loops start on their own, unless the visitor asked their system for less motion.
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    for (const loop of document.querySelectorAll("video[data-autoplay]")) {
      if (!calm) {
        loop.preload = "auto";
        loop.play().catch(() => {});
      }
    }
    for (const frame of document.querySelectorAll("[data-video]")) {
      const button = frame.querySelector(".video-play");
      if (!button) continue;
      button.addEventListener("click", (event) => {
        event.preventDefault();
        play(frame);
      });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
