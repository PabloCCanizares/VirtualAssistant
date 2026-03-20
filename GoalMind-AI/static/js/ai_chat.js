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
  let deepSearchModeSelect = null;
  let welcomeEl = null;
  let welcomePromptButtons = [];
  let isSending = false;
  const history = [];
  const maxHistory = 8;
  const DEEP_SEARCH_MODE_STORAGE_KEY = 'ai_chat_deep_search_mode';
  const ALLOWED_DEEP_SEARCH_MODES = ['auto', 'on', 'off'];

  function init() {
    aiBtn = document.getElementById('sidebar-ai-btn');
    chatOverlay = document.getElementById('ai-chat-overlay');
    closeBtn = document.getElementById('ai-chat-close');
    messagesEl = document.getElementById('ai-chat-messages');
    inputEl = document.getElementById('ai-chat-input');
    sendBtn = document.getElementById('ai-chat-send');
    deepSearchModeSelect = document.getElementById('ai-chat-deep-search-mode');
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

    if (deepSearchModeSelect) {
      deepSearchModeSelect.value = loadDeepSearchModePreference();
      deepSearchModeSelect.addEventListener('change', function() {
        var mode = normalizeDeepSearchMode(deepSearchModeSelect.value);
        deepSearchModeSelect.value = mode;
        saveDeepSearchModePreference(mode);
      });
    }

    welcomePromptButtons.forEach(function(btn) {
      btn.addEventListener('click', function() {
        var prompt = (btn.dataset.prompt || '').trim();
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

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
  }

  function appendMessage(role, text) {
    if (!messagesEl) {
      return null;
    }
    if (welcomeEl) {
      welcomeEl.remove();
      welcomeEl = null;
    }
    var wrapper = document.createElement('div');
    wrapper.className = 'ai-chat-message ' + role;
    var bubble = document.createElement('div');
    bubble.className = 'ai-chat-bubble';
    bubble.textContent = text;
    wrapper.appendChild(bubble);
    messagesEl.appendChild(wrapper);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return wrapper;
  }

  function appendThinkingMessage() {
    var wrapper = appendMessage('assistant', 'Pensando...');
    if (wrapper) {
      wrapper.classList.add('thinking');
    }
    return wrapper;
  }

  function updateThinkingStatus(wrapper, name, action) {
    if (!wrapper) return;
    var bubble = wrapper.querySelector('.ai-chat-bubble');
    if (!bubble) return;
    bubble.innerHTML = '<strong>' + escapeHtml(name) + '</strong> · ' + escapeHtml(action);
    if (messagesEl) {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  }

  function updateAssistantMessage(wrapper, text) {
    if (!wrapper) {
      appendMessage('assistant', text);
      return;
    }
    var bubble = wrapper.querySelector('.ai-chat-bubble');
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
    if (sendBtn) {
      sendBtn.disabled = state;
    }
    if (inputEl) {
      inputEl.disabled = state;
    }
    if (deepSearchModeSelect) {
      deepSearchModeSelect.disabled = state;
    }
  }

  function normalizeDeepSearchMode(mode) {
    var normalized = String(mode || '').trim().toLowerCase();
    if (ALLOWED_DEEP_SEARCH_MODES.indexOf(normalized) >= 0) {
      return normalized;
    }
    return 'auto';
  }

  function loadDeepSearchModePreference() {
    try {
      return normalizeDeepSearchMode(window.localStorage.getItem(DEEP_SEARCH_MODE_STORAGE_KEY));
    } catch (_err) {
      return 'auto';
    }
  }

  function saveDeepSearchModePreference(mode) {
    try {
      window.localStorage.setItem(DEEP_SEARCH_MODE_STORAGE_KEY, normalizeDeepSearchMode(mode));
    } catch (_err) {
      // Ignorar: algunos navegadores pueden bloquear storage.
    }
  }

  function getSelectedDeepSearchMode() {
    if (!deepSearchModeSelect) {
      return 'auto';
    }
    return normalizeDeepSearchMode(deepSearchModeSelect.value);
  }

  function handleSend() {
    if (isSending || !inputEl) {
      return;
    }
    var message = inputEl.value.trim();
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
    var thinkingWrapper = appendThinkingMessage();
    try {
      var res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message,
          history: history,
          deep_search_mode: getSelectedDeepSearchMode()
        })
      });

      if (!res.ok) {
        throw new Error('Error al enviar mensaje');
      }

      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';
      var finalReply = '';

      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;

        buffer += decoder.decode(chunk.value, { stream: true });
        var lines = buffer.split('\n');
        buffer = lines.pop();

        for (var i = 0; i < lines.length; i++) {
          var line = lines[i];
          if (line.indexOf('data: ') !== 0) continue;
          try {
            var data = JSON.parse(line.slice(6));
            if (data.type === 'status') {
              updateThinkingStatus(thinkingWrapper, data.name, data.action);
            } else if (data.type === 'done') {
              finalReply = (data.reply || '').trim() || 'No se recibió respuesta.';
            } else if (data.type === 'error') {
              finalReply = 'Error: ' + (data.message || 'Error inesperado');
            }
          } catch (_parseErr) {
            // Ignorar lineas mal formadas
          }
        }
      }

      var safeReply = finalReply || 'No se recibió respuesta.';
      updateAssistantMessage(thinkingWrapper, safeReply);
      history.push({ role: 'assistant', content: safeReply });
      while (history.length > maxHistory) {
        history.shift();
      }
    } catch (err) {
      var errorText = (err && err.message) ? err.message : 'Error inesperado';
      updateAssistantMessage(thinkingWrapper, 'Error: ' + errorText);
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
