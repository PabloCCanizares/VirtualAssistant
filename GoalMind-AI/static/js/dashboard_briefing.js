/**
 * MCP Dashboard Briefing
 * Loads assistant-generated cards and work items for the initial dashboard.
 */

(function() {
  'use strict';

  const endpoint = '/api/dashboard/briefing';

  function severityLabel(severity) {
    const labels = {
      critical: 'Critico',
      high: 'Alta',
      medium: 'Media',
      low: 'Baja',
      info: 'Info'
    };
    return labels[severity] || 'Info';
  }

  function escapeHtml(value) {
    return String(value || '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function renderTask(task) {
    return `
      <article class="mcp-briefing-item">
        <div class="mcp-briefing-item-main">
          <span class="mcp-briefing-pill ${escapeHtml(task.priority)}">${escapeHtml(task.priority || 'media')}</span>
          <strong>${escapeHtml(task.title)}</strong>
          <p>${escapeHtml(task.summary)}</p>
        </div>
      </article>
    `;
  }

  function renderMissingContext(item) {
    return `
      <article class="mcp-briefing-item compact">
        <strong>${escapeHtml(item.label)}</strong>
        <p>${escapeHtml(item.why)}</p>
      </article>
    `;
  }

  function renderBriefing(container, briefing) {
    const diagnosis = briefing.diagnosis || {};
    const title = container.querySelector('.mcp-briefing-title');
    const status = container.querySelector('.mcp-briefing-status');
    const summary = container.querySelector('.mcp-briefing-summary');
    const tasksContainer = container.querySelector('[data-briefing-tasks]');
    const contextContainer = container.querySelector('[data-briefing-context]');

    container.dataset.severity = diagnosis.severity || 'info';
    title.textContent = diagnosis.title || 'Lectura operativa preparada';
    status.textContent = severityLabel(diagnosis.severity);
    summary.textContent = diagnosis.summary || 'El MCP no detecta senales fuertes con los datos actuales.';

    const tasks = briefing.assistant_tasks || [];
    tasksContainer.innerHTML = tasks.length
      ? tasks.slice(0, 4).map(renderTask).join('')
      : '<span class="mcp-briefing-empty">No hay tareas sugeridas ahora mismo.</span>';

    const missing = briefing.missing_context || [];
    contextContainer.innerHTML = missing.length
      ? missing.slice(0, 4).map(renderMissingContext).join('')
      : '<span class="mcp-briefing-empty">No faltan datos clave detectados.</span>';
  }

  async function loadBriefing() {
    const container = document.getElementById('mcpDashboardBriefing');
    if (!container) return;

    try {
      const response = await fetch(endpoint);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const briefing = await response.json();
      renderBriefing(container, briefing);
      container.classList.add('loaded');
      container.classList.remove('error');
    } catch (error) {
      console.error('Error cargando briefing MCP:', error);
      container.classList.add('error');
      const title = container.querySelector('.mcp-briefing-title');
      const status = container.querySelector('.mcp-briefing-status');
      const summary = container.querySelector('.mcp-briefing-summary');
      title.textContent = 'No se pudo cargar el briefing MCP';
      status.textContent = 'Error';
      summary.textContent = 'El dashboard sigue disponible, pero la lectura operativa no se ha podido generar.';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadBriefing);
  } else {
    loadBriefing();
  }

  window.DashboardBriefing = {
    reload: loadBriefing
  };
})();
