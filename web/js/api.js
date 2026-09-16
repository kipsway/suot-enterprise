/* SUOT Neo — API-клиент */
(function () {
  const BASE = "/api";
  const LS = "suot_token", SS = "suot_token_session";

  function readToken() {
    return localStorage.getItem(LS) || sessionStorage.getItem(SS) || "";
  }
  let token = readToken();

  async function request(path, { method = "GET", body } = {}) {
    const headers = {};
    if (token) headers["Authorization"] = "Bearer " + token;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(BASE + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch (_) { /* no body */ }
    if (!res.ok) {
      const msg = (data && (data.detail || data.message)) || `HTTP ${res.status}`;
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function setToken(t, remember = true) {
    localStorage.removeItem(LS);
    sessionStorage.removeItem(SS);
    token = t || "";
    if (!token) return;
    (remember ? localStorage : sessionStorage).setItem(
      remember ? LS : SS, token);
  }
  function hasToken() { return !!token; }

  function authHeaders() {
    return token ? { "Authorization": "Bearer " + token } : {};
  }

  async function upload(file) {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(BASE + "/media/upload", {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    });
    let data = null;
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) {
      const msg = (data && (data.detail || data.message)) || `HTTP ${res.status}`;
      throw Object.assign(new Error(msg), { status: res.status });
    }
    return data;
  }

  window.API = {
    request, setToken, hasToken, authHeaders, upload,
    get: (p) => request(p),
    post: (p, b) => request(p, { method: "POST", body: b }),
    put: (p, b) => request(p, { method: "PUT", body: b }),
    patch: (p, b) => request(p, { method: "PATCH", body: b }),
    del: (p) => request(p, { method: "DELETE" }),
  };
})();
