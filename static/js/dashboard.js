// Dashboard charts: single-series horizontal bars (dataviz reference palette).
(function () {
  "use strict";
  const C = {
    series: "#6a89a7", text: "#56616d", muted: "#8a96a3",
    grid: "#dde3e9", axis: "#b9c3cd", surface: "#ffffff",
  };

  function data(id) {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  }

  function barChart(el, rows, opts) {
    if (!el || typeof echarts === "undefined") return;
    el.style.height = Math.max(120, rows.length * 34 + 48) + "px";
    const chart = echarts.init(el, null, { renderer: "svg" });
    const labels = rows.map((r) => r.label);
    const values = rows.map((r) => (r.value === null ? null : r.value));
    const series = {
      type: "bar",
      data: values,
      barMaxWidth: 24,
      itemStyle: { color: C.series, borderRadius: [0, 4, 4, 0] },
      label: {
        show: true, position: "right", color: C.text, fontSize: 12,
        formatter: (p) => (p.value === null || p.value === undefined ? "sin datos" : p.value),
      },
      emphasis: { itemStyle: { color: "#384959" } },
    };
    if (opts.threshold !== null && opts.threshold !== undefined) {
      series.markLine = {
        symbol: "none", silent: true,
        lineStyle: { color: C.muted, width: 1, type: "solid" },
        label: { show: false },  // the value is in the chart's subtitle
        data: [{ xAxis: opts.threshold }],
      };
    }
    chart.setOption({
      animation: false,
      grid: { left: 8, right: 56, top: 8, bottom: 24, containLabel: true },
      tooltip: {
        trigger: "item",
        formatter: (p) => p.name + ": <b>" + (p.value ?? "sin datos") + "</b>" + (opts.unit || ""),
      },
      xAxis: {
        type: "value", max: opts.max, minInterval: 1,
        axisLabel: { color: C.muted }, axisLine: { show: false },
        splitLine: { lineStyle: { color: C.grid, width: 1, type: "solid" } },
      },
      yAxis: {
        type: "category", data: labels, inverse: true,
        axisLabel: { color: C.text, width: 160, overflow: "truncate" },
        axisTick: { show: false }, axisLine: { lineStyle: { color: C.axis } },
      },
      series: [series],
    });
    window.addEventListener("resize", () => chart.resize());
  }

  // --- Each person arranges their own dashboard (saved per user and client). ---
  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  function setupLayout() {
    const dash = document.querySelector(".dash");
    const layout = document.querySelector(".dash-layout");
    const toggle = document.getElementById("dash-personalizar");
    if (!dash || !layout || !toggle) return;
    const url = layout.dataset.saveUrl;
    const columns = Array.from(layout.querySelectorAll(".dash-col"));
    const status = document.createElement("span");
    status.className = "dash-saved";
    status.setAttribute("aria-live", "polite");
    toggle.after(status);

    function hiddenIds() {
      return Array.from(document.querySelectorAll("[data-show]")).map((b) => b.dataset.show);
    }
    function current(hidden) {
      const out = { hidden: hidden || hiddenIds() };
      columns.forEach((col) => {
        out[col.dataset.col] = Array.from(col.querySelectorAll(":scope > .dash-mod"))
          .map((m) => m.dataset.mod);
      });
      return out;
    }
    function post(body) {
      status.textContent = "Guardando…";
      return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(body),
      }).then((r) => {
        // A redirect means the session ended and we landed on the login page.
        status.textContent = r.ok && !r.redirected ? "Guardado" : "No se pudo guardar";
        return r;
      }).catch(() => { status.textContent = "No se pudo guardar. Revisa tu conexión."; });
    }
    function changed() {
      window.dispatchEvent(new Event("resize"));  // charts follow their new width
      post(current());
    }
    function reloadEditing() {
      location.hash = "personalizar";
      location.reload();
    }

    const sortables = typeof Sortable === "undefined" ? [] : columns.map((col) =>
      Sortable.create(col, {
        group: "dash-modulos", handle: ".mod-handle", draggable: ".dash-mod",
        animation: 150, disabled: true, onEnd: changed,
      }));

    function setEditing(on) {
      dash.classList.toggle("editing", on);
      toggle.setAttribute("aria-pressed", on ? "true" : "false");
      toggle.textContent = on ? "Listo" : "Personalizar";
      sortables.forEach((s) => s.option("disabled", !on));
      if (!on) status.textContent = "";
    }
    toggle.addEventListener("click", () => setEditing(!dash.classList.contains("editing")));

    layout.addEventListener("click", (e) => {
      const btn = e.target.closest(".mod-btn");
      if (!btn) return;
      const mod = btn.closest(".dash-mod");
      const col = mod.parentElement;
      const act = btn.dataset.act;
      if (act === "up" && mod.previousElementSibling) col.insertBefore(mod, mod.previousElementSibling);
      else if (act === "down" && mod.nextElementSibling) col.insertBefore(mod.nextElementSibling, mod);
      else if (act === "swap") columns.find((c) => c !== col).appendChild(mod);
      else if (act === "hide") {
        const hidden = [...hiddenIds(), mod.dataset.mod];
        mod.remove();
        post(current(hidden)).then(reloadEditing);
        return;
      } else return;
      btn.focus();
      changed();
    });
    document.querySelectorAll("[data-show]").forEach((b) => b.addEventListener("click", () => {
      post(current(hiddenIds().filter((id) => id !== b.dataset.show))).then(reloadEditing);
    }));
    document.getElementById("dash-reset").addEventListener("click", () => {
      post({ reset: true }).then(() => { location.hash = ""; location.reload(); });
    });

    if (location.hash === "#personalizar") setEditing(true);
  }

  document.addEventListener("DOMContentLoaded", function () {
    setupLayout();
    const readiness = data("data-readiness");
    if (readiness) {
      barChart(document.getElementById("chart-readiness"), readiness.rows,
               { max: 100, threshold: readiness.threshold, unit: " / 100" });
    }
    const tickets = data("data-tickets");
    if (tickets) {
      barChart(document.getElementById("chart-tickets"), tickets, { unit: " tickets" });
    }
  });
})();
