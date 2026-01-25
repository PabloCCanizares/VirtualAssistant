/**
 * Category Multi-Select Component
 * Componente reutilizable para seleccion multiple de categorias
 * GoalMind-AI
 */

(function() {
  'use strict';

  // Cache de categorias cargadas
  let categoriesCache = null;
  let categoriesCacheTime = 0;
  const CACHE_DURATION = 30000; // 30 segundos

  /**
   * Carga las categorias desde el servidor (con cache)
   */
  async function loadCategories(forceRefresh = false) {
    const now = Date.now();
    if (!forceRefresh && categoriesCache && (now - categoriesCacheTime) < CACHE_DURATION) {
      return categoriesCache;
    }

    try {
      const response = await fetch('/categories/api/all');
      const data = await response.json();
      if (data.success) {
        categoriesCache = data.categories || [];
        categoriesCacheTime = now;
        return categoriesCache;
      }
    } catch (error) {
      console.error('Error loading categories:', error);
    }
    return categoriesCache || [];
  }

  /**
   * Invalida el cache de categorias
   */
  function invalidateCache() {
    categoriesCache = null;
    categoriesCacheTime = 0;
  }

  /**
   * Inicializa un selector multiple de categorias
   * @param {HTMLElement} container - El contenedor del selector
   * @param {Object} options - Opciones de configuracion
   */
  async function initCategorySelector(container, options = {}) {
    if (!container) return;

    const {
      name = 'categorias',
      selectedIds = [],
      placeholder = 'Seleccionar categorias...',
      allowCreate = true,
      onChange = null
    } = options;

    // Cargar categorias
    const categories = await loadCategories();

    // Estado interno
    let selected = new Set(selectedIds.map(String));
    let isOpen = false;
    let searchQuery = '';

    // Crear estructura HTML
    container.innerHTML = `
      <div class="category-multi-select">
        <div class="category-multi-select-trigger">
          <div class="selected-categories-tags"></div>
          <span class="category-multi-select-placeholder">${placeholder}</span>
        </div>
        <input type="hidden" name="${name}" value="">
        <div class="category-multi-select-dropdown">
          <div class="category-multi-select-search">
            <input type="text" placeholder="Buscar categoria..." class="category-search-input">
          </div>
          <div class="category-multi-select-options"></div>
          ${allowCreate ? `
          <div class="category-multi-select-add" style="display: none;">
            <span>+ Crear categoria "</span><span class="new-category-name"></span><span>"</span>
          </div>
          ` : ''}
        </div>
      </div>
    `;

    // Referencias a elementos
    const trigger = container.querySelector('.category-multi-select-trigger');
    const dropdown = container.querySelector('.category-multi-select-dropdown');
    const hiddenInput = container.querySelector(`input[name="${name}"]`);
    const tagsContainer = container.querySelector('.selected-categories-tags');
    const placeholderEl = container.querySelector('.category-multi-select-placeholder');
    const searchInput = container.querySelector('.category-search-input');
    const optionsContainer = container.querySelector('.category-multi-select-options');
    const addNewEl = container.querySelector('.category-multi-select-add');
    const newCategoryNameEl = container.querySelector('.new-category-name');

    /**
     * Actualiza el valor del input hidden
     */
    function updateHiddenValue() {
      const ids = Array.from(selected);
      hiddenInput.value = ids.join(',');
      if (onChange) onChange(ids);
    }

    /**
     * Renderiza los tags seleccionados
     */
    function renderTags() {
      tagsContainer.innerHTML = '';
      
      if (selected.size === 0) {
        placeholderEl.style.display = '';
        return;
      }

      placeholderEl.style.display = 'none';
      
      selected.forEach(id => {
        const cat = categories.find(c => c._id === id);
        if (!cat) return;

        const tag = document.createElement('span');
        tag.className = 'category-tag';
        tag.innerHTML = `
          <span>${escapeHtml(cat.name)}</span>
          <button type="button" class="category-tag-remove" data-id="${id}">&times;</button>
        `;
        tagsContainer.appendChild(tag);
      });

      // Event listeners para remover tags
      tagsContainer.querySelectorAll('.category-tag-remove').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const id = btn.dataset.id;
          selected.delete(id);
          renderTags();
          renderOptions();
          updateHiddenValue();
        });
      });
    }

    /**
     * Renderiza las opciones del dropdown
     */
    function renderOptions() {
      const filteredCategories = categories.filter(cat => 
        cat.name.toLowerCase().includes(searchQuery.toLowerCase())
      );

      if (filteredCategories.length === 0) {
        optionsContainer.innerHTML = '<div class="category-multi-select-empty">No hay categorias</div>';
        
        // Mostrar opcion de crear si esta habilitado y hay texto de busqueda
        if (allowCreate && searchQuery.trim()) {
          addNewEl.style.display = '';
          newCategoryNameEl.textContent = searchQuery.trim();
        } else if (addNewEl) {
          addNewEl.style.display = 'none';
        }
        return;
      }

      if (addNewEl) {
        addNewEl.style.display = 'none';
      }

      optionsContainer.innerHTML = filteredCategories.map(cat => `
        <label class="category-multi-select-option ${selected.has(cat._id) ? 'selected' : ''}">
          <input type="checkbox" value="${cat._id}" ${selected.has(cat._id) ? 'checked' : ''}>
          <span class="category-multi-select-option-label">${escapeHtml(cat.name)}</span>
        </label>
      `).join('');

      // Event listeners para checkboxes
      optionsContainer.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
        checkbox.addEventListener('change', () => {
          const id = checkbox.value;
          if (checkbox.checked) {
            selected.add(id);
          } else {
            selected.delete(id);
          }
          renderTags();
          renderOptions();
          updateHiddenValue();
        });
      });
    }

    /**
     * Abre/cierra el dropdown
     */
    function toggleDropdown(open) {
      isOpen = open !== undefined ? open : !isOpen;
      dropdown.classList.toggle('open', isOpen);
      trigger.classList.toggle('active', isOpen);
      
      if (isOpen) {
        searchInput.focus();
        renderOptions();
      }
    }

    // Event listeners
    trigger.addEventListener('click', (e) => {
      if (!e.target.closest('.category-tag-remove')) {
        toggleDropdown();
      }
    });

    searchInput.addEventListener('input', (e) => {
      searchQuery = e.target.value;
      renderOptions();
      
      // Mostrar opcion de crear si hay texto
      if (allowCreate && searchQuery.trim()) {
        const exists = categories.some(c => 
          c.name.toLowerCase() === searchQuery.trim().toLowerCase()
        );
        if (!exists) {
          addNewEl.style.display = '';
          newCategoryNameEl.textContent = searchQuery.trim();
        } else {
          addNewEl.style.display = 'none';
        }
      }
    });

    // Crear nueva categoria
    if (addNewEl) {
      addNewEl.addEventListener('click', async () => {
        const name = searchQuery.trim();
        if (!name) return;

        try {
          const response = await fetch('/categories/api/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
          });

          const data = await response.json();
          if (data.success && data.category) {
            // Agregar a la lista local
            categories.push(data.category);
            invalidateCache();
            
            // Seleccionar la nueva categoria
            selected.add(data.category._id);
            searchQuery = '';
            searchInput.value = '';
            
            renderTags();
            renderOptions();
            updateHiddenValue();
            
            // Notificar a otros componentes
            document.dispatchEvent(new CustomEvent('categoriesUpdated'));
          }
        } catch (error) {
          console.error('Error creating category:', error);
        }
      });
    }

    // Cerrar al hacer click fuera
    document.addEventListener('click', (e) => {
      if (!container.contains(e.target)) {
        toggleDropdown(false);
      }
    });

    // Cerrar con Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && isOpen) {
        toggleDropdown(false);
      }
    });

    // Escuchar actualizaciones de categorias
    document.addEventListener('categoriesUpdated', async () => {
      const newCategories = await loadCategories(true);
      categories.length = 0;
      categories.push(...newCategories);
      renderOptions();
    });

    // Render inicial
    renderTags();
    updateHiddenValue();

    // Retornar API del componente
    return {
      getSelected: () => Array.from(selected),
      setSelected: (ids) => {
        selected = new Set(ids.map(String));
        renderTags();
        renderOptions();
        updateHiddenValue();
      },
      refresh: async () => {
        const newCategories = await loadCategories(true);
        categories.length = 0;
        categories.push(...newCategories);
        renderOptions();
      }
    };
  }

  /**
   * Escapa caracteres HTML
   */
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * Inicializa todos los selectores de categoria en la pagina
   */
  async function initAllCategorySelectors() {
    const containers = document.querySelectorAll('[data-category-selector]');
    
    for (const container of containers) {
      const name = container.dataset.name || 'categorias';
      const selectedStr = container.dataset.selected || '';
      const selectedIds = selectedStr ? selectedStr.split(',').filter(Boolean) : [];
      const allowCreate = container.dataset.allowCreate !== 'false';
      
      await initCategorySelector(container, {
        name,
        selectedIds,
        allowCreate
      });
    }
  }

  // Exponer API global
  window.CategorySelector = {
    init: initCategorySelector,
    initAll: initAllCategorySelectors,
    loadCategories,
    invalidateCache
  };

  // Auto-inicializar cuando el DOM este listo
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAllCategorySelectors);
  } else {
    initAllCategorySelectors();
  }

})();
