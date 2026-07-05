/**
 * Reloads the server-calculated dashboard pulse without a full page refresh.
 */

(function() {
  'use strict';

  const endpoint = '/api/dashboard/summary';
  const fallbackBars = [12, 12, 12, 12, 12, 12, 12];

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function classToken(value, fallback) {
    const token = String(value || '').toLowerCase().replace(/[^a-z0-9_-]/g, '');
    return token || fallback;
  }

  function progress(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number)) return 0;
    return Math.max(0, Math.min(100, Math.round(number)));
  }

  function renderSummaryCard(card) {
    const tone = classToken(card.tone, 'neutral');
    const icon = classToken(card.icon, 'pulse');
    const width = progress(card.progress);

    return `
      <article class="gm-summary-card gm-tone-${tone}">
        <div class="gm-summary-topline">
          <span class="gm-summary-icon gm-summary-icon-${icon}" aria-hidden="true"></span>
          <span>${escapeHtml(card.label)}</span>
        </div>
        <strong>${escapeHtml(card.value)}</strong>
        <small>${escapeHtml(card.detail)}</small>
        <span class="gm-summary-subdetail">${escapeHtml(card.subdetail)}</span>
        <i class="gm-kpi-progress"><em style="width: ${width}%"></em></i>
      </article>
    `;
  }

  function renderStat(stat) {
    const tone = classToken(stat.tone, 'neutral');
    const trend = classToken(stat.trend, 'neutral');
    const width = progress(stat.progress);
    const bars = Array.isArray(stat.bars) && stat.bars.length ? stat.bars : fallbackBars;

    return `
      <article class="gm-stat-tile gm-tone-${tone}">
        <span>${escapeHtml(stat.label)}</span>
        <small>${escapeHtml(stat.period)}</small>
        <strong>${escapeHtml(stat.value)}</strong>
        <em class="gm-stat-delta gm-trend-${trend}">${escapeHtml(stat.delta)}</em>
        <i class="gm-progress"><em style="width: ${width}%"></em></i>
        <div class="gm-mini-bars" aria-hidden="true">
          ${bars.map(bar => `<span style="height: ${progress(bar)}%"></span>`).join('')}
        </div>
      </article>
    `;
  }

  function setLoading(isLoading) {
    const button = document.querySelector('[data-dashboard-summary-reload]');
    if (!button) return;
    button.classList.toggle('is-loading', isLoading);
    button.disabled = isLoading;
  }

  function renderSummary(payload) {
    const summaryStrip = document.querySelector('.gm-summary-strip');
    const statGrid = document.querySelector('.gm-stat-grid');

    if (summaryStrip && Array.isArray(payload.summary_cards)) {
      summaryStrip.innerHTML = payload.summary_cards.map(renderSummaryCard).join('');
      summaryStrip.dataset.loadedAt = new Date().toISOString();
    }

    if (statGrid && Array.isArray(payload.stats)) {
      statGrid.innerHTML = payload.stats.map(renderStat).join('');
      statGrid.dataset.loadedAt = new Date().toISOString();
    }
  }

  async function reloadSummary() {
    setLoading(true);
    try {
      const response = await fetch(endpoint, {
        headers: { Accept: 'application/json' },
        cache: 'no-store'
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      renderSummary(await response.json());
    } catch (error) {
      console.error('Error recargando resumen del dashboard:', error);
    } finally {
      setLoading(false);
    }
  }

  function bindReload() {
    const button = document.querySelector('[data-dashboard-summary-reload]');
    if (button) {
      button.addEventListener('click', reloadSummary);
    }

    document.addEventListener('dashboard:summary:reload', reloadSummary);
    document.addEventListener('visibilitychange', function() {
      if (document.visibilityState === 'visible') {
        reloadSummary();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindReload);
  } else {
    bindReload();
  }

  window.DashboardSummary = {
    reload: reloadSummary
  };
})();
