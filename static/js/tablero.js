// Kanban board for impacts: drag a card to change its state.
// The server enforces the lifecycle; the board refreshes from it after every move.
(function () {
  "use strict";

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  function showMessage(text, ok) {
    const box = document.getElementById("board-msg");
    if (!box) return;
    box.innerHTML = "";
    const p = document.createElement("p");
    p.className = "msg " + (ok ? "msg-success" : "msg-error");
    p.textContent = text;
    box.appendChild(p);
  }

  function refresh(board) {
    htmx.ajax("GET", board.dataset.refreshUrl, { target: "#board", swap: "outerHTML" });
  }

  function move(board, numero, hacia, motivo) {
    const body = new FormData();
    body.append("hacia", hacia);
    body.append("motivo", motivo || "");
    const url = board.dataset.moveUrl.replace("/0/", "/" + numero + "/");
    fetch(url, { method: "POST", body: body, headers: { "X-CSRFToken": csrfToken() } })
      .then((r) => r.json())
      .then((data) => {
        showMessage(data.ok ? data.message : (data.codigo ? data.codigo + ": " : "") +
          data.errors.join(" "), data.ok);
      })
      .catch(() => showMessage("No se pudo guardar el cambio. Revisa tu conexión.", false))
      .finally(() => refresh(board));
  }

  function askReason(board, numero, hacia, columnLabel) {
    const dialog = document.getElementById("reason-dialog");
    const textarea = dialog.querySelector("textarea");
    dialog.querySelector("#reason-title").textContent = columnLabel;
    textarea.value = "";
    dialog.onclose = function () {
      if (dialog.returnValue === "ok" && textarea.value.trim()) {
        move(board, numero, hacia, textarea.value.trim());
      } else {
        refresh(board); // put the card back
      }
    };
    dialog.showModal();
    textarea.focus();
  }

  function allowedFor(el) {
    return (el.dataset.allowed || "").split(",").filter(Boolean);
  }

  function init(root) {
    const board = root.id === "board" ? root : root.querySelector && root.querySelector("#board");
    if (!board || !board.dataset.editable || typeof Sortable === "undefined") return;
    const columns = board.querySelectorAll(".kcol");

    board.querySelectorAll(".kcol-cards").forEach(function (list) {
      Sortable.create(list, {
        group: {
          name: "impactos",
          put: function (to, from, dragEl) {
            return allowedFor(dragEl).includes(to.el.dataset.estado);
          },
        },
        sort: false,
        animation: 150,
        delay: 150,
        delayOnTouchOnly: true,
        onStart: function (evt) {
          const allowed = allowedFor(evt.item);
          board.classList.add("dragging");
          columns.forEach((c) => c.classList.toggle("drop-ok", allowed.includes(c.dataset.estado)));
        },
        onEnd: function (evt) {
          board.classList.remove("dragging");
          columns.forEach((c) => c.classList.remove("drop-ok"));
          if (evt.from === evt.to) return;
          const hacia = evt.to.dataset.estado;
          const numero = evt.item.dataset.numero;
          const needsReason = (evt.item.dataset.needsReason || "").split(",").includes(hacia);
          if (needsReason) {
            const label = evt.to.closest(".kcol").querySelector(".kcol-head span").textContent;
            askReason(board, numero, hacia, label);
          } else {
            move(board, numero, hacia, "");
          }
        },
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => init(document));
  document.addEventListener("htmx:load", (evt) => init(evt.detail.elt));
})();
