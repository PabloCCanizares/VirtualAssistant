/**
 * GoalMind AI Chat - Funcionalidad basica
 */

(function() {
  'use strict';

  let aiBtn = null;
  let chatOverlay = null;
  let closeBtn = null;
  let messagesEl = null;
  let inputEl = null;
  let sendBtn = null;
  let modelSelect = null;
  let welcomeEl = null;
  let welcomePromptButtons = [];
  let isSending = false;
  let hasAvailableModel = true;
  let selectedModelId = null;
  const history = [];
  const maxHistory = 8;
  const modelStorageKey = 'ai-chat-model-id';
  let modelWarningShown = false;

  function init() {
    aiBtn = document.getElementById('sidebar-ai-btn');
    chatOverlay = document.getElementById('ai-chat-overlay');
    closeBtn = document.getElementById('ai-chat-close');
    messagesEl = document.getElementById('ai-chat-messages');
    inputEl = document.getElementById('ai-chat-input');
    sendBtn = document.getElementById('ai-chat-send');
    modelSelect = document.getElementById('ai-chat-model');
    welcomeEl = messagesEl ? messagesEl.querySelector('.ai-chat-welcome') : null;
    welcomePromptButtons = welcomeEl ? Array.from(welcomeEl.querySelectorAll('.ai-chat-welcome-btn')) : [];

    if (!aiBtn || !chatOverlay) {
      console.warn('AI Chat: Elementos no encontrados');
      return;
    }

    aiBtn.addEventListener('click', openAIChat);

    if (closeBtn) {
      closeBtn.addEventListener('click', closeAIChat);
    }

    if (sendBtn) {
      sendBtn.addEventListener('click', handleSend);
    }

    if (modelSelect) {
      modelSelect.addEventListener('change', handleModelChange);
    }

    welcomePromptButtons.forEach(function(btn) {
      btn.addEventListener('click', function() {
        const prompt = (btn.dataset.prompt || '').trim();
        if (!prompt) {
          return;
        }
        if (inputEl) {
          inputEl.value = prompt;
          autoResize();
        }
        handleSend();
      });
    });

    if (inputEl) {
      inputEl.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          handleSend();
        }
      });

      inputEl.addEventListener('input', autoResize);
    }

    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && chatOverlay.classList.contains('active')) {
        closeAIChat();
      }
    });

    chatOverlay.addEventListener('click', function(e) {
      if (e.target === chatOverlay) {
        closeAIChat();
      }
    });

    syncInputState();
    loadModelCatalog();
  }

  function openAIChat() {
    chatOverlay.classList.add('active');
    if (inputEl) {
      inputEl.focus();
    }
  }

  function closeAIChat() {
    chatOverlay.classList.remove('active');
  }

  function autoResize() {
    if (!inputEl) {
      return;
    }
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
  }

  function appendMessage(role, text) {
    if (!messagesEl) {
      return null;
    }
    if (welcomeEl) {
      welcomeEl.remove();
      welcomeEl = null;
    }
    const wrapper = document.createElement('div');
    wrapper.className = 'ai-chat-message ' + role;
    const bubble = document.createElement('div');
    bubble.className = 'ai-chat-bubble';
    bubble.textContent = text;
    wrapper.appendChild(bubble);
    messagesEl.appendChild(wrapper);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return wrapper;
  }

  function appendThinkingMessage() {
    const wrapper = appendMessage('assistant', 'Pensando...');
    if (wrapper) {
      wrapper.classList.add('thinking');
    }
    return wrapper;
  }

  function updateAssistantMessage(wrapper, text) {
    if (!wrapper) {
      appendMessage('assistant', text);
      return;
    }
    const bubble = wrapper.querySelector('.ai-chat-bubble');
    if (!bubble) {
      appendMessage('assistant', text);
      return;
    }
    wrapper.classList.remove('thinking');
    bubble.textContent = text;
    if (messagesEl) {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  }

  function setSending(state) {
    isSending = state;
    syncInputState();
  }

  function syncInputState() {
    const disabled = isSending || !hasAvailableModel;

    if (sendBtn) {
      sendBtn.disabled = disabled;
    }
    if (inputEl) {
      inputEl.disabled = disabled;
    }
    if (modelSelect) {
      modelSelect.disabled = isSending || modelSelect.options.length === 0;
    }
  }

  function getStoredModelId() {
    try {
      return localStorage.getItem(modelStorageKey);
    } catch (err) {
      return null;
    }
  }

  function storeModelId(modelId) {
    try {
      if (!modelId) {
        localStorage.removeItem(modelStorageKey);
        return;
      }
      localStorage.setItem(modelStorageKey, modelId);
    } catch (err) {
      return;
    }
  }

  function handleModelChange() {
    if (!modelSelect) {
      return;
    }
    selectedModelId = modelSelect.value || null;
    storeModelId(selectedModelId);
  }

  function renderModelOptions(models, defaultModelId) {
    if (!modelSelect) {
      return;
    }
    modelSelect.innerHTML = '';

    const availableIds = [];
    models.forEach(function(model) {
      const option = document.createElement('option');
      option.value = model.id;
      option.textContent = model.available ? model.label : model.label + ' (sin API key)';
      option.disabled = !model.available;
      modelSelect.appendChild(option);
      if (model.available) {
        availableIds.push(model.id);
      }
    });

    if (!models.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'Sin modelos configurados';
      modelSelect.appendChild(option);
    }

    hasAvailableModel = availableIds.length > 0;
    if (!hasAvailableModel) {
      selectedModelId = null;
      modelSelect.value = '';
      if (inputEl) {
        inputEl.placeholder = 'Configura una API key en .env para usar el chat...';
      }
      if (!modelWarningShown) {
        appendMessage('assistant', 'No hay modelos de IA disponibles. Revisa las API keys en el archivo .env.');
        modelWarningShown = true;
      }
      syncInputState();
      return;
    }

    const storedModelId = getStoredModelId();
    if (storedModelId && availableIds.indexOf(storedModelId) >= 0) {
      selectedModelId = storedModelId;
    } else if (defaultModelId && availableIds.indexOf(defaultModelId) >= 0) {
      selectedModelId = defaultModelId;
    } else {
      selectedModelId = availableIds[0];
    }

    modelSelect.value = selectedModelId;
    if (inputEl) {
      inputEl.placeholder = 'Escribe tu mensaje...';
    }
    storeModelId(selectedModelId);
    syncInputState();
  }

  async function loadModelCatalog() {
    if (!modelSelect) {
      return;
    }

    try {
      const res = await fetch('/api/ai/models', {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'No se pudo cargar el catalogo de modelos');
      }

      const models = Array.isArray(data.models) ? data.models : [];
      renderModelOptions(models, data.default_model_id || null);
    } catch (err) {
      hasAvailableModel = false;
      selectedModelId = null;
      modelSelect.innerHTML = '';
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'Error cargando modelos';
      modelSelect.appendChild(option);
      if (inputEl) {
        inputEl.placeholder = 'No se pudieron cargar los modelos de IA...';
      }
      if (!modelWarningShown) {
        appendMessage('assistant', 'No se pudo cargar el catalogo de modelos. Revisa la configuracion del backend.');
        modelWarningShown = true;
      }
      syncInputState();
    }
  }

  function handleSend() {
    if (isSending || !inputEl || !hasAvailableModel) {
      return;
    }
    const message = inputEl.value.trim();
    if (!message) {
      return;
    }
    appendMessage('user', message);
    history.push({ role: 'user', content: message });
    while (history.length > maxHistory) {
      history.shift();
    }
    inputEl.value = '';
    autoResize();
    sendMessage(message);
  }

  async function sendMessage(message) {
    setSending(true);
    const thinkingMessage = appendThinkingMessage();
    try {
      const res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: message,
          history: history,
          model_id: selectedModelId
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Error al enviar mensaje');
      }
      const reply = (data.reply || '').trim();
      const safeReply = reply || 'No se recibio respuesta.';
      updateAssistantMessage(thinkingMessage, safeReply);
      history.push({ role: 'assistant', content: safeReply });
      while (history.length > maxHistory) {
        history.shift();
      }
    } catch (err) {
      const errorText = (err && err.message) ? err.message : 'Error inesperado';
      updateAssistantMessage(thinkingMessage, 'Error: ' + errorText);
    } finally {
      setSending(false);
      if (inputEl) {
        inputEl.focus();
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
