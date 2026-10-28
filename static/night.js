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

  function init() {
    var letters = document.querySelectorAll(".letter[data-draft]");
    for (var i = 0; i < letters.length; i++) wireLetter(letters[i]);
    openHashTarget();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

/* S1b replay: State A performs the night beat by beat, then lands on B. */
(function () {
  "use strict";
  window.__nightShiftAlive = 1;
  var replay = document.getElementById("replay");
  var note = document.getElementById("state-question");
  function showNote() { if (note) note.hidden = false; }
  if (!replay) return;
  var root = document.documentElement;
  var reduced = true;
  try {
    reduced = window.matchMedia
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : true;
  } catch (e) { reduced = true; }
  if (reduced || !root.classList.contains("rv")) {
    root.classList.remove("rv");
    showNote();
    return;
  }
  var speed = 1;
  try {
    var wanted = new URLSearchParams(window.location.search).get("speed");
    if (wanted === "2" || wanted === "4") speed = +wanted;
  } catch (e) { speed = 1; }

  /* The one mapping from the night's virtual beats to wall time (ms).
     Beats are the events' own virtual times; dwells between clock groups
     pad the replay to 20.5 s while in-group staggers stay on spec. */
  var VT_BASE = {"21:30": 500, "22:30": 3000, "00:38": 6500,
                 "00:39": 12000, "00:47": 20500};
  var DWELL = {handoff: 0, reads: 0, verdict: 350, revised: 0, sheet: 1500,
               sheetcap: 1500, diff: 3000, beatcap: 3400, decision: 4000,
               deadline: 5250, skip: 0};
  function wallAt(vt, slot, index) {
    var base = VT_BASE[vt] || 0;
    if (slot === "check") return base + (index || 0) * 450;
    if (slot === "result") return base + (index || 0) * 450 + 250;
    return base + (DWELL[slot] || 0);
  }

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $all(sel, ctx) {
    return Array.prototype.slice.call((ctx || document).querySelectorAll(sel));
  }
  function reveal(el, still) {
    if (!el) return;
    el.classList.add("on");
    if (!still) el.classList.add("feed-anim");
  }

  var clockEl = $(".clockblock .clock") || $(".clock");
  var dotEl = $(".dot");
  var trackEl = $(".tl");
  var evtag = $(".evtag");
  var curVt = "21:30";
  function pctOf(vt) {
    var parts = String(vt).split(":");
    var mins = (+parts[0]) * 60 + (+parts[1]);
    var delta = mins - (21 * 60 + 30);
    if (delta < 0) delta += 24 * 60;
    return Math.max(0, Math.min(100, delta * 100 / 720));
  }
  function dotTo(vt) {
    if (!dotEl || !trackEl) return;
    var width = trackEl.clientWidth || 0;
    dotEl.style.transform = "translateX(" + (width * pctOf(vt) / 100) + "px)";
  }
  function setClock(vt, amber) {
    curVt = vt;
    if (clockEl) {
      var parts = String(vt).split(":");
      var h = $(".h", clockEl);
      var m = $(".m", clockEl);
      if (h) h.textContent = parts[0];
      if (m) m.textContent = parts[1] || "";
      clockEl.classList.add("dip");
      setTimeout(function () { clockEl.classList.remove("dip"); }, 90);
      var tl = $(".tl");
      if (tl) tl.setAttribute("aria-label",
        "Night timeline from 21:30 to 09:30, now at " + vt);
    }
    if (amber && dotEl) dotEl.classList.add("amber");
    dotTo(vt);
  }
  if (dotEl) {
    dotEl.style.left = "0px";
    dotTo("21:30");
  }
  window.addEventListener("resize", function () { dotTo(curVt); });

  var feedSec = $('[data-rv-sec="feed"]', replay);
  var beatSec = $('[data-rv-sec="beat"]', replay);
  var howSec = $('[data-rv-sec="how"]', replay);
  var decSec = $('[data-rv-sec="decision"]', replay);
  var checksFold = $('[data-rv="checks-fold"]', replay);
  var cards = $all('[data-rv="check"]', replay);
  function item(slot) { return $('[data-rv="' + slot + '"]', replay); }

  var state = {done: false, manual: false, vnow: 0, fired: 0};
  function finish() {
    if (state.done) return;
    state.done = true;
    setClock("00:47", true);
    if (evtag && evtag.parentNode) evtag.parentNode.removeChild(evtag);
    if (replay.parentNode) replay.parentNode.removeChild(replay);
    document.body.classList.add("state-b");
    showNote();
    var paper = note ? $(".note", note) : null;
    if (paper) paper.classList.add("settle");
    try { window.scrollTo(0, 0); } catch (e) {}
    document.body.setAttribute("data-replay-done", "1");
  }

  var plan = [];
  function at(vt, slot, index, fn) {
    plan.push({at: wallAt(vt, slot, index), fn: fn});
  }
  at("21:30", "handoff", 0, function () {
    reveal(feedSec, true); reveal(item("handoff"));
    reveal(howSec, true); reveal(item("skip"), true);
  });
  at("22:30", "reads", 0, function () {
    setClock("22:30", false); reveal(item("reads"));
  });
  at("22:30", "verdict", 0, function () { reveal(item("verdict")); });
  at("00:38", "revised", 0, function () {
    setClock("00:38", false);
    if (evtag) evtag.hidden = false;
    reveal(item("revised"));
  });
  at("00:38", "sheet", 0, function () {
    reveal(beatSec, true); reveal(item("sheet"), true);
    reveal(item("sheetcap"));
  });
  at("00:38", "diff", 0, function () { reveal(item("diff")); });
  at("00:38", "beatcap", 0, function () { reveal(item("beatcap")); });
  cards.forEach(function (card, i) {
    at("00:39", "check", i, function () {
      if (i === 0) {
        setClock("00:39", false);
        reveal(howSec, true); reveal(checksFold, true);
      }
      reveal(card);
    });
    at("00:39", "result", i, function () {
      var yn = $(".yn", card);
      if (yn) yn.classList.add("on");
    });
  });
  at("00:39", "decision", 0, function () {
    reveal(decSec, true); reveal(item("decision"));
  });
  at("00:39", "deadline", 0, function () { reveal(item("deadline")); });
  at("00:47", "finish", 0, finish);

  plan.sort(function (a, b) { return a.at - b.at; });
  var duration = 0;
  for (var p = 0; p < plan.length; p++) {
    if (plan[p].at > duration) duration = plan[p].at;
  }
  var timers = plan.map(function (ev) {
    return setTimeout(function () { if (!state.manual) ev.fn(); },
                      ev.at / speed);
  });
  window.__nightShiftTick = function (ms) {
    if (!state.manual) {
      state.manual = true;
      for (var i = 0; i < timers.length; i++) clearTimeout(timers[i]);
    }
    state.vnow += ms;
    while (state.fired < plan.length &&
           plan[state.fired].at / speed <= state.vnow) {
      plan[state.fired].fn();
      state.fired++;
    }
    return {vnow: state.vnow, done: state.done};
  };
  window.__nightShiftReplay = {duration: duration, speed: speed,
                               state: state};
})();

/* S1b dawn: the clock jumps to 07:00, the band rises, then morning. */
(function () {
  "use strict";
  var dawn = document.getElementById("dawn");
  if (!dawn) return;
  var band = dawn.querySelector(".dawn-band");
  var veil = dawn.querySelector(".dawn-veil");
  var target = dawn.getAttribute("data-target") || "";
  var RISE = 2500, SETTLE = 400, LEAVE = 3000;
  var reduced = true;
  try {
    reduced = window.matchMedia
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : true;
  } catch (e) { reduced = true; }
  function pctOf(vt) {
    var parts = String(vt).split(":");
    var mins = (+parts[0]) * 60 + (+parts[1]);
    var delta = mins - (21 * 60 + 30);
    if (delta < 0) delta += 24 * 60;
    return Math.max(0, Math.min(100, delta * 100 / 720));
  }
  function jumpClock() {
    var clockEl = document.querySelector(".clockblock .clock")
      || document.querySelector(".clock");
    if (clockEl) {
      var h = clockEl.querySelector(".h");
      var m = clockEl.querySelector(".m");
      if (h) h.textContent = "07";
      if (m) m.textContent = "00";
      var tl = document.querySelector(".tl");
      if (tl) tl.setAttribute("aria-label",
        "Night timeline from 21:30 to 09:30, now at 07:00");
    }
    var dot = document.querySelector(".dot");
    var track = document.querySelector(".tl");
    if (dot && track && track.clientWidth) {
      dot.style.left = "0px";
      dot.style.transform = "translateX("
        + (track.clientWidth * pctOf("07:00") / 100) + "px)";
    } else if (dot) {
      dot.style.left = pctOf("07:00") + "%";
    }
  }
  function paintRise(x) {
    if (band) band.style.transform = "translateY(" + (101 - 101 * x) + "%)";
  }
  function paintSettle(x) {
    if (veil) veil.style.opacity = x.toFixed(3);
  }
  var state = {left: false, manual: false, vnow: 0};
  function leave() {
    if (state.left) return;
    state.left = true;
    if (target) {
      try { window.location.assign(target); } catch (e) {}
    }
  }
  jumpClock();
  if (reduced) {
    paintRise(1);
    paintSettle(1);
    setTimeout(leave, 120);
    window.__nightShiftTick = function () { return {vnow: 0, done: true}; };
    return;
  }
  if (band) band.classList.add("wall");
  if (veil) veil.classList.add("wall");
  if (window.requestAnimationFrame) {
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () { paintRise(1); });
    });
  } else {
    paintRise(1);
  }
  setTimeout(function () { paintSettle(1); }, RISE);
  setTimeout(leave, LEAVE);
  window.__nightShiftTick = function (ms) {
    if (!state.manual) {
      state.manual = true;
      if (band) band.classList.remove("wall");
      if (veil) veil.classList.remove("wall");
    }
    state.vnow += ms;
    paintRise(Math.min(1, state.vnow / RISE));
    paintSettle(Math.max(0, Math.min(1, (state.vnow - RISE) / SETTLE)));
    if (state.vnow >= LEAVE) leave();
    return {vnow: state.vnow, done: state.left};
  };
  window.__nightShiftDawn = {rise: RISE, settle: SETTLE, leave: LEAVE};
})();

/* S1b film: the cue sheet plays the beats; tick drives it deterministically.
   Film is an explicit opt-in to motion (?film=1), so it auto-plays; the
   render script and tests advance it with __nightShiftTick instead. */
(function () {
  "use strict";
  var stage = document.getElementById("fstage");
  if (!stage) return;
  var cuesEl = document.getElementById("cues");
  if (!cuesEl) return;
  var beats = JSON.parse(cuesEl.textContent).beats;
  var only = stage.getAttribute("data-beat") || "";
  var sections = Array.prototype.slice.call(
    stage.querySelectorAll(".fbeat"));
  var clockH = document.querySelector(".fclock-t .h");
  var clockM = document.querySelector(".fclock-t .m");
  var kick = document.querySelector(".fkick");
  var timeline = [];
  var cursor = 0;
  beats.forEach(function (beat) {
    if (only && beat.name !== only) return;
    timeline.push({
      name: beat.name, ms: beat.ms, start: cursor,
      el: stage.querySelector('[data-beat="' + beat.name + '"]')
    });
    cursor += beat.ms;
  });
  var total = cursor;
  function stagger(el, local, ms, sel) {
    if (!el) return;
    var items = el.querySelectorAll(sel);
    var step = items.length ? ms / items.length : ms;
    for (var i = 0; i < items.length; i++) {
      if (local >= i * step) items[i].classList.add("on");
      else items[i].classList.remove("on");
    }
  }
  function renderAt(vnow) {
    vnow = Math.max(0, Math.min(total, vnow));
    var cur = timeline[0];
    var index = 0;
    for (var i = 0; i < timeline.length; i++) {
      if (vnow >= timeline[i].start) { cur = timeline[i]; index = i; }
    }
    for (var j = 0; j < sections.length; j++) {
      sections[j].classList.remove("on");
    }
    if (cur.el) cur.el.classList.add("on");
    var local = vnow - cur.start;
    var p = cur.ms ? local / cur.ms : 1;
    if (cur.el) {
      var parts = (cur.el.getAttribute("data-clock") || "").split(":");
      if (clockH) clockH.textContent = parts[0] || "";
      if (clockM) clockM.textContent = parts[1] || "";
      if (kick) kick.textContent = cur.el.getAttribute("data-kicker") || "";
      var paper = cur.el.getAttribute("data-theme") === "paper";
      document.body.classList.toggle("paper", paper);
      document.body.classList.toggle("night", !paper);
    }
    stagger(cur.el, local, cur.ms, "[data-frow]");
    stagger(cur.el, local, cur.ms, "[data-fcard]");
    if (cur.name === "sheet" && cur.el) {
      var sheet = cur.el.querySelector(".fsheet");
      if (sheet) sheet.style.transform = "scale(" + (1 + 0.06 * p).toFixed(4)
        + ")";
    }
    if (cur.name === "dawn" && cur.el) {
      var band = cur.el.querySelector(".fdawn-band");
      var veil = cur.el.querySelector(".fdawn-veil");
      var rise = Math.min(1, local / 9000);
      var settle = Math.max(0, Math.min(1, (local - 9000) / 1500));
      if (band) band.style.transform = "translateY(" + (101 - 101 * rise)
        + "%)";
      if (veil) veil.style.opacity = settle.toFixed(3);
    }
    return {beat: cur.name, index: index, local: local, total: total};
  }
  var manual = false;
  var vnow = 0;
  var raf = 0;
  var iv = 0;
  function frame(now) {
    if (manual) return;
    if (!frame.t0) frame.t0 = now;
    vnow = now - frame.t0;
    renderAt(vnow);
    if (vnow < total) raf = window.requestAnimationFrame(frame);
  }
  renderAt(0);
  if (window.requestAnimationFrame) {
    raf = window.requestAnimationFrame(frame);
  } else {
    iv = setInterval(function () {
      vnow += 100;
      renderAt(vnow);
      if (vnow >= total) clearInterval(iv);
    }, 100);
  }
  window.__nightShiftTick = function (ms) {
    if (!manual) {
      manual = true;
      if (raf && window.cancelAnimationFrame) {
        window.cancelAnimationFrame(raf);
      }
      if (iv) clearInterval(iv);
    }
    vnow += ms;
    return renderAt(vnow);
  };
  window.__nightShiftFilm = {total: total, beats: beats, only: only};
})();
