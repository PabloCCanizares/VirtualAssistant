/**
 * Dashboard Statistics Loader
 * Carga las gráficas de estadísticas desde los endpoints de stats_controller.py
 */

(function() {
  'use strict';

  // Mapeo de data-stat a endpoint
  const STAT_ENDPOINTS = {
    'tasks_completed_month': '/stats/tasks_completed_month',
    'goals_progress': '/stats/goals_progress',
    'tasks_relevance': '/stats/tasks_relevance',
    'events_by_type': '/stats/events_by_type'
  };

  /**
   * Carga una estadística en su celda correspondiente
   * @param {HTMLElement} cell - Elemento contenedor
   * @param {string} statName - Nombre de la estadística
   */
  async function loadStat(cell, statName) {
    const endpoint = STAT_ENDPOINTS[statName];
    if (!endpoint) {
      console.warn(`Endpoint no encontrado para: ${statName}`);
      return;
    }

    try {
      const response = await fetch(endpoint);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const html = await response.text();
      cell.innerHTML = html;
      cell.classList.add('loaded');
      cell.classList.remove('loading', 'error');

      // Ejecutar scripts inline si existen en el HTML cargado
      const scripts = cell.querySelectorAll('script');
      scripts.forEach(script => {
        const newScript = document.createElement('script');
        if (script.src) {
          newScript.src = script.src;
        } else {
          newScript.textContent = script.textContent;
        }
        script.parentNode.replaceChild(newScript, script);
      });

    } catch (error) {
      console.error(`Error cargando estadística ${statName}:`, error);
      cell.classList.add('error');
      cell.classList.remove('loading');
      cell.innerHTML = `
        <div class="panel-placeholder error">
          <span class="panel-placeholder-icon">!</span>
          <span>Error al cargar</span>
          <button class="stat-retry-btn" data-stat="${statName}">Reintentar</button>
        </div>
      `;
    }
  }

  /**
   * Carga todas las estadísticas del grid
   */
  function loadAllStats() {
    const cells = document.querySelectorAll('.dashboard-stats-cell[data-stat]');

    cells.forEach(cell => {
      const statName = cell.dataset.stat;
      cell.classList.add('loading');
      loadStat(cell, statName);
    });
  }

  /**
   * Recarga una estadística específica
   * @param {string} statName - Nombre de la estadística
   */
  function reloadStat(statName) {
    const cell = document.querySelector(`.dashboard-stats-cell[data-stat="${statName}"]`);
    if (cell) {
      cell.classList.add('loading');
      loadStat(cell, statName);
    }
  }

  // Event delegation para botones de reintentar
  document.addEventListener('click', function(e) {
    if (e.target.classList.contains('stat-retry-btn')) {
      const statName = e.target.dataset.stat;
      if (statName) {
        reloadStat(statName);
      }
    }
  });

  // Inicializar cuando el DOM esté listo
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadAllStats);
  } else {
    loadAllStats();
  }

  // Exponer funciones para uso externo si es necesario
  window.DashboardStats = {
    reload: loadAllStats,
    reloadStat: reloadStat
  };

})();
