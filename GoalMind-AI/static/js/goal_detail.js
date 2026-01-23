// goal_detail.js - Funcionalidades específicas para la vista de detalle de objetivo
document.addEventListener("DOMContentLoaded", () => {
  // ============================================================
  // ===============  Modal de edición de objetivo  =============
  // ============================================================
  const editGoalModal = document.getElementById("editGoalModal");
  const btnEditGoal = document.getElementById("btnEditGoal");
  const closeEditGoalModal = document.getElementById("closeEditGoalModal");
  const cancelEditGoal = document.getElementById("cancelEditGoal");
  const editGoalForm = document.getElementById("editGoalForm");

  function openEditModal() {
    if (editGoalModal) editGoalModal.style.display = "flex";
  }

  function closeEditModal() {
    if (editGoalModal) editGoalModal.style.display = "none";
  }

  if (btnEditGoal) btnEditGoal.addEventListener("click", openEditModal);
  if (closeEditGoalModal) closeEditGoalModal.addEventListener("click", closeEditModal);
  if (cancelEditGoal) cancelEditGoal.addEventListener("click", closeEditModal);

  if (editGoalModal) {
    editGoalModal.addEventListener("click", (e) => {
      if (e.target === editGoalModal) closeEditModal();
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && editGoalModal && editGoalModal.style.display === "flex") {
      closeEditModal();
    }
  });

  // Envío del formulario via AJAX
  if (editGoalForm) {
    editGoalForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const goalId = document.getElementById("editGoalId").value;
      
      const payload = {
        titulo: document.getElementById("editTitulo").value,
        descripcion: document.getElementById("editDescripcion").value,
        categoria: document.getElementById("editCategoria").value,
        fecha_inicio: document.getElementById("editFechaInicio").value || null,
        fecha_fin: document.getElementById("editFechaFin").value || null,
        project_id: document.getElementById("editProjectId").value,
        estado: document.getElementById("editEstado").value,
        prioridad: document.getElementById("editPrioridad").value,
        progreso: parseInt(document.getElementById("editProgreso").value) || 0,
        scope: document.getElementById("editScope").value
      };

      try {
        const res = await fetch(`/goals/api/${goalId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        const data = await res.json();
        
        if (data.success) {
          // Actualizar la UI con los nuevos valores
          updateGoalDetailUI(payload);
          closeEditModal();
          alert("Objetivo actualizado correctamente");
        } else {
          alert("Error: " + (data.error || "No se pudo actualizar"));
        }
      } catch (err) {
        console.error(err);
        alert("Error de red al actualizar el objetivo");
      }
    });
  }

  function updateGoalDetailUI(payload) {
    // Actualizar campos de información
    const updateText = (id, value, fallback = "—") => {
      const el = document.getElementById(id);
      if (el) el.textContent = value || fallback;
    };

    updateText("goal-titulo", payload.titulo, "(sin titulo)");
    updateText("goal-descripcion", payload.descripcion, "(sin descripcion)");
    updateText("goal-categoria", payload.categoria, "Sin categoria");
    updateText("goal-estado", payload.estado);
    updateText("goal-prioridad", payload.prioridad);
    updateText("goal-scope", payload.scope);
    updateText("goal-fecha-inicio", payload.fecha_inicio);
    updateText("goal-fecha-fin", payload.fecha_fin);
    updateText("goal-progreso-text", payload.progreso + "%");

    // Actualizar progress ring
    const progressRing = document.getElementById("goal-progress-ring");
    const progressValue = document.getElementById("goal-progress-value");
    if (progressRing) progressRing.style.setProperty("--progress", payload.progreso + "%");
    if (progressValue) progressValue.textContent = payload.progreso + "%";

    // Actualizar hero
    const heroTitle = document.querySelector(".panel-hero-title");
    const heroDesc = document.querySelector(".panel-hero-desc");
    if (heroTitle) heroTitle.textContent = payload.titulo;
    if (heroDesc) heroDesc.textContent = payload.descripcion || "Sin descripcion";
  }

  // ============================================================
  // =======  Seleccionar todo / Acciones en lote (Tareas)  =====
  // ============================================================
  const selectAllGoalTasks = document.getElementById("selectAllGoalTasks");
  const bulkActionsContainerGoal = document.getElementById("bulkActionsContainerGoal");
  const bulkDeleteBtnGoal = document.getElementById("bulkDeleteBtnGoal");
  const deleteConfirmModalGoal = document.getElementById("deleteConfirmModalGoal");

  const getGoalTaskChecks = () => Array.from(document.querySelectorAll(".goal-task-checkbox"));

  function getSelectedGoalTaskIds() {
    return getGoalTaskChecks().filter(ch => ch.checked).map(ch => ch.value);
  }

  function updateBulkActionsVisibilityGoal() {
    const selectedIds = getSelectedGoalTaskIds();
    const hasSelection = selectedIds.length > 0;
    if (bulkActionsContainerGoal) {
      bulkActionsContainerGoal.style.display = hasSelection ? "flex" : "none";
    }
  }

  function updateSelectAllStateGoal() {
    if (!selectAllGoalTasks) return;
    const checks = getGoalTaskChecks();
    if (checks.length === 0) {
      selectAllGoalTasks.checked = false;
      selectAllGoalTasks.indeterminate = false;
      return;
    }
    const allChecked = checks.every(ch => ch.checked);
    const someChecked = checks.some(ch => ch.checked);
    selectAllGoalTasks.checked = allChecked;
    selectAllGoalTasks.indeterminate = !allChecked && someChecked;
  }

  if (selectAllGoalTasks) {
    selectAllGoalTasks.addEventListener("change", () => {
      getGoalTaskChecks().forEach(ch => { ch.checked = selectAllGoalTasks.checked; });
      updateBulkActionsVisibilityGoal();
    });
  }

  document.addEventListener("change", (ev) => {
    const t = ev.target;
    if (!t || !t.classList || !t.classList.contains("goal-task-checkbox")) return;
    updateSelectAllStateGoal();
    updateBulkActionsVisibilityGoal();
  });

  // Modal de eliminación masiva
  if (bulkDeleteBtnGoal) {
    bulkDeleteBtnGoal.addEventListener("click", (e) => {
      e.stopPropagation();
      if (deleteConfirmModalGoal) {
        deleteConfirmModalGoal.style.display = "flex";
      }
    });
  }

  const cancelDeleteGoal = document.getElementById("cancelDeleteGoal");
  const closeDeleteModalGoal = document.getElementById("closeDeleteModalGoal");

  function hideDeleteModalGoal() {
    if (deleteConfirmModalGoal) {
      deleteConfirmModalGoal.style.display = "none";
    }
  }

  if (cancelDeleteGoal) cancelDeleteGoal.addEventListener("click", hideDeleteModalGoal);
  if (closeDeleteModalGoal) closeDeleteModalGoal.addEventListener("click", hideDeleteModalGoal);

  const confirmDeleteGoal = document.getElementById("confirmDeleteGoal");
  if (confirmDeleteGoal) {
    confirmDeleteGoal.addEventListener("click", async () => {
      const selectedTasks = getSelectedGoalTaskIds();
      if (selectedTasks.length === 0) {
        alert("No hay tareas seleccionadas.");
        hideDeleteModalGoal();
        return;
      }

      try {
        const response = await fetch("/tasks/bulk-delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ selected_tasks: selectedTasks })
        });

        const data = await response.json();
        if (data.success) {
          alert(data.message);
          window.location.reload();
        } else {
          alert("Error: " + data.message);
        }
      } catch (error) {
        alert("Error de red: " + error);
      }
      hideDeleteModalGoal();
    });
  }

  // ============================================================
  // ===============  Expandir / Colapsar tareas  ===============
  // ============================================================
  const goalTaskList = document.getElementById("goalTaskList");
  let expandedGoalTask = null;

  function isInteractiveTarget(target) {
    if (!target) return false;
    return !!target.closest(
      "button, a, input, textarea, select, form, .task-delete-btn, .btn-edit, .btn-confirm, .btn-cancel"
    );
  }

  if (goalTaskList) {
    goalTaskList.addEventListener("click", (ev) => {
      const li = ev.target.closest(".item-card");
      if (!li) return;
      if (isInteractiveTarget(ev.target)) return;
      ev.stopPropagation();

      const already = li.classList.contains("expanded");
      document.querySelectorAll("#goalTaskList .item-card.expanded").forEach(item => {
        if (item !== li) collapseGoalTask(item);
      });

      if (!already) expandGoalTask(li);
      else collapseGoalTask(li);
    });

    goalTaskList.addEventListener("keydown", (ev) => {
      const li = ev.target.closest(".item-card");
      if (!li) return;
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        ev.stopPropagation();
        const already = li.classList.contains("expanded");
        document.querySelectorAll("#goalTaskList .item-card.expanded").forEach(item => {
          if (item !== li) collapseGoalTask(item);
        });
        if (!already) expandGoalTask(li);
        else collapseGoalTask(li);
      }
    });
  }

  document.addEventListener("click", (ev) => {
    if (!expandedGoalTask) return;
    if (ev.target.closest(".item-card")) return;
    if (ev.target.closest(".modal-overlay")) return;
    document.querySelectorAll("#goalTaskList .item-card.expanded").forEach(item => collapseGoalTask(item));
  });

  function expandGoalTask(li) {
    const details = li.querySelector(".item-details");
    if (details) {
      li.classList.add("expanded");
      li.setAttribute("aria-expanded", "true");
      details.style.display = "flex";
      details.style.flexDirection = "column";
      details.setAttribute("aria-hidden", "false");
    }
    expandedGoalTask = li;
  }

  function collapseGoalTask(li) {
    const details = li.querySelector(".item-details");
    if (details) {
      const form = li.querySelector(".task-edit-form");
      if (form) {
        try { exitEditModeGoal(form, true); } catch (e) {}
      }
      li.classList.remove("expanded");
      li.setAttribute("aria-expanded", "false");
      details.style.display = "none";
      details.setAttribute("aria-hidden", "true");
    }
    if (expandedGoalTask === li) expandedGoalTask = null;
  }

  // ============================================================
  // ==================  Edición de tareas  =====================
  // ============================================================
  function enterEditModeGoal(form) {
    const view = form.querySelector(".task-fields-view");
    const edit = form.querySelector(".task-fields-edit");
    const li = form.closest(".item-card");
    const editBtn = li.querySelector(".btn-edit");
    const confirmBtn = li.querySelector(".btn-confirm");
    const cancelBtn = li.querySelector(".btn-cancel");

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

  function exitEditModeGoal(form, restore = true) {
    const li = form.closest(".item-card");
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
      form.__originalValues = {};
      inputs.forEach(i => form.__originalValues[i.name] = i.value);
    }

    if (view) view.style.display = "flex";
    if (edit) edit.style.display = "none";
    if (editBtn) editBtn.style.display = "inline-block";
    if (confirmBtn) confirmBtn.style.display = "none";
    if (cancelBtn) cancelBtn.style.display = "none";

    if (!restore) updateViewFromFormGoal(form);
  }

  function updateViewFromFormGoal(form) {
    const li = form.closest(".item-card");
    const contentInput = form.querySelector("input[name='contenido']");
    const descTextarea = form.querySelector("textarea[name='descripcion']");
    const fechaInput = form.querySelector("input[name='fecha_limite']");
    const estadoSel = form.querySelector("select[name='estado']");
    const categoriaInput = form.querySelector("input[name='categoria']");
    const prioSel = form.querySelector("select[name='prioridad']");

    if (contentInput) {
      const title = li.querySelector(".item-title");
      if (title) title.textContent = contentInput.value;
    }
    if (descTextarea) {
      const el = form.querySelector(".task-desc-text");
      if (el) el.textContent = descTextarea.value || "(sin descripcion)";
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
  }

  // Inicialización de formularios de edición
  document.querySelectorAll("#goalTaskList .item-card").forEach(li => {
    const form = li.querySelector(".task-edit-form");
    if (!form) return;

    const editBtn = li.querySelector(".btn-edit");
    const confirmBtn = li.querySelector(".btn-confirm");
    const cancelBtn = li.querySelector(".btn-cancel");

    const inputs = form.querySelectorAll("input[name], textarea[name], select[name]");
    form.__originalValues = {};
    inputs.forEach(i => form.__originalValues[i.name] = i.value);

    [editBtn, cancelBtn, confirmBtn].forEach(btn => {
      if (!btn) return;
      btn.addEventListener("click", (e) => e.stopPropagation());
    });

    if (editBtn) {
      editBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        enterEditModeGoal(form);
      });
    }

    if (cancelBtn) {
      cancelBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        exitEditModeGoal(form, true);
      });
    }

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
        updateViewFromFormGoal(form);
        exitEditModeGoal(form, false);
      } catch (err) {
        alert("Error de red: " + err);
      }
    });
  });

  // ============================================================
  // ===============  Ordenar lista de tareas  ==================
  // ============================================================
  const sortSelectGoal = document.getElementById("sortGoalTasks");
  const taskListElementGoal = document.getElementById("goalTaskList");

  if (sortSelectGoal && taskListElementGoal) {
    sortSelectGoal.addEventListener("change", () => {
      const sortValue = sortSelectGoal.value;
      const tasks = Array.from(taskListElementGoal.querySelectorAll(".item-card"));

      if (tasks.length === 0) return;

      const taskData = tasks.map(task => {
        const prioridadTag = task.querySelector(".item-meta-tag:last-child");
        const prioridadText = prioridadTag ? prioridadTag.textContent.trim().toLowerCase() : "media";
        
        let prioridad = prioridadText.replace(/[^a-z]/g, "").trim();
        if (prioridad.includes("alta")) prioridad = "alta";
        else if (prioridad.includes("baja")) prioridad = "baja";
        else prioridad = "media";

        const deadlineTag = task.querySelector(".item-meta-tag.deadline");
        const fechaLimite = deadlineTag ? deadlineTag.textContent.trim().replace(/[^\d-]/g, "") : null;

        const statusTags = task.querySelectorAll(".item-meta-tag");
        let estado = "pendiente";
        statusTags.forEach(tag => {
          const classes = tag.className;
          if (classes.includes("status-pendiente")) estado = "pendiente";
          else if (classes.includes("status-en-curso") || classes.includes("status-en-progreso")) estado = "en curso";
          else if (classes.includes("status-completada") || classes.includes("status-completado")) estado = "completada";
        });

        return { element: task, prioridad, fechaLimite, estado };
      });

      const prioridadOrder = { "alta": 1, "media": 2, "baja": 3 };

      switch (sortValue) {
        case "priority-desc":
          taskData.sort((a, b) => prioridadOrder[a.prioridad] - prioridadOrder[b.prioridad]);
          break;
        case "deadline-asc":
          taskData.sort((a, b) => {
            if (!a.fechaLimite && !b.fechaLimite) return 0;
            if (!a.fechaLimite) return 1;
            if (!b.fechaLimite) return -1;
            return new Date(a.fechaLimite) - new Date(b.fechaLimite);
          });
          break;
        case "status-pending":
          taskData.sort((a, b) => {
            if (a.estado === "pendiente" && b.estado !== "pendiente") return -1;
            if (a.estado !== "pendiente" && b.estado === "pendiente") return 1;
            return 0;
          });
          break;
        case "status-in-progress":
          taskData.sort((a, b) => {
            if (a.estado === "en curso" && b.estado !== "en curso") return -1;
            if (a.estado !== "en curso" && b.estado === "en curso") return 1;
            return 0;
          });
          break;
        case "status-completed":
          taskData.sort((a, b) => {
            if (a.estado === "completada" && b.estado !== "completada") return -1;
            if (a.estado !== "completada" && b.estado === "completada") return 1;
            return 0;
          });
          break;
        default:
          return;
      }

      taskData.forEach(item => {
        taskListElementGoal.appendChild(item.element);
      });
    });
  }
});
