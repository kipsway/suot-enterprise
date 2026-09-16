/* SUOT Neo — пакетная печать (Часть 13, рефактор Части 17). */

window.batchPrint = function () {
  return {
    open: false, key: "", selectedIds: [], busy: false,
    watermark: "", merge: true, result: null, error: "",
    icons: window.ICONS,
    t: (k) => I18N.t(k),

    openBatch(e) {
      this.open = true;
      this.key = e.detail.key;
      this.selectedIds = e.detail.ids;
      this.result = null;
      this.error = "";
      const wm = window.SUOT_WATERMARK || "";
      if (!this.watermark && wm) this.watermark = wm;
    },

    async doPrint() {
      this.busy = true;
      this.error = "";
      try {
        const tok = localStorage.getItem("suot_token") ||
                    sessionStorage.getItem("suot_token_session") || "";
        const r = await fetch("/api/print/pdf", {
          method: "POST",
          headers: { "Authorization": "Bearer " + tok,
                     "Content-Type": "application/json" },
          body: JSON.stringify({
            table: this.key,
            record_ids: this.selectedIds,
            watermark_text: this.watermark,
            merge: this.merge,
          }),
        });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const blob = await r.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "batch.pdf";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(a.href);
        this.result = { count: this.selectedIds.length };
        if (window.Sounds) Sounds.play("success");
      } catch (e) {
        this.error = e.message;
        if (window.Sounds) Sounds.play("error");
      }
      this.busy = false;
    },
  };
};
