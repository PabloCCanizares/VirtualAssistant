/**
 * Category Manager - Gestion de categorias en el panel lateral del dashboard
 * GoalMind-AI
 */

(function() {
  'use strict';

  // Estado del modulo
  let categories = [];
  let selectedCategoryId = null;
  let searchTimeout = null;
  let pendingDeleteCategoryId = null;

  // Elementos del DOM
  const elements = {
    searchInput: null,
    categoryList: null,
    nameInput: null,
    insertBtn: null,
    editBtn: null,
    deleteBtn: null,
    messageEl: null,
    // Modal de confirmación
    deleteModal: null,
    deleteModalMessage: null,
    deleteModalUsageDetails: null,
    cancelDeleteBtn: null,
    confirmDeleteBtn: null
  };

  /**
   * Carga y renderiza las categorias en el sidebar lateral
   */
  function loadSidebarCategories() {
    const container = document.getElementById('sidebar-categories');
    if (!container) return;
    fetch('/categories/api/all')
      .then(r => r.json())
      .then(data => {
        if (data.success && data.categories.length > 0) {
          const seenNames = new Set();
          const uniqueCategories = data.categories.filter(function(category) {
            const normalizedName = String(category.name || '').trim().toLowerCase();
            if (!normalizedName || seenNames.has(normalizedName)) return false;
            seenNames.add(normalizedName);
            return true;
          });
          const visibleCategories = uniqueCategories.slice(0, 14);
          const remainingCount = uniqueCategories.length - visibleCategories.length;
          const pills = visibleCategories
            .map(c => `<div class="sidebar-pill">${escapeHtml(c.name)}</div>`)
            .join('');
          const morePill = remainingCount > 0
            ? `<div class="sidebar-pill sidebar-pill-more">+${remainingCount}</div>`
            : '';
          container.innerHTML = pills + morePill;
        } else {
          container.innerHTML = '<div class="sidebar-pill">Sin categorias</div>';
        }
      })
      .catch(() => {
        container.innerHTML = '<div class="sidebar-pill">Sin categorias</div>';
      });
  }

  /**
   * Inicializa el modulo cuando el DOM esta listo
   */
  function init() {
    loadSidebarCategories();
    document.addEventListener('categoriesUpdated', loadSidebarCategories);

    // Obtener referencias a elementos del DOM
    elements.searchInput = document.getElementById('category_search');
    elements.categoryList = document.getElementById('categoryList');
    elements.nameInput = document.getElementById('category_name');
    elements.insertBtn = document.getElementById('insertCategoryBtn');
    elements.editBtn = document.getElementById('editCategoryBtn');
    elements.deleteBtn = document.getElementById('deleteCategoryBtn');
    elements.messageEl = document.getElementById('categoryMessage');

    // Elementos del modal de confirmación
    elements.deleteModal = document.getElementById('deleteCategoryModal');
    elements.deleteModalMessage = document.getElementById('deleteCategoryModalMessage');
    elements.deleteModalUsageDetails = document.getElementById('deleteCategoryUsageDetails');
    elements.cancelDeleteBtn = document.getElementById('cancelDeleteCategoryBtn');
    elements.confirmDeleteBtn = document.getElementById('confirmDeleteCategoryBtn');

    // Verificar que los elementos existen
    if (!elements.categoryList) {
      return; // No estamos en la pagina correcta
    }

    // Configurar event listeners
    setupEventListeners();

    // Cargar categorias iniciales
    loadCategories();
  }

  /**
   * Configura los event listeners
   */
  function setupEventListeners() {
    // Busqueda con debounce
    if (elements.searchInput) {
      elements.searchInput.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
          searchCategories(this.value);
        }, 300);
      });
    }

    // Boton insertar
    if (elements.insertBtn) {
      elements.insertBtn.addEventListener('click', insertCategory);
    }

    // Boton editar
    if (elements.editBtn) {
      elements.editBtn.addEventListener('click', editCategory);
    }

    // Boton borrar
    if (elements.deleteBtn) {
      elements.deleteBtn.addEventListener('click', deleteCategory);
    }

    // Event delegation para clicks en la lista de categorias
    if (elements.categoryList) {
      elements.categoryList.addEventListener('click', function(e) {
        const item = e.target.closest('.category-list-item');
        if (item && item.dataset.id) {
          e.preventDefault();
          selectCategory(item.dataset.id);
        }
      });
    }

    // Enter en el input de nombre para insertar
    if (elements.nameInput) {
      elements.nameInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          if (selectedCategoryId) {
            editCategory();
          } else {
            insertCategory();
          }
        }
      });
    }

    // Event listeners para el modal de confirmación
    if (elements.cancelDeleteBtn) {
      elements.cancelDeleteBtn.addEventListener('click', hideDeleteModal);
    }

    if (elements.confirmDeleteBtn) {
      elements.confirmDeleteBtn.addEventListener('click', confirmDeleteCategory);
    }

    // Cerrar modal al hacer click fuera
    if (elements.deleteModal) {
      elements.deleteModal.addEventListener('click', function(e) {
        if (e.target === elements.deleteModal) {
          hideDeleteModal();
        }
      });
    }

    // Cerrar modal con tecla Escape
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && elements.deleteModal &&
          elements.deleteModal.style.display === 'flex') {
        hideDeleteModal();
      }
    });
  }

  /**
   * Carga todas las categorias desde el servidor
   */
  async function loadCategories() {
    try {
      const response = await fetch('/categories/api/all');
      const data = await response.json();

      if (data.success) {
        categories = data.categories || [];
        renderCategoryList(categories);
      } else {
        showMessage('Error al cargar categorias', 'error');
      }
    } catch (error) {
      console.error('Error loading categories:', error);
      showMessage('Error de conexion', 'error');
    }
  }

  /**
   * Busca categorias por nombre
   */
  async function searchCategories(query) {
    try {
      const url = query.trim() 
        ? `/categories/api/search?q=${encodeURIComponent(query.trim())}`
        : '/categories/api/all';

      const response = await fetch(url);
      const data = await response.json();

      if (data.success) {
        categories = data.categories || [];
        renderCategoryList(categories);
      }
    } catch (error) {
      console.error('Error searching categories:', error);
    }
  }

  /**
   * Renderiza la lista de categorias en el DOM
   */
  function renderCategoryList(cats) {
    if (!elements.categoryList) return;

    if (!cats || cats.length === 0) {
      elements.categoryList.innerHTML = '<li class="category-list-empty">No hay categorias</li>';
      return;
    }

    elements.categoryList.innerHTML = cats.map(cat => `
      <li class="category-list-item ${cat._id === selectedCategoryId ? 'selected' : ''}" 
          data-id="${cat._id}">
        <span class="category-item-name">${escapeHtml(cat.name)}</span>
      </li>
    `).join('');
  }

  /**
   * Selecciona una categoria
   */
  function selectCategory(categoryId) {
    // Si hacemos click en la misma, deseleccionar
    if (selectedCategoryId === categoryId) {
      selectedCategoryId = null;
      if (elements.nameInput) elements.nameInput.value = '';
      updateButtonStates();
      renderCategoryList(categories);
      return;
    }

    selectedCategoryId = categoryId;
    const category = categories.find(c => c._id === categoryId);
    
    if (category && elements.nameInput) {
      elements.nameInput.value = category.name;
    }

    updateButtonStates();
    renderCategoryList(categories);
  }

  /**
   * Actualiza el estado de los botones segun la seleccion
   */
  function updateButtonStates() {
    const hasSelection = selectedCategoryId !== null;
    
    if (elements.editBtn) {
      elements.editBtn.disabled = !hasSelection;
    }
    if (elements.deleteBtn) {
      elements.deleteBtn.disabled = !hasSelection;
    }
  }

  /**
   * Inserta una nueva categoria
   */
  async function insertCategory() {
    const name = elements.nameInput?.value?.trim();
    
    if (!name) {
      showMessage('El nombre es obligatorio', 'error');
      return;
    }

    try {
      const response = await fetch('/categories/api/add', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name })
      });

      const data = await response.json();

      if (data.success) {
        showMessage('Categoria creada correctamente', 'success');
        elements.nameInput.value = '';
        selectedCategoryId = null;
        updateButtonStates();
        loadCategories();
        
        // Disparar evento personalizado para que otros componentes se actualicen
        document.dispatchEvent(new CustomEvent('categoriesUpdated'));
      } else {
        showMessage(data.message || 'Error al crear categoria', 'error');
      }
    } catch (error) {
      console.error('Error inserting category:', error);
      showMessage('Error de conexion', 'error');
    }
  }

  /**
   * Edita la categoria seleccionada
   */
  async function editCategory() {
    if (!selectedCategoryId) {
      showMessage('Selecciona una categoria primero', 'error');
      return;
    }

    const name = elements.nameInput?.value?.trim();
    
    if (!name) {
      showMessage('El nombre es obligatorio', 'error');
      return;
    }

    try {
      const response = await fetch(`/categories/api/update/${selectedCategoryId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name })
      });

      const data = await response.json();

      if (data.success) {
        showMessage('Categoria actualizada correctamente', 'success');
        elements.nameInput.value = '';
        selectedCategoryId = null;
        updateButtonStates();
        loadCategories();
        
        // Disparar evento personalizado
        document.dispatchEvent(new CustomEvent('categoriesUpdated'));
      } else {
        showMessage(data.message || 'Error al actualizar categoria', 'error');
      }
    } catch (error) {
      console.error('Error editing category:', error);
      showMessage('Error de conexion', 'error');
    }
  }

  /**
   * Inicia el proceso de eliminación de categoría (verifica uso y muestra modal)
   */
  async function deleteCategory() {
    if (!selectedCategoryId) {
      showMessage('Selecciona una categoria primero', 'error');
      return;
    }

    const category = categories.find(c => c._id === selectedCategoryId);
    console.log('Checking usage for category:', selectedCategoryId);

    try {
      // Verificar si la categoría está siendo usada
      const response = await fetch(`/categories/api/usage/${selectedCategoryId}`);
      const data = await response.json();

      if (!response.ok) {
        if (response.status === 404) {
          showMessage('La categoria ya no existe', 'error');
          clearSelection();
          loadCategories();
          return;
        }
        throw new Error(data.message || 'Error al verificar uso de categoria');
      }

      const usage = data.usage;

      // Si tiene items asociados, mostrar modal de confirmación
      if (usage.total > 0) {
        showDeleteModal(category, usage);
      } else {
        // Si no tiene items asociados, confirmar con un simple confirm
        if (confirm(`¿Estas seguro de eliminar la categoria "${category?.name}"?`)) {
          pendingDeleteCategoryId = selectedCategoryId;
          await confirmDeleteCategory();
        }
      }
    } catch (error) {
      console.error('Error checking category usage:', error);
      showMessage('Error al verificar uso de categoria', 'error');
    }
  }

  /**
   * Muestra el modal de confirmación de eliminación
   */
  function showDeleteModal(category, usage) {
    if (!elements.deleteModal) return;

    pendingDeleteCategoryId = category._id;

    // Actualizar mensaje del modal
    if (elements.deleteModalMessage) {
      elements.deleteModalMessage.innerHTML = `
        La categoria <strong>"${escapeHtml(category.name)}"</strong> está asignada a elementos que se quedarán sin categoria:
      `;
    }

    // Actualizar detalles de uso
    if (elements.deleteModalUsageDetails) {
      elements.deleteModalUsageDetails.innerHTML = `
        <div class="modal-usage-item">
          <span class="modal-usage-item-label">Objetivos</span>
          <span class="modal-usage-item-value ${usage.goals > 0 ? 'has-items' : ''}">${usage.goals}</span>
        </div>
        <div class="modal-usage-item">
          <span class="modal-usage-item-label">Tareas</span>
          <span class="modal-usage-item-value ${usage.tasks > 0 ? 'has-items' : ''}">${usage.tasks}</span>
        </div>
        <div class="modal-usage-item">
          <span class="modal-usage-item-label">Proyectos</span>
          <span class="modal-usage-item-value ${usage.projects > 0 ? 'has-items' : ''}">${usage.projects}</span>
        </div>
        <div class="modal-usage-total">
          <span class="modal-usage-total-label">Total de elementos afectados</span>
          <span class="modal-usage-total-value">${usage.total}</span>
        </div>
      `;
    }

    // Mostrar modal
    elements.deleteModal.style.display = 'flex';
  }

  /**
   * Oculta el modal de confirmación
   */
  function hideDeleteModal() {
    if (elements.deleteModal) {
      elements.deleteModal.style.display = 'none';
    }
    pendingDeleteCategoryId = null;
  }

  /**
   * Confirma y ejecuta la eliminación de la categoría
   */
  async function confirmDeleteCategory() {
    const categoryIdToDelete = pendingDeleteCategoryId;
    hideDeleteModal();

    if (!categoryIdToDelete) {
      showMessage('Error: No hay categoria pendiente de eliminar', 'error');
      return;
    }

    console.log('Deleting category:', categoryIdToDelete);

    try {
      const response = await fetch(`/categories/api/delete/${categoryIdToDelete}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      console.log('Delete response status:', response.status);

      if (!response.ok) {
        if (response.status === 404) {
          showMessage('La categoria ya no existe', 'error');
          clearSelection();
          loadCategories();
          return;
        }
        throw new Error(`HTTP ${response.status}`);
      }

      let data;
      try {
        data = await response.json();
      } catch (jsonError) {
        console.error('Error parsing JSON response:', jsonError);
        throw new Error('Respuesta del servidor no es JSON válido');
      }

      if (data.success === true) {
        showMessage('Categoria eliminada correctamente', 'success');
        clearSelection();
        loadCategories();

        // Disparar evento personalizado
        document.dispatchEvent(new CustomEvent('categoriesUpdated'));
      } else {
        const errorMsg = data.message || 'Error al eliminar categoria';
        showMessage(errorMsg, 'error');

        if (data.message && data.message.toLowerCase().includes('no encontrada')) {
          clearSelection();
          loadCategories();
        }
      }
    } catch (error) {
      console.error('Error deleting category:', error);
      showMessage('Error de conexion', 'error');
    }
  }

  /**
   * Limpia la selección actual
   */
  function clearSelection() {
    if (elements.nameInput) elements.nameInput.value = '';
    selectedCategoryId = null;
    updateButtonStates();
  }

  /**
   * Muestra un mensaje de feedback
   */
  function showMessage(text, type = 'info') {
    if (!elements.messageEl) return;

    elements.messageEl.textContent = text;
    elements.messageEl.className = `category-message category-message-${type}`;
    
    // Auto-ocultar despues de 3 segundos
    setTimeout(() => {
      if (elements.messageEl) {
        elements.messageEl.textContent = '';
        elements.messageEl.className = 'category-message';
      }
    }, 3000);
  }

  /**
   * Escapa caracteres HTML para prevenir XSS
   */
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Exponer funciones publicas para uso externo
  window.CategoryManager = {
    loadCategories,
    getCategories: () => categories,
    refresh: loadCategories
  };

  // Inicializar cuando el DOM este listo
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
