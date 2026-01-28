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
  let welcomeEl = null;
  let isSending = false;
  const history = [];
  const maxHistory = 8;

  function init() {
    aiBtn = document.getElementById('sidebar-ai-btn');
    chatOverlay = document.getElementById('ai-chat-overlay');
    closeBtn = document.getElementById('ai-chat-close');
    messagesEl = document.getElementById('ai-chat-messages');
    inputEl = document.getElementById('ai-chat-input');
    sendBtn = document.getElementById('ai-chat-send');
    welcomeEl = messagesEl ? messagesEl.querySelector('.ai-chat-welcome') : null;

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

  function appendMessage(role, text) {
    if (!messagesEl) {
      return;
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
  }

  function setSending(state) {
    isSending = state;
    if (sendBtn) {
      sendBtn.disabled = state;
    }
    if (inputEl) {
      inputEl.disabled = state;
    }
  }

  function handleSend() {
    if (isSending || !inputEl) {
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
    try {
      const res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: message,
          history: history
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Error al enviar mensaje');
      }
      const reply = (data.reply || '').trim();
      appendMessage('assistant', reply || 'No se recibio respuesta.');
      history.push({ role: 'assistant', content: reply });
      while (history.length > maxHistory) {
        history.shift();
      }
    } catch (err) {
      appendMessage('assistant', 'Error: ' + err.message);
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
