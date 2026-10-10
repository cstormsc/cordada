// "?" help reminders: show the definition on hover, keyboard focus or tap. The bubble is
// positioned on the page (not inside its box), so tables that scroll don't clip it.
(function () {
  "use strict";
  let open = null;
  let hideTimer = null;

  function place(btn, tip) {
    tip.style.left = "0px";
    tip.style.top = "0px";
    const b = btn.getBoundingClientRect();
    const t = tip.getBoundingClientRect();
    const margin = 8;
    let left = Math.min(Math.max(margin, b.left + b.width / 2 - t.width / 2), innerWidth - t.width - margin);
    let top = b.bottom + 6;
    if (top + t.height > innerHeight - margin && b.top - t.height - 6 > margin) top = b.top - t.height - 6;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }

  function show(btn) {
    clearTimeout(hideTimer);
    const tip = document.getElementById(btn.getAttribute("aria-describedby"));
    if (!tip) return;
    if (open && open !== tip) hide();
    tip.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    place(btn, tip);
    open = tip;
  }

  function hide() {
    if (!open) return;
    open.hidden = true;
    const btn = document.querySelector('[aria-describedby="' + open.id + '"]');
    if (btn) btn.setAttribute("aria-expanded", "false");
    open = null;
  }

  function hideSoon() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hide, 150);
  }

  const inHelp = (el) => el && el.closest && el.closest(".ayuda");

  document.addEventListener("mouseover", (e) => {
    const btn = e.target.closest && e.target.closest(".ayuda-btn");
    if (btn) show(btn);
    else if (inHelp(e.target)) clearTimeout(hideTimer);  // pointer moved onto the bubble
  });
  document.addEventListener("mouseout", (e) => {
    if (inHelp(e.target) && !inHelp(e.relatedTarget)) hideSoon();
  });
  document.addEventListener("focusin", (e) => {
    if (e.target.classList && e.target.classList.contains("ayuda-btn")) show(e.target);
  });
  document.addEventListener("focusout", (e) => {
    if (inHelp(e.target) && !inHelp(e.relatedTarget)) hideSoon();
  });
  document.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest(".ayuda-btn");
    if (btn) {  // taps on touch screens
      e.preventDefault();
      const tip = document.getElementById(btn.getAttribute("aria-describedby"));
      if (open === tip) hide(); else show(btn);
    } else if (!inHelp(e.target)) hide();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
  window.addEventListener("scroll", hide, { passive: true, capture: true });
  window.addEventListener("resize", hide);
})();
