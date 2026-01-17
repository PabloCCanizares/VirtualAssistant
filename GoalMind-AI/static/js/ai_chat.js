/**
 * GoalMind AI Chat - Funcionalidad basica
 */

(function() {
  'use strict';

  let aiBtn = null;
  let chatOverlay = null;
  let closeBtn = null;

  function init() {
    aiBtn = document.getElementById('sidebar-ai-btn');
    chatOverlay = document.getElementById('ai-chat-overlay');
    closeBtn = document.getElementById('ai-chat-close');

    if (!aiBtn || !chatOverlay) {
      console.warn('AI Chat: Elementos no encontrados');
      return;
    }

    aiBtn.addEventListener('click', openAIChat);

    if (closeBtn) {
      closeBtn.addEventListener('click', closeAIChat);
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
  }

  function closeAIChat() {
    chatOverlay.classList.remove('active');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
