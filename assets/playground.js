// Guard Spec playground: sends the text to the playground proxy
// (POST {api}/v1/scan) and shows the decision. No storage, no cookies, no
// third-party script unless Turnstile is configured. Text from the server is
// written with textContent only.
(function () {
  "use strict";
  var form = document.getElementById("pg-form");
  if (!form) return;
  var t = JSON.parse(document.getElementById("pg-i18n").textContent);
  var data = JSON.parse(document.getElementById("pg-data").textContent);
  var api = form.getAttribute("data-api");
  var max = parseInt(form.getAttribute("data-max"), 10) || 4096;
  var sitekey = form.getAttribute("data-sitekey");
  var $ = function (id) { return document.getElementById(id); };
  var text = $("pg-text"), count = $("pg-count"), scanBtn = $("pg-scan");
  var enc = new TextEncoder();
  var widget = null;

  function fmt(s, vals) {
    return s.replace(/\{(\w+)\}/g, function (m, k) { return k in vals ? vals[k] : m; });
  }
  function bytes() { return enc.encode(text.value).length; }
  function kind() { return form.querySelector("input[name=kind]:checked").value; }
  function setKind(k) { form.querySelector("input[name=kind][value=" + k + "]").checked = true; }
  function num(x) { return (Math.round(x * 1000) / 1000).toFixed(3); }

  function updateCount() {
    var n = bytes();
    count.textContent = fmt(t.count, { n: n, max: max });
    count.classList.toggle("over", n > max);
  }
  text.addEventListener("input", updateCount);
  updateCount();

  // Samples. The "hidden" part is appended as Unicode tag characters
  // (invisible), the way such payloads arrive in real text.
  var chips = $("pg-chips");
  data.samples.forEach(function (s) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "chip chip-" + s.kind;
    b.textContent = t["s_" + s.id] || s.id;
    b.addEventListener("click", function () {
      var v = s.text;
      if (s.hidden) {
        v += Array.from(s.hidden).map(function (c) {
          return String.fromCodePoint(0xE0000 + c.codePointAt(0));
        }).join("");
      }
      text.value = v;
      setKind(s.kind);
      updateCount();
      scan();
    });
    chips.appendChild(b);
  });

  if (sitekey && window.turnstile === undefined) {
    window.addEventListener("load", renderTurnstile);
  } else if (sitekey) {
    renderTurnstile();
  }
  function renderTurnstile() {
    if (window.turnstile && widget === null) {
      widget = window.turnstile.render("#pg-turnstile", { sitekey: sitekey, size: "flexible" });
    }
  }

  function showError(msg) {
    $("pg-error").textContent = msg;
    $("pg-error").hidden = false;
  }

  function fill(list, items) {
    list.textContent = "";
    items.forEach(function (x) {
      var li = document.createElement("li");
      li.textContent = x;
      list.appendChild(li);
    });
  }

  function bar(name, value) {
    var row = document.createElement("div");
    row.className = "pg-layer";
    var label = document.createElement("span");
    label.textContent = name;
    var track = document.createElement("div");
    track.className = "pg-bar";
    var fillEl = document.createElement("i");
    var val = document.createElement("b");
    if (value === null || value === undefined) {
      row.classList.add("off");
      val.textContent = t.not_run;
    } else {
      fillEl.style.width = Math.max(1, Math.min(100, value * 100)) + "%";
      if (value >= data.threshold) fillEl.className = "hi";
      else if (value >= 0.5) fillEl.className = "mid";
      val.textContent = num(value);
    }
    track.appendChild(fillEl);
    row.appendChild(label);
    row.appendChild(track);
    row.appendChild(val);
    return row;
  }

  function render(r) {
    var blocked = r.decision === "blocked";
    var badge = $("pg-badge");
    badge.textContent = blocked ? t.blocked : t.allowed;
    badge.className = "pg-badge " + (blocked ? "block" : "allow");
    $("pg-result").className = "card pg-result " + (blocked ? "is-block" : "is-allow");
    $("pg-kind-out").textContent = t["kind_out_" + r.kind] || r.kind;
    $("pg-score").textContent = num(r.score);
    var sb = $("pg-score-bar");
    sb.style.width = Math.max(1, Math.min(100, r.score * 100)) + "%";
    sb.className = r.score >= data.threshold ? "hi" : r.score >= 0.5 ? "mid" : "";

    var layers = $("pg-layers");
    layers.textContent = "";
    if (r.layers) {
      layers.appendChild(bar(t.l1, r.layers.l1));
      layers.appendChild(bar(t.l2, r.layers.l2));
      layers.appendChild(bar(t.l3, r.layers.l3));
    } else {
      var p = document.createElement("p");
      p.className = "pg-muted";
      p.textContent = t.no_layers;
      layers.appendChild(p);
    }

    $("pg-label").textContent = r.label;
    var by = r.decided_by ? (t["by_" + r.decided_by] || r.decided_by) : "—";
    var why = r.reason ? t["why_" + r.reason] : "";
    $("pg-decided").textContent = why ? by + " · " + why : by;
    $("pg-latency").textContent = r.latency_ms + " ms";

    var notes = [];
    if (r.sanitizer) {
      (r.sanitizer.findings || []).forEach(function (f) {
        if (f === "removed_chars") notes.push(fmt(t.f_removed_chars, { n: r.sanitizer.bytes_removed }));
        else if (t["f_" + f]) notes.push(t["f_" + f]);
      });
      if (r.sanitizer.anomaly_score > 0) notes.push(fmt(t.anomaly, { n: num(r.sanitizer.anomaly_score) }));
      if (!notes.length) notes.push(t.san_clean);
    } else {
      notes.push(t.san_tool);
    }
    fill($("pg-san"), notes);

    var sig = r.signals || [];
    fill($("pg-sig"), sig);
    $("pg-sig-wrap").hidden = !sig.length;
    // Rules explain a high score; for an allowed text or a sanitizer block
    // they are weak hints and would only confuse.
    var rules = blocked && r.decided_by !== "sanitizer" ? (r.rules || []) : [];
    fill($("pg-rules"), rules);
    $("pg-rules-wrap").hidden = !rules.length;

    $("pg-empty").hidden = true;
    $("pg-out").hidden = false;
  }

  var busy = false;
  function scan() {
    if (busy) return;
    $("pg-error").hidden = true;
    if (!text.value.trim()) { showError(t.err_empty); return; }
    if (bytes() > max) { showError(fmt(t.err_too_long, { max: max })); return; }
    var body = { text: text.value, kind: kind() };
    if (sitekey && window.turnstile && widget !== null) {
      body.turnstile_token = window.turnstile.getResponse(widget) || "";
    }
    busy = true;
    scanBtn.disabled = true;
    scanBtn.querySelector("span").textContent = t.scanning;
    $("pg-result").setAttribute("aria-busy", "true");
    fetch(api + "/v1/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer"
    }).then(function (resp) {
      return resp.json().catch(function () { return {}; }).then(function (j) {
        if (resp.ok) { render(j); return; }
        var s = resp.headers.get("Retry-After") || "60";
        if (resp.status === 429) showError(fmt(t.err_rate, { s: s }));
        else if (resp.status === 503) showError(t.err_busy);
        else if (resp.status === 413) showError(fmt(t.err_too_long, { max: max }));
        else if (j.error === "challenge_failed") showError(t.err_challenge);
        else showError(t.err_generic);
      });
    }).catch(function () {
      showError(t.err_network);
    }).then(function () {
      busy = false;
      scanBtn.disabled = false;
      scanBtn.querySelector("span").textContent = t.scan;
      $("pg-result").removeAttribute("aria-busy");
      if (sitekey && window.turnstile && widget !== null) window.turnstile.reset(widget);
    });
  }

  form.addEventListener("submit", function (e) { e.preventDefault(); scan(); });
  text.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); scan(); }
  });
})();
