// task_menu.js
document.addEventListener("DOMContentLoaded", () => {
  // ============================================================
  // =======  Seleccionar todo / Eliminación múltiple  ===========
  // ============================================================
  const selectAll = document.getElementById("selectAllTasks");
  const bulkDeleteBtn = document.getElementById("bulkDeleteBtn");
  const bulkForm = document.getElementById("bulkDeleteForm");

  const getChecks = () => Array.from(document.querySelectorAll(".task-select"));

  function updateBulkButtonState() {
    const anyChecked = getChecks().some(ch => ch.checked);
    if (bulkDeleteBtn) bulkDeleteBtn.disabled = !anyChecked;
  }

  if (selectAll) {
    selectAll.addEventListener("change", () => {
      getChecks().forEach(ch => { ch.checked = selectAll.checked; });
      updateBulkButtonState();
    });
  }

  // Delegado global: cambio en cualquier checkbox de tarea
  document.addEventListener("change", (ev) => {
    const t = ev.target;
    if (!t || !t.classList || !t.classList.contains("task-select")) return;

    updateBulkButtonState();

    if (selectAll) {
      const checks = getChecks();
      const all = checks.length > 0 && checks.every(ch => ch.checked);
      const some = checks.some(ch => ch.checked);
      selectAll.checked = all;
      selectAll.indeterminate = !all && some;
    }
  });

  // Estado inicial del botón
  updateBulkButtonState();


  // ============================================================
  // ===============  Expandir / Colapsar tareas  ===============
  // ============================================================
  const taskList = document.getElementById("taskList");
  let expandedItem = null;

  // Permite clicks en inputs/botones sin togglear el panel
  function isInteractiveTarget(target) {
    if (!target) return false;
    return !!target.closest(
      "button, a, input, textarea, select, form, .task-delete-btn, .btn-edit, .btn-confirm, .btn-cancel"
    );
  }

  if (taskList) {
    // Click para expandir/colapsar
    taskList.addEventListener("click", (ev) => {
      const li = ev.target.closest(".task-item");
      if (!li) return;
      if (isInteractiveTarget(ev.target)) return; // no togglear si es control
      ev.stopPropagation();

      const already = li.classList.contains("expanded");
      document.querySelectorAll(".task-item.expanded").forEach(item => {
        if (item !== li) collapseItem(item);
      });

      if (!already) expandItem(li);
      else collapseItem(li);
    });

    // Teclado (Enter / Espacio) cuando el <li> está enfocado
    taskList.addEventListener("keydown", (ev) => {
      const li = ev.target.closest(".task-item");
      if (!li) return;
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        ev.stopPropagation();
        const already = li.classList.contains("expanded");
        document.querySelectorAll(".task-item.expanded").forEach(item => {
          if (item !== li) collapseItem(item);
        });
        if (!already) expandItem(li);
        else collapseItem(li);
      }
    });
  }

  // Cerrar al clicar fuera
  document.addEventListener("click", (ev) => {
    if (!expandedItem) return;
    if (ev.target.closest(".task-item")) return;
    document.querySelectorAll(".task-item.expanded").forEach(item => collapseItem(item));
  });

  // Escape para cerrar
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && expandedItem) {
      document.querySelectorAll(".task-item.expanded").forEach(item => collapseItem(item));
    }
  });

  function expandItem(li) {
    const details = li.querySelector(".task-details");
    if (details) {
      li.classList.add("expanded");
      li.setAttribute("aria-expanded", "true");
      details.style.display = "flex";
      details.style.flexDirection = "column";
      details.setAttribute("aria-hidden", "false");
    }
    expandedItem = li;

    const firstInput = li.querySelector("input, textarea, select, button");
    if (firstInput) firstInput.focus();
  }

  function collapseItem(li) {
    const details = li.querySelector(".task-details");
    if (details) {
      const form = li.querySelector(".task-edit-form");
      if (form && typeof exitEditMode === "function") {
        try { exitEditMode(form, true); } catch (e) {}
      }
      li.classList.remove("expanded");
      li.setAttribute("aria-expanded", "false");
      details.style.display = "none";
      details.setAttribute("aria-hidden", "true");
    }
    if (expandedItem === li) expandedItem = null;
  }


  // ============================================================
  // ==================  Edición de una tarea  ==================
  // ============================================================
  // Nota: definimos enter/exit a nivel de módulo para que collapseItem pueda llamarlas.
  function enterEditMode(form) {
    const view = form.querySelector(".task-fields-view");
    const edit = form.querySelector(".task-fields-edit");
    const editBtn = form.closest(".task-item").querySelector(".btn-edit");
    const confirmBtn = form.closest(".task-item").querySelector(".btn-confirm");
    const cancelBtn = form.closest(".task-item").querySelector(".btn-cancel");

    if (view) view.style.display = "none";
    if (edit) {
      edit.style.display = "flex";
      edit.style.flexDirection = "column";
      edit.style.gap = "8px";
    }
    if (editBtn) editBtn.style.display = "none";
    if (confirmBtn) confirmBtn.style.display = "inline-block";
    if (cancelBtn) cancelBtn.style.display = "inline-block";
  }

  function exitEditMode(form, restore = true) {
    const li = form.closest(".task-item");
    const view = form.querySelector(".task-fields-view");
    const edit = form.querySelector(".task-fields-edit");
    const editBtn = li.querySelector(".btn-edit");
    const confirmBtn = li.querySelector(".btn-confirm");
    const cancelBtn = li.querySelector(".btn-cancel");

    const inputs = form.querySelectorAll("input[name], textarea[name], select[name]");
    const original = form.__originalValues || {};

    if (restore) {
      inputs.forEach(i => {
        if (Object.prototype.hasOwnProperty.call(original, i.name)) {
          i.value = original[i.name];
        }
      });
    } else {
      // persistimos nuevos valores como "original"
      form.__originalValues = {};
      inputs.forEach(i => form.__originalValues[i.name] = i.value);
    }

    if (view) view.style.display = "flex";
    if (edit) edit.style.display = "none";
    if (editBtn) editBtn.style.display = "inline-block";
    if (confirmBtn) confirmBtn.style.display = "none";
    if (cancelBtn) cancelBtn.style.display = "none";

    if (!restore) updateViewFromForm(form);
  }

  function updateViewFromForm(form) {
    const li = form.closest(".task-item");
    const contentInput = form.querySelector("input[name='contenido']");
    const descTextarea = form.querySelector("textarea[name='descripcion']");
    const fechaInput = form.querySelector("input[name='fecha_limite']");
    const estadoSel = form.querySelector("select[name='estado']");
    const categoriaInput = form.querySelector("input[name='categoria']");
    const prioSel = form.querySelector("select[name='prioridad']");

    if (contentInput) {
      const title = li.querySelector(".task-title");
      if (title) title.textContent = contentInput.value;
    }
    if (descTextarea) {
      const el = form.querySelector(".task-desc-text");
      if (el) el.textContent = descTextarea.value || "(sin descripción)";
    }
    if (estadoSel) {
      const el = form.querySelector(".task-est-text");
      if (el) el.textContent = estadoSel.value;
    }
    if (categoriaInput) {
      const el = form.querySelector(".task-cat-text");
      if (el) el.textContent = categoriaInput.value || "—";
    }
    if (prioSel) {
      const el = form.querySelector(".task-prio-text");
      if (el) el.textContent = prioSel.value;
    }

    const contentBlock = li.querySelector(".task-content");
    const deadlineEl = li.querySelector(".task-deadline");
    if (fechaInput && fechaInput.value) {
      if (deadlineEl) {
        deadlineEl.textContent = "Fecha límite: " + fechaInput.value;
      } else if (contentBlock) {
        const p = document.createElement("p");
        p.className = "task-deadline";
        p.textContent = "Fecha límite: " + fechaInput.value;
        contentBlock.appendChild(p);
      }
    } else if (deadlineEl) {
      deadlineEl.remove();
    }
  }

  // Inicialización de formularios de edición en cada task
  document.querySelectorAll(".task-item").forEach(li => {
    const form = li.querySelector(".task-edit-form");
    if (!form) return;

    const editBtn = li.querySelector(".btn-edit");
    const confirmBtn = li.querySelector(".btn-confirm");
    const cancelBtn = li.querySelector(".btn-cancel");

    // Guardar valores originales
    const inputs = form.querySelectorAll("input[name], textarea[name], select[name]");
    form.__originalValues = {};
    inputs.forEach(i => form.__originalValues[i.name] = i.value);

    // Evitar burbujeo que cierre el panel
    [editBtn, cancelBtn, confirmBtn].forEach(btn => {
      if (!btn) return;
      btn.addEventListener("click", (e) => e.stopPropagation());
    });

    // 🖊️ Editar
    if (editBtn) {
      editBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        enterEditMode(form);
      });
    }

    // ❌ Cancelar
    if (cancelBtn) {
      cancelBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        exitEditMode(form, true);
      });
    }

    // ✅ Confirmar (submit via fetch)
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      e.stopPropagation();

      const url = form.action;
      const data = new URLSearchParams();
      inputs.forEach(i => data.append(i.name, i.value));

      try {
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: data.toString()
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

});
