/**
 * MCP Dashboard Briefing
 * Hydrates the operational brain panel with read-only assistant suggestions.
 */

(function() {
  'use strict';

  const endpoint = '/api/dashboard/briefing';

  function severityLabel(severity) {
    const labels = {
      critical: 'Riesgo alto',
      high: 'Riesgo alto',
      medium: 'Riesgo medio',
      low: 'Estable',
      info: 'Info'
    };
    return labels[severity] || 'Info';
  }

  function confidenceLabel(severity) {
    const labels = {
      critical: 'Alta',
      high: 'Alta',
      medium: 'Media',
      low: 'Baja',
      info: 'Baja'
    };
    return labels[severity] || 'Media';
  }

  function toneFromSeverity(severity) {
    if (severity === 'critical' || severity === 'high') return 'danger';
    if (severity === 'medium') return 'warn';
    if (severity === 'low') return 'accent';
    return 'neutral';
  }

  function escapeHtml(value) {
    return String(value || '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function setText(container, selector, value) {
    const node = container.querySelector(selector);
    if (node) node.textContent = value;
  }

  function renderBrainInsight(card) {
    const tone = toneFromSeverity(card.severity);
    return `
      <article class="gm-brain-row gm-tone-${escapeHtml(tone)}">
        <span class="gm-brain-dot" aria-hidden="true"></span>
        <span>
          <strong>${escapeHtml(card.title)}</strong>
          <small>${escapeHtml(card.summary)}</small>
        </span>
        <em>${escapeHtml(confidenceLabel(card.severity))}</em>
      </article>
    `;
  }

  function renderBrainAction(task) {
    const tag = task.requires_confirmation ? 'confirmar' : (task.suggested_tool ? 'MCP' : 'IA');
    return `
      <article class="gm-brain-action-row" data-action-kind="${escapeHtml(task.type)}">
        <span>
          <strong>${escapeHtml(task.title)}</strong>
          <small>${escapeHtml(task.summary)}</small>
        </span>
        <em>${escapeHtml(tag)}</em>
      </article>
    `;
  }

  function renderBrainMissing(item) {
    return `<em title="${escapeHtml(item.why)}">${escapeHtml(item.label || item.field)}</em>`;
  }

  function renderOperationalBrain(container, briefing) {
    const diagnosis = briefing.diagnosis || {};
    const cards = briefing.cards || [];
    const tasks = briefing.assistant_tasks || [];
    const missing = briefing.missing_context || [];
    const severity = diagnosis.severity || 'info';

    container.dataset.severity = severity;
    setText(container, '[data-brain-status]', severityLabel(severity));

    const updated = container.querySelector('[data-brain-updated]');
    if (updated) {
      const stamp = new Date();
      updated.textContent = `Actualizado ${String(stamp.getHours()).padStart(2, '0')}:${String(stamp.getMinutes()).padStart(2, '0')}`;
    }

    const insightContainer = container.querySelector('[data-brain-insights]');
    if (insightContainer) {
      insightContainer.innerHTML = cards.length
        ? cards.slice(0, 3).map(renderBrainInsight).join('')
        : '<div class="gm-brain-empty">No hay senales fuertes ahora mismo.</div>';
    }
    setText(container, '[data-brain-insight-count]', `${Math.min(cards.length, 3)} senales`);

    const actionContainer = container.querySelector('[data-brain-actions]');
    if (actionContainer) {
      actionContainer.innerHTML = tasks.length
        ? tasks.slice(0, 3).map(renderBrainAction).join('')
        : '<div class="gm-brain-empty">Sin acciones preparadas.</div>';
    }

    const missingContainer = container.querySelector('[data-brain-missing]');
    if (missingContainer) {
      missingContainer.innerHTML = missing.length
        ? missing.slice(0, 5).map(renderBrainMissing).join('')
        : '<em>contexto suficiente</em>';
    }
  }

  function renderLegacyTask(task) {
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

  function renderLegacyMissing(item) {
    return `
      <article class="mcp-briefing-item compact">
        <strong>${escapeHtml(item.label)}</strong>
        <p>${escapeHtml(item.why)}</p>
      </article>
    `;
  }

  function renderLegacyBriefing(container, briefing) {
    const diagnosis = briefing.diagnosis || {};
    const title = container.querySelector('.mcp-briefing-title');
    const status = container.querySelector('.mcp-briefing-status');
    const summary = container.querySelector('.mcp-briefing-summary');
    const tasksContainer = container.querySelector('[data-briefing-tasks]');
    const contextContainer = container.querySelector('[data-briefing-context]');

    container.dataset.severity = diagnosis.severity || 'info';
    if (title) title.textContent = diagnosis.title || 'Lectura operativa preparada';
    if (status) status.textContent = severityLabel(diagnosis.severity);
    if (summary) summary.textContent = diagnosis.summary || 'El MCP no detecta senales fuertes con los datos actuales.';

    const tasks = briefing.assistant_tasks || [];
    if (tasksContainer) {
      tasksContainer.innerHTML = tasks.length
        ? tasks.slice(0, 4).map(renderLegacyTask).join('')
        : '<span class="mcp-briefing-empty">No hay tareas sugeridas ahora mismo.</span>';
    }

    const missing = briefing.missing_context || [];
    if (contextContainer) {
      contextContainer.innerHTML = missing.length
        ? missing.slice(0, 4).map(renderLegacyMissing).join('')
        : '<span class="mcp-briefing-empty">No faltan datos clave detectados.</span>';
    }
  }

  async function loadBriefing() {
    const brain = document.getElementById('operationalBrainPanel');
    const legacy = document.getElementById('mcpDashboardBriefing');
    if (!brain && !legacy) return;

    try {
      const response = await fetch(endpoint);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const briefing = await response.json();

      if (brain) {
        renderOperationalBrain(brain, briefing);
        brain.classList.add('loaded');
        brain.classList.remove('error');
      }
      if (legacy) {
        renderLegacyBriefing(legacy, briefing);
        legacy.classList.add('loaded');
        legacy.classList.remove('error');
      }
    } catch (error) {
      console.error('Error cargando briefing MCP:', error);
      if (brain) {
        brain.classList.add('error');
        setText(brain, '[data-brain-status]', 'IA no disponible');
      }
      if (legacy) {
        legacy.classList.add('error');
        setText(legacy, '.mcp-briefing-title', 'No se pudo cargar el briefing MCP');
        setText(legacy, '.mcp-briefing-status', 'Error');
        setText(legacy, '.mcp-briefing-summary', 'El dashboard sigue disponible, pero la lectura operativa no se ha podido generar.');
      }
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
