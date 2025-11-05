document.addEventListener("DOMContentLoaded", () => {
  const taskList = document.getElementById("taskList");
  if (!taskList) return;

  let expandedItem = null;

  function isInteractiveTarget(target) {
    if (!target) return false;
    return !!target.closest("button, a, input, textarea, select, form, .task-delete-btn, .btn-edit, .btn-confirm, .btn-cancel");
  }

  // Click delegado en la lista (abre/cierra)
  taskList.addEventListener("click", (ev) => {
    const li = ev.target.closest(".task-item");
    if (!li) return;

    // Si clic en elemento interactivo, no togglear
    if (isInteractiveTarget(ev.target)) return;

    // Evita que el document capture el mismo click
    ev.stopPropagation();

    const already = li.classList.contains("expanded");

    // Cierra cualquiera abierto (si distinto)
    document.querySelectorAll(".task-item.expanded").forEach(item => {
      if (item !== li) collapseItem(item);
    });

    if (!already) expandItem(li);
    else collapseItem(li);
  });

  // Soporte teclado (Enter / Space) para abrir cuando li está enfocado
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

  // Click fuera de cualquier task -> cierra todo
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
      if (form) {
        try {
          if (typeof exitEditMode === "function") exitEditMode(form, true);
        } catch (err) {}
      }

      li.classList.remove("expanded");
      li.setAttribute("aria-expanded", "false");
      details.style.display = "none";
      details.setAttribute("aria-hidden", "true");
    }
    if (expandedItem === li) expandedItem = null;
  }

  // Inicializar handlers por item (editar, cancelar, submit)
  document.querySelectorAll(".task-item").forEach(li => {
    const form = li.querySelector(".task-edit-form");
    if (!form) return;

    const editBtn = li.querySelector(".btn-edit");
    const cancelBtn = li.querySelector(".btn-cancel");

    // stopPropagation en botones para evitar burbujeo que cierre el panel
    [editBtn, cancelBtn].forEach(btn => {
      if (!btn) return;
      btn.addEventListener("click", (e) => e.stopPropagation());
    });
  });

});

document.addEventListener("DOMContentLoaded", () => {
  const taskList = document.getElementById("taskList");
  if (!taskList) return;

  let expandedItem = null;

  // ========= Helpers =========
  function isInteractiveTarget(target) {
    return !!target.closest("button, a, input, textarea, select, form");
  }

  // ========= Expand / Collapse logic =========
  taskList.addEventListener("click", (ev) => {
    const li = ev.target.closest(".task-item");
    if (!li) return;

    // Evitar toggle si se ha pulsado un botón o control
    if (isInteractiveTarget(ev.target)) return;

    ev.stopPropagation();

    const already = li.classList.contains("expanded");
    document.querySelectorAll(".task-item.expanded").forEach(item => {
      if (item !== li) collapseItem(item);
    });

    if (!already) expandItem(li);
    else collapseItem(li);
  });

  // Click fuera → cerrar todo
  document.addEventListener("click", (ev) => {
    if (!expandedItem) return;
    if (ev.target.closest(".task-item")) return;
    document.querySelectorAll(".task-item.expanded").forEach(item => collapseItem(item));
  });

  // Escape → cerrar
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
  }

  function collapseItem(li) {
    const details = li.querySelector(".task-details");
    if (details) {
      const form = li.querySelector(".task-edit-form");
      if (form) exitEditMode(form, true);
      li.classList.remove("expanded");
      li.setAttribute("aria-expanded", "false");
      details.style.display = "none";
      details.setAttribute("aria-hidden", "true");
    }
    if (expandedItem === li) expandedItem = null;
  }

  // ========= Edit / Submit logic =========
  document.querySelectorAll(".task-item").forEach(li => {
    const form = li.querySelector(".task-edit-form");
    if (!form) return;

    const editBtn = li.querySelector(".btn-edit");
    const confirmBtn = li.querySelector(".btn-confirm");
    const cancelBtn = li.querySelector(".btn-cancel");

    const view = form.querySelector(".task-fields-view");
    const edit = form.querySelector(".task-fields-edit");
    const inputs = form.querySelectorAll("input[name], textarea[name], select[name]");
    const original = {};
    inputs.forEach(i => original[i.name] = i.value);

    // 🖊️ EDITAR
    editBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      enterEditMode(form);
    });

    // ❌ CANCELAR
    cancelBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      exitEditMode(form, true);
    });

    // ✅ CONFIRMAR (submit vía fetch)
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      e.stopPropagation();

      const url = form.action;
      const formData = new URLSearchParams();
      inputs.forEach(i => formData.append(i.name, i.value));

      try {
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: formData.toString()
        });

        if (resp.ok) {
          updateViewFromForm(form);
          exitEditMode(form, false);
        } else {
          const text = await resp.text();
          alert("Error al actualizar: " + resp.status + " " + text);
        }
      } catch (err) {
        alert("Error de red: " + err);
      }
    });

    // ====== Funciones auxiliares ======

    function enterEditMode(form) {
      view.style.display = "none";
      edit.style.display = "flex";
      edit.style.flexDirection = "column";
      edit.style.gap = "8px";

      editBtn.style.display = "none";
      confirmBtn.style.display = "inline-block";
      cancelBtn.style.display = "inline-block";
    }

    function exitEditMode(form, restore = true) {
      if (restore) {
        inputs.forEach(i => {
          if (original.hasOwnProperty(i.name)) i.value = original[i.name];
        });
      } else {
        inputs.forEach(i => original[i.name] = i.value);
      }

      view.style.display = "flex";
      edit.style.display = "none";

      editBtn.style.display = "inline-block";
      confirmBtn.style.display = "none";
      cancelBtn.style.display = "none";

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

      li.querySelector(".task-title").textContent = contentInput.value;
      form.querySelector(".task-desc-text").textContent = descTextarea.value || "(sin descripción)";
      form.querySelector(".task-est-text").textContent = estadoSel.value;
      form.querySelector(".task-cat-text").textContent = categoriaInput.value || "—";
      form.querySelector(".task-prio-text").textContent = prioSel.value;

      const deadlineEl = li.querySelector(".task-deadline");
      if (fechaInput.value) {
        if (deadlineEl) deadlineEl.textContent = fechaInput.value;
        else {
          const p = document.createElement("p");
          p.className = "task-deadline";
          p.textContent = fechaInput.value;
          li.querySelector(".task-content").appendChild(p);
        }
      } else if (deadlineEl) {
        deadlineEl.remove();
      }
    }
  });
});