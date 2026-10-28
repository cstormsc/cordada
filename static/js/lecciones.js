// Drag lessons or blocks to reorder them; the new order is saved at once.
(function () {
  function init() {
    if (typeof Sortable === "undefined") return;
    const token = document.querySelector("meta[name=csrf-token]").content;
    document.querySelectorAll("[data-sortable]").forEach(function (list) {
      Sortable.create(list, {
        animation: 150,
        delay: 150,
        delayOnTouchOnly: true,
        filter: "a, button",
        preventOnFilter: false,
        onEnd: function (evt) {
          if (evt.oldIndex === evt.newIndex) return;
          const ids = [...list.children].map((li) => li.dataset.id);
          fetch(list.dataset.sortable, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": token },
            body: JSON.stringify({ ids: ids }),
          }).then((r) => {
            if (!r.ok) window.location.reload();
          });
        },
      });
    });
  }
  document.addEventListener("DOMContentLoaded", init);
})();
