// task_menu.js
document.addEventListener("DOMContentLoaded", () => {
  // ============================================================
  // =======  Seleccionar todo / Acciones en lote  ===========
  // ============================================================
  const selectAll = document.getElementById("selectAllTasks");
  const bulkActionsContainer = document.getElementById("bulkActionsContainer");
  const assignGoalBtn = document.getElementById("assignGoalBtn");
  const bulkDeleteBtn = document.getElementById("bulkDeleteBtn");
  const deleteConfirmModal = document.getElementById("deleteConfirmModal");

  // Obtener todos los checkboxes de tareas
  const getChecks = () => Array.from(document.querySelectorAll(".item-checkbox[name='selected_tasks']"));

  // Obtener IDs de tareas seleccionadas
  function getSelectedTaskIds() {
    return getChecks().filter(ch => ch.checked).map(ch => ch.value);
  }

  // Actualizar visibilidad de botones de acciones
  function updateBulkActionsVisibility() {
    const selectedIds = getSelectedTaskIds();
    const hasSelection = selectedIds.length > 0;
    
    if (bulkActionsContainer) {
      bulkActionsContainer.style.display = hasSelection ? "flex" : "none";
    }
  }

  // Actualizar estado del checkbox "Seleccionar todo"
  function updateSelectAllState() {
    if (!selectAll) return;
    
    const checks = getChecks();
    if (checks.length === 0) {
      selectAll.checked = false;
      selectAll.indeterminate = false;
      return;
    }
    
    const allChecked = checks.every(ch => ch.checked);
    const someChecked = checks.some(ch => ch.checked);
    
    selectAll.checked = allChecked;
    selectAll.indeterminate = !allChecked && someChecked;
  }

  // Evento: Seleccionar todo
  if (selectAll) {
    selectAll.addEventListener("change", () => {
      getChecks().forEach(ch => { ch.checked = selectAll.checked; });
      updateBulkActionsVisibility();
    });
  }

  // Delegado global: cambio en cualquier checkbox de tarea
  document.addEventListener("change", (ev) => {
    const t = ev.target;
    if (!t || !t.classList || !t.classList.contains("item-checkbox")) return;
    if (t.id === "selectAllTasks") return; // Ignorar el checkbox de seleccionar todo
    
    updateSelectAllState();
    updateBulkActionsVisibility();
  });

  // Estado inicial
  updateBulkActionsVisibility();

  // ============================================================
  // =======  Modal: Asignar objetivo  ==========================
  // ============================================================
  const goalAssignModal = document.getElementById("goalAssignModal");
  let selectedGoalId = null;
  let pendingTaskIds = []; // Tareas a asignar (puede ser múltiples o una sola)

  // Abrir modal desde botón de acciones masivas
  if (assignGoalBtn) {
    assignGoalBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      pendingTaskIds = getSelectedTaskIds();
      if (pendingTaskIds.length === 0) {
        alert("No hay tareas seleccionadas.");
        return;
      }
      showGoalModal();
    });
  }

  // Abrir modal desde botón individual en cada tarea
  document.querySelectorAll(".btn-assign-goal").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const taskId = btn.dataset.taskId;
      if (taskId) {
        pendingTaskIds = [taskId];
        showGoalModal();
      }
    });
  });

  function showGoalModal() {
    if (goalAssignModal) {
      goalAssignModal.style.display = "flex";
    }
  }

  function hideGoalModal() {
    if (goalAssignModal) {
      goalAssignModal.style.display = "none";
    }
    selectedGoalId = null;
    pendingTaskIds = [];
    // Deseleccionar opciones
    document.querySelectorAll(".goal-option.selected").forEach(opt => {
      opt.classList.remove("selected");
    });
    // Deshabilitar botón confirmar
    const confirmBtn = document.getElementById("confirmAssignGoal");
    if (confirmBtn) confirmBtn.disabled = true;
  }

  // Cerrar modal
  const closeGoalModal = document.getElementById("closeGoalModal");
  const cancelAssignGoal = document.getElementById("cancelAssignGoal");
  
  if (closeGoalModal) {
    closeGoalModal.addEventListener("click", hideGoalModal);
  }
  if (cancelAssignGoal) {
    cancelAssignGoal.addEventListener("click", hideGoalModal);
  }

  // Seleccionar objetivo
  document.querySelectorAll(".goal-option").forEach(option => {
    option.addEventListener("click", () => {
      // Deseleccionar anterior
      document.querySelectorAll(".goal-option.selected").forEach(opt => {
        opt.classList.remove("selected");
      });
      // Seleccionar nuevo
      option.classList.add("selected");
      selectedGoalId = option.dataset.goalId;
      
      // Habilitar botón confirmar
      const confirmBtn = document.getElementById("confirmAssignGoal");
      if (confirmBtn) confirmBtn.disabled = false;
    });
  });

  // Confirmar asignación de objetivo
  const confirmAssignGoal = document.getElementById("confirmAssignGoal");
  if (confirmAssignGoal) {
    confirmAssignGoal.addEventListener("click", async () => {
      if (!selectedGoalId) return;
      
      if (pendingTaskIds.length === 0) {
        alert("No hay tareas seleccionadas.");
        return;
      }

      try {
        const response = await fetch("/tasks/bulk-assign-goal", {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            selected_tasks: pendingTaskIds,
            objetivo_id: selectedGoalId
          })
        });

        const data = await response.json();
        
        if (data.success) {
          alert(data.message);
          // Recargar la página para ver los cambios
          window.location.reload();
        } else {
          alert("Error: " + data.message);
        }
      } catch (error) {
        alert("Error de red: " + error);
      }

      hideGoalModal();
    });
  }

  // ============================================================
  // =======  Modal: Confirmar eliminación  =====================
  // ============================================================

  // Abrir modal de eliminación
  if (bulkDeleteBtn) {
    bulkDeleteBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (deleteConfirmModal) {
        deleteConfirmModal.style.display = "flex";
      }
    });
  }

  // Cerrar modal
  const cancelDelete = document.getElementById("cancelDelete");
  const closeDeleteModal = document.getElementById("closeDeleteModal");
  
  function hideDeleteModal() {
    if (deleteConfirmModal) {
      deleteConfirmModal.style.display = "none";
    }
  }

  if (cancelDelete) {
    cancelDelete.addEventListener("click", hideDeleteModal);
  }
  if (closeDeleteModal) {
    closeDeleteModal.addEventListener("click", hideDeleteModal);
  }

  // Confirmar eliminación
  const confirmDelete = document.getElementById("confirmDelete");
  if (confirmDelete) {
    confirmDelete.addEventListener("click", async () => {
      const selectedTasks = getSelectedTaskIds();
      if (selectedTasks.length === 0) {
        alert("No hay tareas seleccionadas.");
        hideDeleteModal();
        return;
      }

      try {
        const response = await fetch("/tasks/bulk-delete", {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            selected_tasks: selectedTasks
          })
        });

        const data = await response.json();
        
        if (data.success) {
          alert(data.message);
          // Recargar la página para ver los cambios
          window.location.reload();
        } else {
          alert("Error: " + data.message);
        }
      } catch (error) {
        alert("Error de red: " + error);
      }

      hideDeleteModal();
    });
  }

  // Cerrar modales al hacer clic en el overlay
  document.addEventListener("click", (e) => {
    // Cerrar modal de asignar objetivo si se hace clic en el overlay
    if (goalAssignModal && e.target === goalAssignModal) {
      hideGoalModal();
    }
    
    // Cerrar modal de eliminación si se hace clic en el overlay
    if (deleteConfirmModal && e.target === deleteConfirmModal) {
      hideDeleteModal();
    }
  });

  // Cerrar con Escape
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      hideGoalModal();
      hideDeleteModal();
    }
  });


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
      const li = ev.target.closest(".item-card");
      if (!li) return;
      if (isInteractiveTarget(ev.target)) return; // no togglear si es control
      ev.stopPropagation();

      const already = li.classList.contains("expanded");
      document.querySelectorAll(".item-card.expanded").forEach(item => {
        if (item !== li) collapseItem(item);
      });

      if (!already) expandItem(li);
      else collapseItem(li);
    });

    // Teclado (Enter / Espacio) cuando el <li> está enfocado
    taskList.addEventListener("keydown", (ev) => {
      const li = ev.target.closest(".item-card");
      if (!li) return;
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        ev.stopPropagation();
        const already = li.classList.contains("expanded");
        document.querySelectorAll(".item-card.expanded").forEach(item => {
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
    if (ev.target.closest(".item-card")) return;
    // No cerrar si se hace clic en modales
    if (ev.target.closest(".modal-overlay") || ev.target.closest(".assign-goal-modal") || ev.target.closest(".delete-modal")) return;
    document.querySelectorAll(".item-card.expanded").forEach(item => collapseItem(item));
  });

  // Escape para cerrar (ya manejado arriba para modales)

  function expandItem(li) {
    const details = li.querySelector(".item-details");
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
    const details = li.querySelector(".item-details");
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
    const editBtn = form.closest(".item-card").querySelector(".btn-edit");
    const confirmBtn = form.closest(".item-card").querySelector(".btn-confirm");
    const cancelBtn = form.closest(".item-card").querySelector(".btn-cancel");

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

    const contentBlock = li.querySelector(".item-content");
    const deadlineEl = li.querySelector(".item-meta-tag.deadline");
    if (fechaInput && fechaInput.value) {
      if (deadlineEl) {
        deadlineEl.textContent = fechaInput.value;
      }
    }
  }

  // Inicialización de formularios de edición en cada task
  document.querySelectorAll(".item-card").forEach(li => {
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

    // Editar
    if (editBtn) {
      editBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        enterEditMode(form);
      });
    }

    // Cancelar
    if (cancelBtn) {
      cancelBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        exitEditMode(form, true);
      });
    }

    // Confirmar (submit via fetch)
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

  // ============================================================
  // ===============  Ordenar lista de tareas  ==================
  // ============================================================
  const sortSelect = document.getElementById("sortTasks");
  const taskListElement = document.getElementById("taskList");

  if (sortSelect && taskListElement) {
    sortSelect.addEventListener("change", () => {
      const sortValue = sortSelect.value;
      const tasks = Array.from(taskListElement.querySelectorAll(".item-card"));

      if (tasks.length === 0) return;

      // Obtener datos de cada tarea para ordenar
      const taskData = tasks.map(task => {
        const prioridadTag = task.querySelector(".item-meta-tag:last-child");
        const prioridadText = prioridadTag ? prioridadTag.textContent.trim().toLowerCase() : "media";
        
        // Extraer prioridad (quitar el icono si existe)
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

        return {
          element: task,
          prioridad: prioridad,
          fechaLimite: fechaLimite,
          estado: estado
        };
      });

      // Funciones de ordenamiento
      const prioridadOrder = { "alta": 1, "media": 2, "baja": 3 };
      const estadoOrder = { "pendiente": 1, "en curso": 2, "completada": 3 };

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
          // Por defecto: mantener orden original (recargar página)
          return;
      }

      // Reordenar elementos en el DOM
      taskData.forEach(item => {
        taskListElement.appendChild(item.element);
      });
    });
  }

});
