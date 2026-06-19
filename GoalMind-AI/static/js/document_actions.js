(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".js-summarize-doc").forEach(function (btn) {
      btn.addEventListener("click", handleSummarize);
    });
  });

  async function handleSummarize(e) {
    const btn = e.currentTarget;
    const docId = btn.dataset.docId;
    const projectId = btn.dataset.projectId;
    const originalText = btn.textContent;

    btn.textContent = "...";
    btn.disabled = true;

    try {
      const res = await fetch("/api/ai/summarize-document", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_id: docId, project_id: projectId }),
      });
      const json = await res.json();

      if (json.success) {
        showSnackbar(json.message || "Resumen guardado como nota.", "success");
      } else {
        showSnackbar(json.message || "Error al generar el resumen.", "error");
      }
    } catch (err) {
      showSnackbar("Error de conexión con el servidor.", "error");
    } finally {
      btn.textContent = originalText;
      btn.disabled = false;
    }
  }

  function showSnackbar(message, type) {
    const el = document.getElementById("docActionSnackbar");
    if (!el) return;

    el.textContent = message;
    el.className = "snackbar snackbar-" + type + " snackbar-show";
    el.style.display = "block";

    clearTimeout(el._timeout);
    el._timeout = setTimeout(function () {
      el.className = "snackbar";
      el.style.display = "none";
    }, 5000);
  }
})();
