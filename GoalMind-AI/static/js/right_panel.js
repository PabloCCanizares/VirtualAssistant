/**
 * Right Panel - Sistema de bloques colapsables
 *
 * Comportamiento:
 * - Por defecto todos los bloques estan colapsados (solo muestran titulo)
 * - Al hacer hover, el bloque se expande
 * - Si se hace click en un elemento del contenido (form, input, etc), el bloque queda "locked"
 * - El bloque locked permanece expandido hasta que se haga click fuera de el
 * - Solo puede haber un bloque locked a la vez
 */

document.addEventListener('DOMContentLoaded', function() {
  const dashboardSide = document.getElementById('dashboardSide');
  if (!dashboardSide) return;

  const cards = dashboardSide.querySelectorAll('.dashboard-card');
  let lockedCard = null;

  /**
   * Bloquea una card (la mantiene expandida)
   */
  function lockCard(card) {
    // Si hay otra card bloqueada, desbloquearla primero
    if (lockedCard && lockedCard !== card) {
      unlockCard(lockedCard);
    }

    card.classList.add('locked');
    dashboardSide.classList.add('has-locked');
    lockedCard = card;
  }

  /**
   * Desbloquea una card
   */
  function unlockCard(card) {
    if (!card) return;
    card.classList.remove('locked');
    dashboardSide.classList.remove('has-locked');
    if (lockedCard === card) {
      lockedCard = null;
    }
  }

  /**
   * Desbloquea todas las cards
   */
  function unlockAll() {
    cards.forEach(card => card.classList.remove('locked'));
    dashboardSide.classList.remove('has-locked');
    lockedCard = null;
  }

  // Configurar cada card
  cards.forEach(card => {
    const content = card.querySelector('.dashboard-card-content');
    if (!content) return;

    // Click en el contenido de la card -> bloquear
    content.addEventListener('click', function(e) {
      e.stopPropagation();
      lockCard(card);
    });

    // Click en inputs, selects, textareas, buttons dentro del contenido -> bloquear
    const interactiveElements = content.querySelectorAll('input, select, textarea, button');
    interactiveElements.forEach(el => {
      el.addEventListener('focus', function() {
        lockCard(card);
      });

      el.addEventListener('click', function(e) {
        e.stopPropagation();
        lockCard(card);
      });
    });

    // Click en el header -> toggle manual (opcional: expandir/colapsar)
    const header = card.querySelector('.dashboard-card-header');
    if (header) {
      header.addEventListener('click', function(e) {
        e.stopPropagation();

        // Si esta bloqueada, desbloquear
        if (card.classList.contains('locked')) {
          unlockCard(card);
        } else {
          // Si no esta bloqueada, bloquearla
          lockCard(card);
        }
      });
    }
  });

  // Click fuera de cualquier card -> desbloquear todo
  document.addEventListener('click', function(e) {
    // Verificar si el click fue fuera del panel lateral
    if (!dashboardSide.contains(e.target)) {
      unlockAll();
    }
  });

  // Tecla Escape -> desbloquear todo
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      unlockAll();
    }
  });

  // Prevenir que el submit de forms desbloquee
  const forms = dashboardSide.querySelectorAll('form');
  forms.forEach(form => {
    form.addEventListener('submit', function(e) {
      // Mantener el bloqueo despues del submit (si no hay redirect)
      const card = form.closest('.dashboard-card');
      if (card) {
        setTimeout(() => lockCard(card), 100);
      }
    });
  });
});
