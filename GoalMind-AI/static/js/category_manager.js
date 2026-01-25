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

  // Elementos del DOM
  const elements = {
    searchInput: null,
    categoryList: null,
    nameInput: null,
    insertBtn: null,
    editBtn: null,
    deleteBtn: null,
    messageEl: null
  };

  /**
   * Inicializa el modulo cuando el DOM esta listo
   */
  function init() {
    // Obtener referencias a elementos del DOM
    elements.searchInput = document.getElementById('category_search');
    elements.categoryList = document.getElementById('categoryList');
    elements.nameInput = document.getElementById('category_name');
    elements.insertBtn = document.getElementById('insertCategoryBtn');
    elements.editBtn = document.getElementById('editCategoryBtn');
    elements.deleteBtn = document.getElementById('deleteCategoryBtn');
    elements.messageEl = document.getElementById('categoryMessage');

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
   * Elimina la categoria seleccionada
   */
  async function deleteCategory() {
    if (!selectedCategoryId) {
      showMessage('Selecciona una categoria primero', 'error');
      return;
    }

    // Confirmar eliminacion
    const category = categories.find(c => c._id === selectedCategoryId);
    if (!confirm(`¿Estas seguro de eliminar la categoria "${category?.name}"?`)) {
      return;
    }

    console.log('Deleting category:', selectedCategoryId);
    
    try {
      const response = await fetch(`/categories/api/delete/${selectedCategoryId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      console.log('Delete response status:', response.status);

      // Verificar si la respuesta es válida antes de parsear JSON
      if (!response.ok) {
        if (response.status === 404) {
          showMessage('La categoria ya no existe', 'error');
          // Limpiar estado local ya que no existe en el servidor
          elements.nameInput.value = '';
          selectedCategoryId = null;
          updateButtonStates();
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
        console.error('Response text:', await response.text());
        throw new Error('Respuesta del servidor no es JSON válido');
      }

      // Validar que la respuesta tenga la estructura esperada
      if (!data || typeof data !== 'object') {
        throw new Error('Respuesta del servidor inválida');
      }

      // Manejar el caso donde data.success pueda ser booleano o undefined/null
      if (data.success === true) {
        showMessage('Categoria eliminada correctamente', 'success');
        elements.nameInput.value = '';
        selectedCategoryId = null;
        updateButtonStates();
        loadCategories();
        
        // Disparar evento personalizado
        document.dispatchEvent(new CustomEvent('categoriesUpdated'));
      } else {
        // Manejar caso donde success es false, null, undefined o booleano false
        const errorMsg = (data && data.message) ? data.message : 'Error al eliminar categoria';
        showMessage(errorMsg, 'error');
        
        // Si el servidor indica que no existe o hay un 404, limpiar el estado local
        if (response.status === 404 || (data.message && data.message.toLowerCase().includes('no encontrada'))) {
          elements.nameInput.value = '';
          selectedCategoryId = null;
          updateButtonStates();
          loadCategories();
        }
      }
    } catch (error) {
      console.error('Error deleting category:', error);
      
      // Si hay error de JSON o conexión, limpiar estado local para evitar intentos múltiples
      if (error.message.includes('JSON') || error.message.includes('conexion')) {
        elements.nameInput.value = '';
        selectedCategoryId = null;
        updateButtonStates();
        loadCategories();
      }
      
      showMessage('Error de conexion', 'error');
    }
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
