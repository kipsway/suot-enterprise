/* Часть 21: мастер первого запуска + восстановление пароля. */

window.setupWizard = function () {
  return {
    step: 1,
    busy: false,
    err: "",
    logoData: "",

    f: { org_name: "", username: "", password: "", password2: "",
         full_name: "", sec_question: "Девичья фамилия матери?",
         sec_answer: "", theme: "dark", lang: "ru", load_demo: false,
         scenario: "today" },

    icons: window.ICONS,
    ru: (a, b) => I18N.lang === "ru" ? a : b,

    QUESTIONS: [
      "Девичья фамилия матери?",
      "Название первой школы?",
      "Кличка первого домашнего животного?",
      "Город, где вы родились?",
      "Ваш любимый фильм?",
    ],

    pickLogo(ev) {
      const file = ev.target.files[0];
      if (!file) return;
      if (file.size > 300 * 1024) {
        Toast.show(this.ru("Логотип до 300 КБ", "Logo up to 300 KB"),
          "error");
        ev.target.value = "";
        return;
      }
      const rd = new FileReader();
      rd.onload = () => {
        this.logoData = String(rd.result || "");
        this.$refs.logoPrev && (this.$refs.logoPrev.src = this.logoData);
      };
      rd.readAsDataURL(file);
    },

    vStep1() {
      return true; // организация необязательна
    },
    vStep2() {
      if (this.f.username.trim().length < 3) {
        this.err = this.ru("Логин: минимум 3 символа",
                           "Username: min 3 chars");
        return false;
      }
      if (this.f.password.length < 6) {
        this.err = this.ru("Пароль: минимум 6 символов",
                           "Password: min 6 chars");
        return false;
      }
      if (this.f.password !== this.f.password2) {
        this.err = this.ru("Пароли не совпадают", "Passwords differ");
        return false;
      }
      if (this.f.sec_answer.trim().length < 2) {
        this.err = this.ru("Ответ на вопрос: минимум 2 символа",
                           "Answer: min 2 chars");
        return false;
      }
      this.err = "";
      return true;
    },

    next() {
      if (this.step === 1) {
        if (this.vStep1()) this.step = 2;
        return;
      }
      if (this.step === 2) {
        if (!this.vStep2()) return;
        this.step = 3;
        return;
      }
      this.submit();
    },
    back() { if (this.step > 1) { this.step--; this.err = ""; } },

    async submit() {
      this.busy = true;
      this.err = "";
      try {
        const r = await API.post("/setup/admin", {
          org_name: this.f.org_name,
          logo: this.logoData,
          username: this.f.username.trim(),
          password: this.f.password,
          full_name: this.f.full_name,
          sec_question: this.f.sec_question,
          sec_answer: this.f.sec_answer,
          theme: this.f.theme,
          lang: I18N.lang || "ru",
          load_demo: this.f.load_demo,
          scenario: this.f.scenario,
        });
        Sounds.play("success");
        /* finishSetup доступен из родительского scope (app root) */
        this.finishSetup(r.user, r.token);
        if (this.f.load_demo) {
          setTimeout(() => {
            try { Alpine.store("tabs").open(this.f.scenario === "documents" ? "protocols" : "employees"); }
            catch (_) {}
            document.dispatchEvent(new CustomEvent(
              "suot-load-demo", { bubbles: true }));
          }, 500);
        }
      } catch (e) {
        this.err = e.message;
        Sounds.play("error");
      }
      this.busy = false;
    },
  };
};

/* Восстановление пароля с экрана входа */
window.passwordRecovery = function () {
  return {
    open: false,
    stage: 1,            // 1 = логин, 2 = ответ
    busy: false,
    err: "",
    question: "",
    f: { username: "", answer: "", p1: "", p2: "" },

    ru: (a, b) => I18N.lang === "ru" ? a : b,

    async findQuestion() {
      if (!this.f.username.trim()) return;
      this.busy = true;
      this.err = "";
      try {
        const r = await API.post("/setup/recover/question",
          { username: this.f.username });
        this.question = r.question;
        this.stage = 2;
      } catch (e) { this.err = e.message; }
      this.busy = false;
    },

    async reset() {
      if (this.f.p1.length < 6) {
        this.err = this.ru("Пароль: минимум 6 символов",
                           "Password: min 6 chars");
        return;
      }
      if (this.f.p1 !== this.f.p2) {
        this.err = this.ru("Пароли не совпадают", "Passwords differ");
        return;
      }
      this.busy = true;
      this.err = "";
      try {
        const r = await API.post("/setup/recover/reset", {
          username: this.f.username,
          answer: this.f.answer,
          new_password: this.f.p1,
        });
        Sounds.play("success");
        this.finishSetup(r.user, r.token);
      } catch (e) { this.err = e.message; }
      this.busy = false;
    },
  };
};
