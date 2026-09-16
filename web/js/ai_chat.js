/* SUOT Neo — AI-центр (Часть 27). Треды, стриминг, агент, diff, ping. */

window.aiChat = function () {
  return {
    /* ── state ── */
    messages: [],               // {role, content}
    input: "",
    busy: false,
    settingsOpen: false,
    settings: { provider: "ollama", base_url: "http://localhost:11434",
                api_key: "", model: "llama3" },
    agentConfirm: null,         // {action, params, type, table, count, diff}
    pingResult: null,           // {ok, ms, provider, error, url}

    /* ── thread history ── */
    threads: [],                // [{id, title, preview, message_count, created_at}]
    activeThreadId: 0,
    threadTitle: "",            // заголовок нового / редактируемого треда
    renamingThreadId: 0,
    renamingTitle: "",

    icons: window.ICONS,
    t: (k) => I18N.t(k),
    ru: (a, b) => I18N.lang === "ru" ? a : b,

    /* ── init ── */
    async init() {
      if (!API.hasToken()) return;
      try {
        const s = await API.get("/ai/settings");
        this.settings = s;
      } catch (_) {}
      await this.loadThreads();
    },

    /* ── настройки ── */
    openSettings() {
      this.settingsOpen = !this.settingsOpen;
      if (this.settingsOpen) {
        API.get("/ai/settings").then((s) => { this.settings = s; });
      }
    },
    async saveSettings() {
      try {
        await API.post("/ai/settings", this.settings);
        Toast.show(I18N.t("tbl.savedOk"), "success");
        this.settingsOpen = false;
      } catch (e) { Toast.show(e.message, "error"); }
    },

    /* ── ping провайдера ── */
    async doPing() {
      this.pingResult = null;
      try {
        this.pingResult = await API.post("/ai/ping", {});
      } catch (e) {
        this.pingResult = { ok: false, ms: 0, provider: this.settings.provider,
                            url: this.settings.base_url, error: e.message };
      }
    },

    /* ── threads ── */
    async loadThreads() {
      try {
        const r = await API.get("/ai/threads");
        this.threads = r.items || [];
      } catch (_) { this.threads = []; }
    },
    async selectThread(id) {
      if (this.activeThreadId === id) return;
      this.activeThreadId = id;
      this.messages = [];
      if (!id) return;
      try {
        const r = await API.get("/ai/threads/" + id + "/messages");
        this.messages = (r.items || []).map((m) => ({ role: m.role, content: m.content }));
      } catch (_) {}
      this.$nextTick(() => { this._scrollBottom(); });
    },
    async createThread() {
      const title = this.threadTitle.trim();
      this.threadTitle = "";
      try {
        const r = await API.post("/ai/threads", { title });
        if (r.id) {
          await this.loadThreads();
          this.activeThreadId = r.id;
          this.messages = [];
        }
      } catch (_) {}
    },
    startRename(t) {
      this.renamingThreadId = t.id;
      this.renamingTitle = t.title;
    },
    async confirmRename() {
      const id = this.renamingThreadId;
      const title = this.renamingTitle.trim();
      if (!title || !id) return;
      try {
        await API.patch("/ai/threads/" + id, { title });
      } catch (_) {}
      this.renamingThreadId = 0;
      this.renamingTitle = "";
      await this.loadThreads();
    },
    async deleteThread(id) {
      if (!confirm(this.ru("Удалить диалог?", "Delete thread?"))) return;
      try {
        await API.del("/ai/threads/" + id);
        if (this.activeThreadId === id) {
          this.activeThreadId = 0;
          this.messages = [];
        }
        await this.loadThreads();
      } catch (_) {}
    },

    /* ── чат ── */
    async send() {
      const text = this.input.trim();
      if (!text || this.busy) return;
      this.input = "";
      this.messages.push({ role: "user", content: text });
      this.busy = true;
      this.messages.push({ role: "assistant", content: "" });

      const activeTab = Alpine.store("tabs").active;
      const table = activeTab && activeTab.key ? activeTab.key : "";

      try {
        const tok = localStorage.getItem("suot_token") ||
                    sessionStorage.getItem("suot_token_session") || "";
        const res = await fetch("/api/ai/chat", {
          method: "POST",
          headers: { "Authorization": "Bearer " + tok,
                     "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: this.messages.slice(0, -1).map(
              (m) => ({ role: m.role, content: m.content })),
            table,
            thread_id: this.activeThreadId,
          }),
        });
        if (!res.ok) throw new Error("HTTP " + res.status);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop();
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const data = line.slice(6);
            if (data === "[DONE]") break;
            try {
              const j = JSON.parse(data);
              if (j.error) throw new Error(j.error);
              const last = this.messages[this.messages.length - 1];
              last.content += j.content || "";
            } catch (e) {
              if (e.message !== "Unexpected end of JSON input")
                throw e;
            }
          }
        }
      } catch (e) {
        const last = this.messages[this.messages.length - 1];
        last.content = "⚠ " + e.message;
        Sounds.play("error");
      }
      this.busy = false;
      this._scrollBottom();
      /* перезагрузить список тредов (обновляется preview / title) */
      await this.loadThreads();
    },

    /* ── инсайты по разделу ── */
    async loadInsights() {
      const activeTab = Alpine.store("tabs").active;
      const table = activeTab && activeTab.key ? activeTab.key : "";
      this.messages.push({ role: "user",
        content: this.ru("Покажи инсайты по текущему разделу",
                         "Show insights for the current section") });
      this.busy = true;
      this.messages.push({ role: "assistant", content: "" });
      try {
        const r = await API.post("/ai/insights", { table });
        this.messages[this.messages.length - 1].content = r.insights || "—";
      } catch (e) {
        this.messages[this.messages.length - 1].content = "⚠ " + e.message;
      }
      this.busy = false;
      this._scrollBottom();
    },

    /* ── агент: план diff-предпросмотра ── */
    async agentPlan() {
      const text = this.input.trim();
      if (!text || this.busy) return;
      this.input = "";
      this.messages.push({ role: "user", content: text });
      this.busy = true;
      try {
        const r = await API.post("/ai/agent/plan", { message: text });
        if (r.type === "preview") {
          this.agentConfirm = r;
        } else {
          this.messages.push({ role: "assistant", content: r.content || "—" });
        }
      } catch (e) {
        this.messages.push({ role: "assistant", content: "⚠ " + e.message });
      }
      this.busy = false;
      this._scrollBottom();
    },

    /* ── агент: подтверждение ── */
    async agentExecute(action, params) {
      try {
        const res = await API.post("/ai/agent/execute", { action, params });
        const info = res.count !== undefined
          ? this.ru("Обновлено: ", "Updated: ") + res.count
          : this.ru("Выполнено ✓", "Done ✓") + " #" + (res.id || "");
        Toast.show(info, "success");
        document.dispatchEvent(new CustomEvent("suot-reload-tables", { bubbles: true }));
        document.dispatchEvent(new CustomEvent("suot-counts-changed", { bubbles: true }));
        this.messages.push({ role: "assistant", content: info });
      } catch (e) {
        Toast.show(e.message, "error");
      }
      this.agentConfirm = null;
      this._scrollBottom();
    },
    dismissAgent() { this.agentConfirm = null; },

    _scrollBottom() {
      this.$nextTick(() => {
        const el = document.getElementById("ai-messages");
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    toggle() {
      this.settingsOpen = false;
      this.pingResult = null;
      this.init();
    },
  };
};
