// goal_menu.js
document.addEventListener("DOMContentLoaded", () => {
  // ============================================================
  // ============  Seleccionar todo / Eliminación múltiple  ======
  // ============================================================
  const selectAll = document.getElementById("selectAllGoals");
  const bulkDeleteBtn = document.getElementById("bulkDeleteGoalsBtn");
  const bulkForm = document.getElementById("bulkDeleteGoalsForm");
  const goalList = document.getElementById("goalList");

  const getChecks = () =>
    Array.from(document.querySelectorAll("#goalList .task-select"));

  function updateBulkButtonState() {
    if (!bulkDeleteBtn) return;
    const anyChecked = getChecks().some((ch) => ch.checked);
    bulkDeleteBtn.disabled = !anyChecked;
  }

  if (selectAll) {
    selectAll.addEventListener("change", (e) => {
      const checked = e.target.checked;
      getChecks().forEach((ch) => {
        ch.checked = checked;
      });
      updateBulkButtonState();
    });
  }

  document.addEventListener("change", (e) => {
    if (e.target && e.target.classList.contains("task-select")) {
      updateBulkButtonState();
    }
  });

  // Si quieres confirm extra al borrar en lote (además del onsubmit del form):
  if (bulkForm) {
    bulkForm.addEventListener("submit", (e) => {
      // Ya tienes confirm en el HTML, esto es opcional
      // if (!confirm("¿Eliminar los objetivos seleccionados?")) {
      //   e.preventDefault();
      // }
    });
  }

  // ============================================================
  // ===================  Expandir / Colapsar  ==================
  // ============================================================
  // Click en el resumen para alternar detalles
  if (goalList) {
    goalList.addEventListener("click", (e) => {
      const row = e.target.closest(".task-row");
      if (!row) return;
      // Evitar que botones dentro del row abran/cerren
      if (e.target.closest(".task-buttons-right")) return;

      const li = row.closest("li");
      const details = li.querySelector(".task-details");
      if (details) {
        const isHidden = details.getAttribute("aria-hidden") === "true" || !details.getAttribute("aria-hidden");
        details.style.display = isHidden ? "block" : "none";
        details.setAttribute("aria-hidden", isHidden ? "false" : "true");
      }
    });
  }

  // ============================================================
  // ================  Editar / Confirmar / Cancelar  ===========
  // ============================================================
  function enterEditMode(form) {
    const container = form.closest("li");
    const view = container.querySelector(".task-fields-view");
    const edit = container.querySelector(".task-fields-edit");
    const btnEdit = container.querySelector(".btn-edit");
    const btnConfirm = container.querySelector(".btn-confirm");
    const btnCancel = container.querySelector(".btn-cancel");

    if (view) view.style.display = "none";
    if (edit) edit.style.display = "block";
    if (btnEdit) btnEdit.style.display = "none";
    if (btnConfirm) btnConfirm.style.display = "inline-block";
    if (btnCancel) btnCancel.style.display = "inline-block";
  }

  function exitEditMode(form, restore = true) {
    const container = form.closest("li");
    const view = container.querySelector(".task-fields-view");
    const edit = container.querySelector(".task-fields-edit");
    const btnEdit = container.querySelector(".btn-edit");
    const btnConfirm = container.querySelector(".btn-confirm");
    const btnCancel = container.querySelector(".btn-cancel");

    if (edit && restore) {
      // Opcional: restablecer inputs desde la vista (puedes omitir si no hace falta)
      const titleSpan = container.querySelector(".task-title");
      if (titleSpan) {
        const inputTitle = edit.querySelector('input[name="titulo"]');
        if (inputTitle) inputTitle.value = titleSpan.textContent.trim();
      }
    }

    if (view) view.style.display = "block";
    if (edit) edit.style.display = "none";
    if (btnEdit) btnEdit.style.display = "inline-block";
    if (btnConfirm) btnConfirm.style.display = "none";
    if (btnCancel) btnCancel.style.display = "none";
  }

  function updateViewFromForm(form) {
    const container = form.closest("li");

    const getVal = (sel, fallback = "—") => {
      const el = form.querySelector(sel);
      if (!el) return fallback;
      return (el.value || fallback).toString();
    };

    // Campos que mostramos en la vista
    const title = getVal('input[name="titulo"]', "(sin título)");
    const desc = getVal('textarea[name="descripcion"]', "(sin descripción)");
    const cat = getVal('input[name="categoria"]', "—");
    const estado = getVal('select[name="estado"]', "En progreso");
    const prioridad = getVal('select[name="prioridad"]', "Media");
    const progreso = getVal('input[name="progreso"]', "0");
    const scope = getVal('select[name="scope"]', "Personal");
    const idUsuario = getVal('input[name="id_usuario"]', "—");
    const alarmaId = getVal('input[name="alarma_id"]', "—");
    const fIni = getVal('input[name="fecha_inicio"]', "");
    const fFin = getVal('input[name="fecha_fin"]', "");

    // Título arriba
    const titleNode = container.querySelector(".task-title");
    if (titleNode) titleNode.textContent = title;

    // Subtítulos del resumen
    const summaries = container.querySelectorAll(".task-summary .task-subtitle");
    if (summaries && summaries[0]) {
      // reconstruir primer subtítulo "Periodo: ..."
      summaries[0].textContent = `Periodo: ${fIni || "—"}${fFin ? " → " + fFin : ""} · Categoría: ${cat}`;
    }
    if (summaries && summaries[1]) {
      summaries[1].textContent = `Estado: ${estado} · Prioridad: ${prioridad} · Progreso: ${progreso}%`;
    }

    // Vista detallada
    const mapView = [
      [".task-desc-text", desc],
      [".task-scope-text", scope],
      [".task-user-text", idUsuario],
      [".task-alarm-text", alarmaId],
      [".task-date-start", fIni || "—"],
      [".task-date-end", fFin || "—"],
      [".task-cat-text", cat],
      [".task-est-text", estado],
      [".task-prio-text", prioridad]
    ];
    mapView.forEach(([sel, val]) => {
      const span = container.querySelector(sel);
      if (span) span.textContent = val;
    });
  }

  // Botones de cada item
  document.querySelectorAll("#goalList .task-edit-form").forEach((form) => {
    const container = form.closest("li");
    const btnEdit = container.querySelector(".btn-edit");
    const btnCancel = container.querySelector(".btn-cancel");

    if (btnEdit) {
      btnEdit.addEventListener("click", () => enterEditMode(form));
    }
    if (btnCancel) {
      btnCancel.addEventListener("click", () => exitEditMode(form, true));
    }

    // Interceptar submit para actualizar via fetch
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const action = form.getAttribute("action") || window.location.href;

      try {
        const fd = new FormData(form);
        // Si usas CSRF con cabeceras, añade aquí el token desde meta o input hidden
        // const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        const resp = await fetch(action, {
          method: "POST",
          body: fd,
          // headers: csrf ? { "X-CSRFToken": csrf } : {}
        });

        if (!resp.ok) {
          const text = await resp.text();
          alert("Error al actualizar: " + resp.status + " " + text);
          return;
        }

        updateViewFromForm(form);
        exitEditMode(form, false);
      } catch (err) {
        alert("Error de red: " + err);
      }
    });
  });

  // Estado inicial del botón de borrado múltiple
  updateBulkButtonState();

  // ============================================================
  // =====================  Mini chart ==========================
  // ============================================================
  const chartEl = document.getElementById("progressChart");
  if (chartEl && window.Chart) {
    const sample = {
      labels: ["Sem 1", "Sem 2", "Sem 3", "Sem 4", "Sem 5", "Sem 6"],
      data: [3, 7, 5, 12, 9, 15],
    };
    new Chart(chartEl, {
      type: "bar",
      data: {
        labels: sample.labels,
        datasets: [
          {
            label: "Tareas completadas",
            data: sample.data,
            backgroundColor: "rgba(108,243,255,.4)",
            borderColor: "#6cf3ff",
            borderWidth: 2,
            borderRadius: 8,
          },
        ],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          y: {
            beginAtZero: true,
            grid: { color: "rgba(255,255,255,.08)" },
            ticks: { color: "#9fb0d7" },
          },
          x: {
            grid: { display: false },
            ticks: { color: "#9fb0d7" },
          },
        },
      },
    });
  }
});
