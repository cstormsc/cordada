// Dashboard charts: single-series horizontal bars (dataviz reference palette).
(function () {
  "use strict";
  const C = {
    series: "#2a78d6", text: "#52514e", muted: "#898781",
    grid: "#e1e0d9", axis: "#c3c2b7", surface: "#fcfcfb",
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
      emphasis: { itemStyle: { color: "#256abf" } },
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

  document.addEventListener("DOMContentLoaded", function () {
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
