/**
 * Weekly meeting with the agent.
 * Uses the MCP bridge and PlanningSessions as durable weekly memory.
 */

(function() {
  'use strict';

  const endpoints = {
    current: '/api/mcp/planning/weekly/current',
    shouldStart: '/api/mcp/planning/weekly/should-start',
    start: '/api/mcp/planning/weekly/start'
  };

  const state = {
    session: null,
    plan: null,
    questions: [],
    reason: '',
    source: '',
    mcpTools: []
  };

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function fieldId(field) {
    return `weekly-meeting-${String(field || '').replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  }

  function asArray(value) {
    if (Array.isArray(value)) return value;
    if (value === null || value === undefined || value === '') return [];
    return [String(value)];
  }

  function answerText(value) {
    if (Array.isArray(value)) return value.join('\n');
    return value ?? '';
  }

  function formatHours(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number) || number <= 0) return '0h';
    const rounded = Math.round(number * 10) / 10;
    return `${rounded}h`;
  }

  function minutesToHours(minutes) {
    return formatHours(Number(minutes || 0) / 60);
  }

  function classToken(value, fallback) {
    const token = String(value || '').toLowerCase().replace(/[^a-z0-9_-]/g, '');
    return token || fallback;
  }

  function questionTone(field) {
    const tones = {
      weekly_available_hours: 'capacity',
      current_energy: 'energy',
      weekly_top_priorities: 'focus',
      fixed_commitments: 'fixed',
      available_windows: 'windows',
      avoid_this_week: 'avoid',
      success_criteria: 'success',
      notes: 'notes'
    };
    return tones[field] || 'notes';
  }

  function currentAnswers() {
    return (state.session && state.session.answers) || {};
  }

  function hasAnswer(value) {
    if (Array.isArray(value)) return value.length > 0;
    return value !== undefined && value !== null && String(value).trim() !== '';
  }

  function listCount(value) {
    if (Array.isArray(value)) return value.length;
    if (!hasAnswer(value)) return 0;
    return String(value).split(/\n|,|;/).map(item => item.trim()).filter(Boolean).length;
  }

  function setText(root, selector, value) {
    const node = root.querySelector(selector);
    if (node) node.textContent = value;
  }

  function setFill(root, selector, value) {
    const node = root.querySelector(selector);
    if (!node) return;
    const number = Number(value || 0);
    const pct = Number.isFinite(number) ? Math.max(0, Math.min(100, Math.round(number))) : 0;
    node.style.width = `${pct}%`;
  }

  async function jsonRequest(url, options) {
    const response = await fetch(url, {
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json'
      },
      cache: 'no-store',
      ...options
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    return payload;
  }

  function setBusy(root, isBusy) {
    root.classList.toggle('is-loading', isBusy);
    root.querySelectorAll('button').forEach(button => {
      button.disabled = isBusy;
    });
  }

  function setStatus(root, label, detail) {
    const stateNode = root.querySelector('[data-weekly-meeting-state]');
    const reasonNode = root.querySelector('[data-weekly-meeting-reason]');
    if (stateNode) stateNode.textContent = label;
    if (reasonNode) reasonNode.textContent = detail || '';
  }

  function questionInput(question, answers) {
    const field = question.field;
    const id = fieldId(field);
    const value = answerText((answers || {})[field]);
    const required = question.required ? 'required' : '';

    if (question.type === 'choice') {
      const options = asArray(question.options);
      return `
        <select id="${escapeHtml(id)}" data-weekly-field="${escapeHtml(field)}" ${required}>
          <option value=""></option>
          ${options.map(option => `
            <option value="${escapeHtml(option)}" ${String(value) === String(option) ? 'selected' : ''}>${escapeHtml(option)}</option>
          `).join('')}
        </select>
      `;
    }

    if (question.type === 'number') {
      return `
        <input id="${escapeHtml(id)}" data-weekly-field="${escapeHtml(field)}" type="number" min="0" max="120" step="0.5" value="${escapeHtml(value)}" ${required}>
      `;
    }

    const rows = question.type === 'list' ? 2 : 3;
    return `
      <textarea id="${escapeHtml(id)}" data-weekly-field="${escapeHtml(field)}" rows="${rows}" ${required}>${escapeHtml(value)}</textarea>
    `;
  }

  function renderQuestions(root) {
    const container = root.querySelector('[data-weekly-meeting-fields]');
    if (!container) return;
    const answers = currentAnswers();
    const questions = state.questions || [];

    container.innerHTML = questions.length
      ? questions.map(question => `
          <label class="gm-weekly-meeting-field gm-weekly-field-${escapeHtml(classToken(questionTone(question.field), 'notes'))}" title="${escapeHtml(question.why || '')}">
            <span>
              ${escapeHtml(question.label || question.field)}
              <em>${question.required ? 'clave' : 'opcional'}</em>
            </span>
            ${questionInput(question, answers)}
          </label>
        `).join('')
      : '<div class="gm-brain-empty">No hay preguntas de planificacion disponibles.</div>';
  }

  function planTaskTitle(item) {
    const task = item.task || {};
    return task.contenido || task.titulo || task.title || 'Tarea';
  }

  function renderPlan(root) {
    const plan = state.plan || (state.session && state.session.generated_plan);
    const capacity = root.querySelector('[data-weekly-meeting-capacity]');
    const focus = root.querySelector('[data-weekly-meeting-focus]');
    const list = root.querySelector('[data-weekly-meeting-plan-list]');
    const mcp = root.querySelector('[data-weekly-meeting-mcp-copy]');

    if (!plan) {
      if (capacity) capacity.textContent = 'Sin plan';
      if (focus) focus.textContent = state.session ? 'Contexto guardado, plan pendiente.' : 'Esperando reunion semanal.';
      if (list) list.innerHTML = '<div class="gm-brain-empty">El plan aparecera aqui cuando guardes la reunion.</div>';
      setText(root, '[data-weekly-plan-count]', '0 acciones');
      setFill(root, '[data-weekly-capacity-fill]', 0);
      if (mcp) {
        mcp.textContent = state.source === 'mcp'
          ? `MCP conectado: ${(state.mcpTools || []).slice(0, 3).join(', ')}`
          : 'Listo para transformar el plan en acciones confirmables.';
      }
      return;
    }

    const cap = plan.capacity || {};
    const focusData = plan.focus || {};
    const items = Array.isArray(plan.do_this_week) ? plan.do_this_week : [];
    const priorities = Array.isArray(focusData.priorities) ? focusData.priorities : [];
    const available = formatHours(cap.available_hours);
    const effective = minutesToHours(cap.effective_budget_minutes);
    const planned = minutesToHours(cap.planned_minutes);
    const effectiveMinutes = Number(cap.effective_budget_minutes || 0);
    const plannedMinutes = Number(cap.planned_minutes || 0);
    const capacityPct = effectiveMinutes > 0 ? (plannedMinutes / effectiveMinutes) * 100 : 0;

    if (capacity) capacity.textContent = `${planned} / ${effective}`;
    setFill(root, '[data-weekly-capacity-fill]', capacityPct);
    if (focus) {
      focus.textContent = priorities.length
        ? priorities.slice(0, 3).join(' · ')
        : (focusData.success_criteria || `Capacidad declarada: ${available}`);
    }
    if (focus && priorities.length) {
      focus.textContent = priorities.slice(0, 3).join(' / ');
    }
    setText(root, '[data-weekly-plan-count]', `${items.length} acciones`);
    if (list) {
      list.innerHTML = items.length
        ? items.slice(0, 6).map(item => `
            <article class="gm-weekly-meeting-plan-item">
              <b aria-hidden="true"></b>
              <span>
                <strong>${escapeHtml(planTaskTitle(item))}</strong>
                <small>${escapeHtml(item.reason || '')}</small>
              </span>
              <em>${minutesToHours(item.estimated_minutes)}</em>
            </article>
          `).join('')
        : '<div class="gm-brain-empty">No hay tareas claras para esta semana.</div>';
    }
    if (mcp) {
      mcp.textContent = plan.missing_questions && plan.missing_questions.length
        ? 'Faltan datos antes de ejecutar acciones.'
        : `Plan generado via MCP: ${(state.mcpTools || []).slice(-2).join(', ')}`;
    }
  }

  function updateSignals(root) {
    const answers = currentAnswers();
    const required = (state.questions || []).filter(question => question.required);
    const answeredRequired = required.filter(question => hasAnswer(answers[question.field]));
    const completion = required.length ? (answeredRequired.length / required.length) * 100 : (state.session ? 100 : 0);
    const priorities = listCount(answers.weekly_top_priorities);
    const available = hasAnswer(answers.weekly_available_hours)
      ? formatHours(answers.weekly_available_hours)
      : 'Sin dato';
    const energy = hasAnswer(answers.current_energy) ? String(answers.current_energy) : 'Pendiente';
    const success = hasAnswer(answers.success_criteria) ? String(answers.success_criteria) : 'Criterio no fijado';
    const windows = listCount(answers.available_windows);
    const statusLabel = state.session
      ? (state.session.status === 'planned' ? 'Plan listo' : 'Sesion activa')
      : 'Sesion sin iniciar';

    setText(root, '[data-weekly-signal-capacity]', available);
    setText(root, '[data-weekly-signal-budget]', windows ? `${windows} ventanas disponibles` : 'Presupuesto semanal');
    setText(root, '[data-weekly-signal-energy]', energy);
    setText(root, '[data-weekly-signal-session]', statusLabel);
    setText(root, '[data-weekly-signal-focus]', `${priorities} frentes`);
    setText(root, '[data-weekly-signal-success]', success);
    setText(root, '[data-weekly-signal-progress]', `${Math.round(completion)}%`);
    setText(root, '[data-weekly-signal-next]', completion >= 100 ? 'Contexto suficiente' : `${required.length - answeredRequired.length} claves pendientes`);
    setText(root, '[data-weekly-source]', state.source === 'mcp' ? 'MCP conectado' : 'MCP');
  }

  function applyMcpMeta(payload) {
    state.source = payload.source || state.source;
    state.mcpTools = Array.isArray(payload.mcp_tools) ? payload.mcp_tools : state.mcpTools;
  }

  function render(root) {
    const session = state.session;
    if (!session) {
      setStatus(root, 'Sin reunion semanal', state.reason || 'Puedes iniciarla cuando quieras.');
    } else if (session.status === 'planned') {
      setStatus(root, 'Plan semanal preparado', 'La reunion ya tiene plan generado.');
    } else if (session.status === 'ready_for_plan') {
      setStatus(root, 'Contexto completo', 'Listo para generar el plan semanal.');
    } else {
      setStatus(root, 'Reunion en curso', 'Faltan algunos datos de contexto.');
    }
    renderQuestions(root);
    renderPlan(root);
    updateSignals(root);
  }

  async function load(root) {
    const current = await jsonRequest(endpoints.current);
    applyMcpMeta(current);
    state.session = current.session || null;
    state.plan = current.plan || (state.session && state.session.generated_plan) || null;
    state.questions = current.questions || current.next_questions || [];
    state.reason = '';

    if (!state.session) {
      const suggestion = await jsonRequest(endpoints.shouldStart);
      applyMcpMeta(suggestion);
      state.reason = suggestion.reason || '';
      state.questions = suggestion.questions || state.questions || [];
    }

    render(root);
  }

  async function ensureSession(root) {
    if (state.session && state.session._id) return state.session;
    const payload = await jsonRequest(endpoints.start, { method: 'POST', body: '{}' });
    applyMcpMeta(payload);
    state.session = payload.session || null;
    state.questions = payload.questions || payload.next_questions || state.questions;
    state.plan = (state.session && state.session.generated_plan) || null;
    render(root);
    return state.session;
  }

  function collectAnswers(root) {
    const answers = [];
    root.querySelectorAll('[data-weekly-field]').forEach(input => {
      if (String(input.value || '').trim() === '') return;
      answers.push({
        field: input.dataset.weeklyField,
        value: input.value
      });
    });
    return answers;
  }

  async function saveAnswers(root) {
    const session = await ensureSession(root);
    if (!session || !session._id) return null;

    let latest = null;
    for (const answer of collectAnswers(root)) {
      latest = await jsonRequest(`/api/mcp/planning/weekly/${session._id}/answer`, {
        method: 'POST',
        body: JSON.stringify(answer)
      });
      applyMcpMeta(latest);
    }

    if (latest) {
      state.session = latest.session || state.session;
      state.questions = latest.questions || latest.next_questions || state.questions;
    }
    render(root);
    return latest;
  }

  async function buildPlan(root) {
    await saveAnswers(root);
    const session = state.session;
    if (!session || !session._id) return;

    const payload = await jsonRequest(`/api/mcp/planning/weekly/${session._id}/plan`, {
      method: 'POST',
      body: '{}'
    });
    applyMcpMeta(payload);
    state.session = payload.session || state.session;
    state.plan = payload.plan || null;
    state.questions = payload.questions || payload.next_questions || state.questions;
    render(root);
  }

  function bind(root) {
    const start = root.querySelector('[data-weekly-meeting-start]');
    const refresh = root.querySelector('[data-weekly-meeting-refresh]');
    const save = root.querySelector('[data-weekly-meeting-save]');
    const plan = root.querySelector('[data-weekly-meeting-plan]');

    if (start) {
      start.addEventListener('click', async () => {
        try {
          setBusy(root, true);
          await ensureSession(root);
        } catch (error) {
          setStatus(root, 'Error', error.message);
        } finally {
          setBusy(root, false);
        }
      });
    }

    if (refresh) {
      refresh.addEventListener('click', async () => {
        try {
          setBusy(root, true);
          await load(root);
        } catch (error) {
          setStatus(root, 'Error', error.message);
        } finally {
          setBusy(root, false);
        }
      });
    }

    if (save) {
      save.addEventListener('click', async () => {
        try {
          setBusy(root, true);
          await saveAnswers(root);
        } catch (error) {
          setStatus(root, 'Error', error.message);
        } finally {
          setBusy(root, false);
        }
      });
    }

    if (plan) {
      plan.addEventListener('click', async () => {
        try {
          setBusy(root, true);
          await buildPlan(root);
        } catch (error) {
          setStatus(root, 'Plan incompleto', error.message);
        } finally {
          setBusy(root, false);
        }
      });
    }
  }

  async function init() {
    const root = document.querySelector('[data-weekly-meeting]');
    if (!root) return;
    bind(root);
    try {
      setBusy(root, true);
      await load(root);
    } catch (error) {
      setStatus(root, 'No disponible', error.message);
    } finally {
      setBusy(root, false);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.WeeklyMeeting = {
    reload: init
  };
})();
