// confirm_modal.js - Modal de confirmación personalizado para eliminaciones

class ConfirmModal {
  constructor() {
    this.modal = null;
    this.overlay = null;
    this.title = null;
    this.body = null;
    this.confirmBtn = null;
    this.cancelBtn = null;
    this.closeBtn = null;
    this.pendingForm = null;
    this.pendingCallback = null;
    this.init();
  }

  init() {
    // Obtener referencias a los elementos
    this.modal = document.getElementById('confirmModal');
    if (!this.modal) {
      return;
    }
    this.overlay = this.modal.querySelector('.confirm-modal-overlay');
    this.title = this.modal.querySelector('#confirmModalTitle');
    this.body = this.modal.querySelector('#confirmModalBody');
    this.closeBtn = this.modal.querySelector('[data-action="close"]');

    // Botones de acción
    const actionBtns = this.modal.querySelectorAll('[data-action]');
    actionBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const action = btn.dataset.action;
        if (action === 'confirm') {
          this.confirm();
        } else if (action === 'cancel') {
          this.cancel();
        }
      });
    });

    // Cerrar con Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.modal.classList.contains('active')) {
        this.cancel();
      }
    });
  }

  /**
   * Abre el modal de confirmación
   * @param {Object} options - Opciones para el modal
   * @param {string} options.title - Título del modal
   * @param {string} options.message - Mensaje de confirmación
   * @param {HTMLFormElement} options.form - Formulario a enviar
   * @param {Function} options.callback - Callback a ejecutar al confirmar (alternativa a form)
   */
  show(options = {}) {
    if (!this.modal) {
      return;
    }
    const {
      title = '¿Confirmar acción?',
      message = '¿Estás seguro de que deseas continuar?',
      form = null,
      callback = null
    } = options;

    this.title.textContent = title;
    this.body.textContent = message;
    this.pendingForm = form;
    this.pendingCallback = callback;

    this.modal.classList.add('active');
    this.modal.setAttribute('aria-hidden', 'false');
  }

  confirm() {
    if (this.pendingForm) {
      this.pendingForm.submit();
    } else if (this.pendingCallback) {
      this.pendingCallback();
    }
    this.close();
  }

  cancel() {
    this.close();
    this.pendingForm = null;
    this.pendingCallback = null;
  }

  close() {
    if (!this.modal) {
      return;
    }
    this.modal.classList.remove('active');
    this.modal.setAttribute('aria-hidden', 'true');
  }
}

// Instancia global del modal
let confirmModal = null;

document.addEventListener('DOMContentLoaded', () => {
  // Inicializar el modal
  confirmModal = new ConfirmModal();

  // Interceptar todos los formularios con data-confirm-message
  document.addEventListener('submit', (e) => {
    const form = e.target;
    const confirmMessage = form.getAttribute('data-confirm-message');

    // Si tiene un data-confirm-message, prevenir envío y mostrar modal
    if (confirmMessage) {
      e.preventDefault();

      // Mostrar el modal
      confirmModal.show({
        title: '¿Confirmar?',
        message: confirmMessage,
        form: form
      });
    }
  }, true); // Usar captura para interceptar antes que otros handlers
});
