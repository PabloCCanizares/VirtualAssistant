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
  let voiceBtn = null;
  let modelSelect = null;
  let welcomeEl = null;
  let welcomePromptButtons = [];
  let isSending = false;
  let isListening = false;
  let supportsVoiceInput = false;
  let recognition = null;
  let voiceStartText = '';
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
    voiceBtn = document.getElementById('ai-chat-voice');
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

    setupVoiceInput();

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
    if (state && isListening) {
      stopVoiceInput();
    }
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
    if (voiceBtn) {
      voiceBtn.disabled = disabled || !supportsVoiceInput;
    }
  }

  function trimHistory() {
    while (history.length > maxHistory) {
      history.shift();
    }
  }

  function getSpeechRecognition() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function setupVoiceInput() {
    if (!voiceBtn) {
      return;
    }

    const SpeechRecognition = getSpeechRecognition();
    supportsVoiceInput = Boolean(SpeechRecognition);
    voiceBtn.setAttribute('aria-pressed', 'false');

    if (!supportsVoiceInput) {
      voiceBtn.title = 'Entrada de voz no disponible';
      voiceBtn.setAttribute('aria-label', 'Entrada de voz no disponible');
      syncInputState();
      return;
    }

    recognition = new SpeechRecognition();
    recognition.lang = document.documentElement.lang || 'es-ES';
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = function() {
      voiceStartText = inputEl ? inputEl.value.trim() : '';
      setVoiceListening(true);
      if (inputEl) {
        inputEl.placeholder = 'Escuchando...';
      }
    };

    recognition.onresult = function(event) {
      if (!inputEl) {
        return;
      }

      let transcript = '';
      for (let i = 0; i < event.results.length; i += 1) {
        transcript += event.results[i][0].transcript;
      }

      transcript = transcript.trim();
      if (!transcript) {
        return;
      }

      inputEl.value = voiceStartText ? voiceStartText + ' ' + transcript : transcript;
      autoResize();
    };

    recognition.onerror = function(event) {
      const error = event && event.error ? event.error : '';
      if (inputEl && error && error !== 'aborted' && error !== 'no-speech') {
        inputEl.placeholder = 'No se pudo activar el microfono...';
      }
    };

    recognition.onend = function() {
      setVoiceListening(false);
      if (inputEl && hasAvailableModel) {
        inputEl.placeholder = 'Escribe tu mensaje...';
        inputEl.focus();
      }
    };

    voiceBtn.addEventListener('click', toggleVoiceInput);
    syncInputState();
  }

  function setVoiceListening(state) {
    isListening = state;
    if (voiceBtn) {
      voiceBtn.classList.toggle('listening', state);
      voiceBtn.setAttribute('aria-pressed', state ? 'true' : 'false');
    }
    syncInputState();
  }

  function toggleVoiceInput() {
    if (!recognition || isSending || !hasAvailableModel) {
      return;
    }

    if (isListening) {
      stopVoiceInput();
      return;
    }

    try {
      recognition.start();
    } catch (err) {
      setVoiceListening(false);
    }
  }

  function stopVoiceInput() {
    if (!recognition || !isListening) {
      return;
    }

    try {
      recognition.stop();
    } catch (err) {
      setVoiceListening(false);
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
    const requestHistory = history.slice();
    appendMessage('user', message);
    history.push({ role: 'user', content: message });
    trimHistory();
    inputEl.value = '';
    autoResize();
    sendMessage(message, requestHistory);
  }

  function parseSseEvent(rawEvent) {
    const dataLines = rawEvent
      .split(/\r?\n/)
      .filter(function(line) {
        return line.indexOf('data:') === 0;
      })
      .map(function(line) {
        return line.slice(5).trimStart();
      });

    if (!dataLines.length) {
      return null;
    }

    try {
      return JSON.parse(dataLines.join('\n'));
    } catch (err) {
      throw new Error('Respuesta del asistente no valida');
    }
  }

  function parseSseText(text, onEvent) {
    text.split(/\r?\n\r?\n/).forEach(function(rawEvent) {
      if (!rawEvent.trim()) {
        return;
      }
      const event = parseSseEvent(rawEvent);
      if (event) {
        onEvent(event);
      }
    });
  }

  async function readSseStream(res, onEvent) {
    if (!res.body || !res.body.getReader || typeof TextDecoder === 'undefined') {
      parseSseText(await res.text(), onEvent);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const result = await reader.read();
      if (result.done) {
        break;
      }

      buffer += decoder.decode(result.value, { stream: true });
      const events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop() || '';
      events.forEach(function(rawEvent) {
        const event = parseSseEvent(rawEvent);
        if (event) {
          onEvent(event);
        }
      });
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      parseSseText(buffer, onEvent);
    }
  }

  async function readErrorMessage(res, contentType) {
    const fallback = 'Error al enviar mensaje';

    try {
      if (contentType.indexOf('application/json') >= 0) {
        const data = await res.json();
        return data.error || data.message || fallback;
      }

      if (contentType.indexOf('text/event-stream') >= 0) {
        let streamError = '';
        await readSseStream(res, function(event) {
          if (event.type === 'error') {
            streamError = event.message || event.error || fallback;
          }
        });
        return streamError || fallback;
      }

      const text = (await res.text()).trim();
      return text || fallback;
    } catch (err) {
      return fallback;
    }
  }

  async function consumeChatResponse(res, onEvent) {
    const contentType = (res.headers.get('content-type') || '').toLowerCase();

    if (!res.ok) {
      throw new Error(await readErrorMessage(res, contentType));
    }

    if (contentType.indexOf('text/event-stream') >= 0) {
      await readSseStream(res, onEvent);
      return;
    }

    const data = await res.json();
    onEvent({
      type: 'done',
      reply: data.reply || data.message || ''
    });
  }

  async function sendMessage(message, requestHistory) {
    setSending(true);
    const thinkingMessage = appendThinkingMessage();
    try {
      const res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: {
          'Accept': 'text/event-stream',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: message,
          history: requestHistory,
          model_id: selectedModelId
        })
      });

      let reply = '';
      let streamError = '';

      await consumeChatResponse(res, function(event) {
        if (!event || !event.type) {
          return;
        }

        if (event.type === 'status') {
          const statusText = event.action || event.name || 'Pensando...';
          updateAssistantMessage(thinkingMessage, statusText);
          if (thinkingMessage) {
            thinkingMessage.classList.add('thinking');
          }
          return;
        }

        if (event.type === 'done') {
          reply = (event.reply || '').trim();
          return;
        }

        if (event.type === 'error') {
          streamError = event.message || event.error || 'Error al generar respuesta';
        }
      });

      if (streamError) {
        throw new Error(streamError);
      }

      const safeReply = reply || 'No se recibio respuesta.';
      updateAssistantMessage(thinkingMessage, safeReply);
      history.push({ role: 'assistant', content: safeReply });
      trimHistory();
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
