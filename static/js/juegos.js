// Learning games inside lessons. "Ordenar pasos": the steps arrive shuffled and the
// person moves them with the arrows until they are in order.
document.addEventListener("alpine:init", () => {
  Alpine.data("ordenar", (id) => ({
    pasos: [],
    revisado: false,
    enSuLugar: 0,
    init() {
      const titulos = JSON.parse(document.getElementById(id).textContent);
      const pasos = titulos.map((titulo, i) => ({ titulo, i }));
      do {
        for (let k = pasos.length - 1; k > 0; k--) {
          const j = Math.floor(Math.random() * (k + 1));
          [pasos[k], pasos[j]] = [pasos[j], pasos[k]];
        }
      } while (pasos.length > 1 && pasos.every((p, k) => p.i === k));
      this.pasos = pasos;
    },
    get listo() {
      return this.revisado && this.enSuLugar === this.pasos.length;
    },
    mover(k, d) {
      const j = k + d;
      if (j < 0 || j >= this.pasos.length) return;
      [this.pasos[k], this.pasos[j]] = [this.pasos[j], this.pasos[k]];
      this.revisado = false;
      // Keep the focus on the step that moved, so the arrows can be pressed again.
      this.$nextTick(() => {
        // At the top or bottom that arrow turns off: fall back to the other one.
        const boton = this.$root.querySelectorAll(`[data-mover="${d}"]`)[j];
        const otro = this.$root.querySelectorAll(`[data-mover="${-d}"]`)[j];
        (boton && !boton.disabled ? boton : otro)?.focus();
      });
    },
    comprobar() {
      this.revisado = true;
      this.enSuLugar = this.pasos.filter((p, k) => p.i === k).length;
    },
  }));
});
