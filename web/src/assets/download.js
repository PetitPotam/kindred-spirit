// The Download page's buttons. Nothing is asked of GitHub until a visitor presses one: then the browser asks GitHub's
// API for the project's releases, finds the newest one that carries Kindred Spirit Setup for that chip (pre-releases
// count: the beta is one), and starts that download. Without JavaScript, or if GitHub doesn't answer, each button is a
// plain link to the releases page.
(() => {
  "use strict";
  const box = document.querySelector("[data-download]");
  const status = document.querySelector("[data-download-status]");
  if (!box || !status) return;

  const say = (text) => {
    status.textContent = text;
  };

  // The newest release (GitHub lists them newest first) with a "Kindred-Spirit-Setup-<version>-macos-<chip>.dmg".
  function find(releases, chip) {
    const suffix = `-macos-${chip}.dmg`;
    for (const release of releases) {
      if (release.draft) continue;
      const asset = (release.assets || []).find((a) => a.name.startsWith("Kindred-Spirit-Setup-") && a.name.endsWith(suffix));
      if (asset) return { url: asset.browser_download_url, name: asset.name, version: release.tag_name };
    }
    return null;
  }

  box.addEventListener("click", async (event) => {
    const button = event.target.closest("a[data-chip]");
    if (!button) return;
    event.preventDefault();
    const fallback = button.href;
    say("Finding the newest release on GitHub…");
    try {
      const response = await fetch(box.dataset.api, { headers: { Accept: "application/vnd.github+json" } });
      if (!response.ok) throw new Error(`GitHub answered ${response.status}`);
      const found = find(await response.json(), button.dataset.chip);
      if (!found) {
        say("No release carries the Setup yet. Until one does, the manual setup (at the end of this page) works.");
        return;
      }
      say(`Downloading ${found.name} (${found.version}) from GitHub. Then open it from your Downloads folder.`);
      window.location.href = found.url;
    } catch {
      say("GitHub didn't answer, so the releases page is opening: pick the .dmg for your Mac there.");
      window.location.href = fallback;
    }
  });
})();
