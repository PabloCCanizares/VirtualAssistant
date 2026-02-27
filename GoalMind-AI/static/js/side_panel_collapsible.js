/*
 * Side Panel Collapsible - Sistema de menus desplegables para paneles laterales
 */

document.addEventListener('DOMContentLoaded', function() {
  initCollapsiblePanels();
});

function initCollapsiblePanels() {
  const sidePanels = document.querySelectorAll('.side-panel');
  
 sidePanels.forEach(sidePanel => {
    const cards = sidePanel.querySelectorAll('.side-panel-card.collapsible');

    function toggleCard(card) {
      card.classList.toggle('expanded');
    }

    // Configurar cada card colapsable
    cards.forEach(card => {
      const header = card.querySelector('.side-panel-header');
      const content = card.querySelector('.side-panel-card-content');
      
      if (!header || !content) return;

      // Click en el header -> toggle expand/collapse
      header.addEventListener('click', function(e) {
        e.stopPropagation();
        toggleCard(card);
      });
    });
  });
}

/**
 * Drag & Drop para subida de documentos
 */
function initDropzone(dropzoneElement, options = {}) {
  if (!dropzoneElement) return;

  const {
    onDrop = () => {},
    onDragOver = () => {},
    onDragLeave = () => {},
    acceptedTypes = null // null = acepta todo, o array de tipos MIME
  } = options;

  // Prevenir comportamiento por defecto del navegador
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropzoneElement.addEventListener(eventName, preventDefaults, false);
    document.body.addEventListener(eventName, preventDefaults, false);
  });

  function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }

  // Highlight al arrastrar
  ['dragenter', 'dragover'].forEach(eventName => {
    dropzoneElement.addEventListener(eventName, () => {
      dropzoneElement.classList.add('dragover');
      onDragOver();
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzoneElement.addEventListener(eventName, () => {
      dropzoneElement.classList.remove('dragover');
      onDragLeave();
    }, false);
  });

  // Handle drop
  dropzoneElement.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0]; // Solo aceptamos un archivo
      
      // Verificar tipo si hay restricciones
      if (acceptedTypes && !acceptedTypes.includes(file.type)) {
        showSnackbar('Tipo de archivo no permitido', 'error');
        return;
      }
      
      onDrop(file);
    }
  }, false);

  // Handle click en input file (si existe)
  const fileInput = dropzoneElement.querySelector('input[type="file"]');
  if (fileInput) {
    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        onDrop(e.target.files[0]);
      }
    });
  }
}

/**
 * Modal de subida de documentos
 */
class UploadModal {
  constructor(modalElement, options = {}) {
    this.modal = modalElement;
    this.overlay = modalElement.closest('.upload-modal-overlay') || modalElement;
    this.options = {
      onSubmit: options.onSubmit || (() => {}),
      onCancel: options.onCancel || (() => {})
    };
    
    this.file = null;
    this.init();
  }

  init() {
    // Cerrar con boton X
    const closeBtn = this.modal.querySelector('.upload-modal-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => this.close());
    }

    // Cerrar con click en overlay
    this.overlay.addEventListener('click', (e) => {
      if (e.target === this.overlay) {
        this.close();
      }
    });

    // Cerrar con Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.isOpen()) {
        this.close();
      }
    });

    // Boton cancelar
    const cancelBtn = this.modal.querySelector('[data-action="cancel"]');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => this.close());
    }

    // Form submit
    const form = this.modal.querySelector('form');
    if (form) {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        this.submit();
      });
    }
  }

  open(file) {
    this.file = file;
    this.updateFilePreview(file);
    this.overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
    
    // Focus en el primer input
    setTimeout(() => {
      const firstInput = this.modal.querySelector('input[type="text"]');
      if (firstInput) firstInput.focus();
    }, 100);
  }

  close() {
    this.overlay.classList.remove('active');
    document.body.style.overflow = '';
    this.file = null;
    this.options.onCancel();
    
    // Reset form
    const form = this.modal.querySelector('form');
    if (form) form.reset();
  }

  isOpen() {
    return this.overlay.classList.contains('active');
  }

  updateFilePreview(file) {
    const nameEl = this.modal.querySelector('.upload-modal-file-name');
    const sizeEl = this.modal.querySelector('.upload-modal-file-size');
    const iconEl = this.modal.querySelector('.upload-modal-file-icon');

    if (nameEl) nameEl.textContent = file.name;
    if (sizeEl) sizeEl.textContent = formatFileSize(file.size);
  }

  submit() {
    const form = this.modal.querySelector('form');
    const formData = new FormData(form);
    
    // Agregar el archivo al FormData
    if (this.file) {
      formData.set('document', this.file);
    }

    this.options.onSubmit(formData, this.file);
  }

  getFormData() {
    const form = this.modal.querySelector('form');
    return new FormData(form);
  }
}

/**
 * Utilidades
 */
function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function showSnackbar(message, type = 'success') {
  // Buscar snackbar existente o crear uno
  let snackbar = document.querySelector('.snackbar');
  if (!snackbar) {
    snackbar = document.createElement('div');
    snackbar.className = 'snackbar';
    document.body.appendChild(snackbar);
  }

  snackbar.textContent = message;
  snackbar.className = `snackbar snackbar-${type} snackbar-show`;

  setTimeout(() => {
    snackbar.classList.remove('snackbar-show');
  }, 3000);
}

// Exportar para uso global
window.initCollapsiblePanels = initCollapsiblePanels;
window.initDropzone = initDropzone;
window.UploadModal = UploadModal;
window.formatFileSize = formatFileSize;
window.showSnackbar = showSnackbar;
