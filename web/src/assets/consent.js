// Cookie choice and Google Analytics, only with consent.
//
// - Nothing from Google is loaded, and no cookie is set, until the visitor clicks "Accept analytics".
// - "No thanks" is one click, as easy as accepting. Global Privacy Control counts as "No thanks".
// - The choice is kept in localStorage ("ks-consent") for 6 months, then we ask again. "Cookie settings" in the
//   footer opens the choice again; withdrawing removes the Analytics cookies and stops Analytics on this page.
// - Consent Mode v2: everything denied by default; only analytics_storage is ever granted. Ads storage, ad user
//   data and ad personalisation stay denied, Google signals and ad personalisation are off.
(() => {
  "use strict";
  const KEY = "ks-consent";
  const VERSION = 1;
  const MAX_AGE_MS = 182 * 24 * 3600 * 1000;
  const COOKIE_SECONDS = 182 * 24 * 3600;
  const measurementId = document.querySelector('meta[name="ks-analytics"]')?.content || "";

  function readChoice() {
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || "null");
      if (!saved || saved.v !== VERSION || Date.now() - saved.t > MAX_AGE_MS) return null;
      return saved.analytics === true ? "granted" : "denied";
    } catch {
      return null;
    }
  }

  function saveChoice(analytics) {
    try {
      localStorage.setItem(KEY, JSON.stringify({ v: VERSION, analytics, t: Date.now() }));
    } catch {
      // Storage blocked: the choice holds for this page only.
    }
  }

  let analyticsStarted = false;
  function startAnalytics() {
    if (analyticsStarted || !/^G-[A-Z0-9]+$/.test(measurementId)) return;
    analyticsStarted = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag() {
      window.dataLayer.push(arguments);
    };
    const denied = { ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied", analytics_storage: "denied" };
    window.gtag("consent", "default", denied);
    window.gtag("set", "ads_data_redaction", true);
    window.gtag("consent", "update", { analytics_storage: "granted" });
    window.gtag("js", new Date());
    window.gtag("config", measurementId, {
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      cookie_expires: COOKIE_SECONDS,
      cookie_flags: "SameSite=Lax;Secure",
    });
    const script = document.createElement("script");
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
    document.head.appendChild(script);
  }

  function stopAnalytics() {
    if (window.gtag) window.gtag("consent", "update", { analytics_storage: "denied" });
    // Remove Google Analytics cookies (_ga, _ga_<id>) on this host and its parent domains.
    const host = location.hostname;
    const parts = host.split(".");
    const domains = [""];
    for (let i = 0; i < parts.length - 1; i++) domains.push(`; domain=.${parts.slice(i).join(".")}`);
    for (const cookie of document.cookie.split(";")) {
      const name = cookie.split("=")[0].trim();
      if (name === "_ga" || name.startsWith("_ga_") || name === "_gid") {
        for (const d of domains) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/${d}`;
      }
    }
    if (analyticsStarted) location.reload(); // the only way to unload a script already running
  }

  let banner = null;
  function showBanner(fromSettings) {
    if (banner) {
      banner.querySelector("button")?.focus();
      return;
    }
    const current = readChoice();
    banner = document.createElement("section");
    banner.className = "consent";
    banner.setAttribute("aria-labelledby", "consent-title");
    const state =
      current === "granted"
        ? "Right now: analytics are <strong>on</strong>."
        : current === "denied"
          ? "Right now: analytics are <strong>off</strong>."
          : "";
    banner.innerHTML = `
      <h2 id="consent-title">May we count visits?</h2>
      <p>With your OK, Google Analytics helps us see how many people visit and which guides help. It sets cookies
        on your device. Say no and the site works exactly the same. <a href="/legal/cookies">Cookie policy</a></p>
      ${state ? `<p class="consent-state">${state}</p>` : ""}
      <div class="btn-row">
        <button type="button" class="btn" data-choice="granted">Accept analytics</button>
        <button type="button" class="btn" data-choice="denied">No thanks</button>
      </div>`;
    banner.addEventListener("click", (event) => {
      const choice = event.target.closest("[data-choice]")?.dataset.choice;
      if (!choice) return;
      const before = readChoice();
      saveChoice(choice === "granted");
      banner.remove();
      banner = null;
      if (choice === "granted") startAnalytics();
      else if (before === "granted" || analyticsStarted) stopAnalytics();
      document.querySelector("[data-consent-open]")?.focus();
    });
    document.body.appendChild(banner);
    if (fromSettings) banner.querySelector("button").focus();
  }

  function init() {
    for (const open of document.querySelectorAll("[data-consent-open]")) {
      open.hidden = false;
      open.addEventListener("click", () => showBanner(true));
    }
    const choice = readChoice();
    if (choice === "granted") startAnalytics();
    else if (choice === null && navigator.globalPrivacyControl !== true) showBanner(false);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
