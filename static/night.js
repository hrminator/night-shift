/* Night Shift: approval flip + deep-link helpers. Vanilla, no framework. */
(function () {
  "use strict";
  var APPROVE = "Approve this exact text";
  var STALE = "Your OK doesn't cover this version";

  function wireLetter(letter) {
    var box = letter.querySelector("textarea.edit");
    var btn = letter.querySelector("button[data-approve]");
    if (!box || !btn) return;
    var original = box.defaultValue;
    var save = letter.querySelector("button[data-save]");
    function render() {
      var edited = box.value !== original;
      btn.textContent = edited ? STALE : APPROVE;
      if (edited) {
        btn.classList.add("is-stale");
        btn.setAttribute("disabled", "disabled");
      } else {
        btn.classList.remove("is-stale");
        btn.removeAttribute("disabled");
      }
      if (save) {
        if (edited) save.removeAttribute("disabled");
        else save.setAttribute("disabled", "disabled");
      }
    }
    box.addEventListener("input", render);
    render();
  }

  function openHashTarget() {
    var hash = "";
    try { hash = window.location.hash || ""; } catch (e) { hash = ""; }
    if (!hash || hash.length < 2) return;
    var id = hash.slice(1);
    var el = document.getElementById(id);
    if (!el) return;
    var details = el.closest ? el.closest("details") : null;
    if (details && !details.open) details.open = true;
    if (el.tagName === "DETAILS" && !el.open) el.open = true;
  }

  function scrollToState() {
    var state = "";
    try {
      state = new URLSearchParams(window.location.search).get("state") || "";
    } catch (e) { state = ""; }
    if (state !== "question" && state !== "morning" && state !== "night") return;
    var anchor = document.getElementById("state-" + state);
    if (!anchor) return;
    var reduce = false;
    try {
      reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (e) { reduce = false; }
    try {
      anchor.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    } catch (e) { /* older browsers: leave the server-rendered position */ }
  }

  function init() {
    var letters = document.querySelectorAll(".letter[data-draft]");
    for (var i = 0; i < letters.length; i++) wireLetter(letters[i]);
    openHashTarget();
    scrollToState();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
