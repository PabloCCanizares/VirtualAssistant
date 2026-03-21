(function () {
  "use strict";

  const API_BASE = "/config/api";
  let originalValues = {};

  // ── Initialization ────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", init);

  function init() {
    if (!document.getElementById("configPanel")) return;
    loadSettings();
    setupDirtyTracking();
    setupTestButtons();

    document.getElementById("configApplyBtn").addEventListener("click", handleApply);
    document.getElementById("configAcceptBtn").addEventListener("click", handleAccept);
    document.getElementById("configExitBtn").addEventListener("click", handleExit);
    document.getElementById("configModalCancel").addEventListener("click", hideModal);
  }

  // ── Load current values ───────────────────────────────────────
  async function loadSettings() {
    try {
      const res = await fetch(`${API_BASE}/settings`);
      const json = await res.json();
      if (!json.success) return;

      const flat = {};
      for (const section of Object.values(json.sections)) {
        Object.assign(flat, section);
      }

      for (const [key, value] of Object.entries(flat)) {
        const el = document.querySelector(`[name="${key}"]`);
        if (!el) continue;
        el.value = value;
        if (el.tagName === "INPUT" && value) {
          el.placeholder = value;
        }
      }

      originalValues = { ...flat };
      updateApplyBtn();
    } catch (err) {
      console.error("Error cargando configuracion:", err);
    }
  }

  // ── Dirty tracking ────────────────────────────────────────────
  function setupDirtyTracking() {
    const fields = document.querySelectorAll(".config-form input, .config-form select");
    fields.forEach((el) => {
      el.addEventListener("input", onFieldChange);
      el.addEventListener("change", onFieldChange);
    });
  }

  function onFieldChange(e) {
    const el = e.target;
    const name = el.getAttribute("name");
    if (!name) return;
    const original = originalValues[name] ?? "";
    const current = el.value;
    if (current !== original) {
      el.classList.add("config-field-dirty");
    } else {
      el.classList.remove("config-field-dirty");
    }
    updateApplyBtn();
  }

  function updateApplyBtn() {
    const btn = document.getElementById("configApplyBtn");
    btn.disabled = !hasUnsavedChanges();
  }

  function hasUnsavedChanges() {
    const fields = document.querySelectorAll(".config-form input, .config-form select");
    for (const el of fields) {
      const name = el.getAttribute("name");
      if (!name) continue;
      if (el.value !== (originalValues[name] ?? "")) return true;
    }
    return false;
  }

  function collectAllChanges() {
    const changes = {};
    const fields = document.querySelectorAll(".config-form input, .config-form select");
    for (const el of fields) {
      const name = el.getAttribute("name");
      if (!name) continue;
      if (el.value !== (originalValues[name] ?? "")) {
        changes[name] = el.value;
      }
    }
    return changes;
  }

  // ── Apply ─────────────────────────────────────────────────────
  async function handleApply() {
    const changes = collectAllChanges();
    if (Object.keys(changes).length === 0) return true;

    showSpinner();
    try {
      const res = await fetch(`${API_BASE}/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(changes),
      });
      const json = await res.json();
      hideSpinner();

      if (json.success) {
        // Actualizar snapshot
        for (const [k, v] of Object.entries(changes)) {
          originalValues[k] = v;
        }
        clearDirtyMarks();
        updateApplyBtn();

        let msg = json.message || "Cambios aplicados correctamente";
        if (json.restart_required) {
          msg += ". Algunos cambios requieren reiniciar la aplicacion.";
        }
        showSnackbar(msg, "success");
        return true;
      } else {
        showSnackbar("Error al aplicar cambios", "error", json.errors);
        return false;
      }
    } catch (err) {
      hideSpinner();
      showSnackbar("Error de conexion con el servidor", "error");
      return false;
    }
  }

  function clearDirtyMarks() {
    document.querySelectorAll(".config-field-dirty").forEach((el) => {
      el.classList.remove("config-field-dirty");
    });
  }

  // ── Accept ────────────────────────────────────────────────────
  function handleAccept() {
    if (hasUnsavedChanges()) {
      showModal(
        "Tienes cambios sin aplicar. ¿Deseas aplicarlos antes de salir?",
        async () => {
          hideModal();
          const ok = await handleApply();
          if (ok) window.location.href = "/";
        }
      );
    } else {
      window.location.href = "/";
    }
  }

  // ── Exit ──────────────────────────────────────────────────────
  function handleExit() {
    if (hasUnsavedChanges()) {
      showModal("¿Salir sin guardar los cambios?", () => {
        window.location.href = "/";
      });
    } else {
      window.location.href = "/";
    }
  }

  // ── Test MongoDB buttons ──────────────────────────────────────
  function setupTestButtons() {
    document.querySelectorAll(".config-test-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const fieldId = btn.getAttribute("data-uri-field");
        const input = document.getElementById(fieldId);
        const resultEl = document.getElementById("test-" + input.name);
        if (!input || !resultEl) return;

        btn.classList.add("testing");
        btn.textContent = "...";
        resultEl.textContent = "";
        resultEl.className = "config-test-result";

        try {
          const endpoint = input.name === "MONGO_LOCAL_URI"
            ? "test-mongo-local"
            : "test-mongo-remote";
          const res = await fetch(`${API_BASE}/${endpoint}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ uri: input.value }),
          });
          const json = await res.json();
          resultEl.textContent = json.message;
          resultEl.classList.add(json.success ? "ok" : "fail");
        } catch {
          resultEl.textContent = "Error de conexion";
          resultEl.classList.add("fail");
        } finally {
          btn.classList.remove("testing");
          btn.textContent = "Probar";
        }
      });
    });
  }

  // ── Spinner ───────────────────────────────────────────────────
  function showSpinner() {
    document.getElementById("configSpinner").style.display = "flex";
  }

  function hideSpinner() {
    document.getElementById("configSpinner").style.display = "none";
  }

  // ── Snackbar ──────────────────────────────────────────────────
  function showSnackbar(message, type, fieldErrors) {
    const el = document.getElementById("configSnackbar");
    let html = message;

    if (fieldErrors && Object.keys(fieldErrors).length > 0) {
      html += '<div class="config-snackbar-errors">';
      for (const [field, msg] of Object.entries(fieldErrors)) {
        html += `<div>· <strong>${field}</strong>: ${msg}</div>`;
      }
      html += "</div>";
    }

    el.innerHTML = html;
    el.className = "config-snackbar " + type;
    el.style.display = "block";

    // Forzar reflow para que la transicion funcione
    void el.offsetHeight;
    el.classList.add("visible");

    clearTimeout(el._timeout);
    el._timeout = setTimeout(() => {
      el.classList.remove("visible");
      setTimeout(() => {
        el.style.display = "none";
      }, 300);
    }, 5000);
  }

  // ── Modal ─────────────────────────────────────────────────────
  function showModal(message, onConfirm) {
    const overlay = document.getElementById("configConfirmModal");
    document.getElementById("configModalMessage").textContent = message;
    overlay.style.display = "flex";

    const confirmBtn = document.getElementById("configModalConfirm");
    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);
    newBtn.addEventListener("click", onConfirm);
  }

  function hideModal() {
    document.getElementById("configConfirmModal").style.display = "none";
  }
})();
