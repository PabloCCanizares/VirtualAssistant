/**
 * Side Panel Collapsible - Sistema de menus desplegables para paneles laterales
 *
 * Comportamiento:
 * - Por defecto todos los bloques con forms estan colapsados
 * - Al hacer hover, el bloque se expande
 * - Si se hace click en un elemento del contenido, el bloque queda "locked"
 * - El bloque locked permanece expandido hasta que se haga click fuera de el
 * - Solo puede haber un bloque locked a la vez
 * - Los bloques sin forms permanecen siempre visibles (no colapsables)
 */

document.addEventListener('DOMContentLoaded', function() {
  initCollapsiblePanels();
});

function initCollapsiblePanels() {
  const sidePanels = document.querySelectorAll('.side-panel');
  
  sidePanels.forEach(sidePanel => {
    const cards = sidePanel.querySelectorAll('.side-panel-card.collapsible');
    let lockedCard = null;
    let hoverTimeout = null;

    /**
     * Expande una card
     */
    function expandCard(card) {
      card.classList.add('expanded');
    }

    /**
     * Colapsa una card
     */
    function collapseCard(card) {
      if (!card.classList.contains('locked')) {
        card.classList.remove('expanded');
      }
    }

    /**
     * Bloquea una card (la mantiene expandida tras click)
     */
    function lockCard(card) {
      // Si hay otra card bloqueada, desbloquearla primero
      if (lockedCard && lockedCard !== card) {
        unlockCard(lockedCard);
      }

      card.classList.add('locked');
      card.classList.add('expanded');
      lockedCard = card;
    }

    /**
     * Desbloquea una card
     */
    function unlockCard(card) {
      if (!card) return;
      card.classList.remove('locked');
      card.classList.remove('expanded');
      if (lockedCard === card) {
        lockedCard = null;
      }
    }

    /**
     * Desbloquea todas las cards
     */
    function unlockAll() {
      cards.forEach(card => {
        card.classList.remove('locked');
        card.classList.remove('expanded');
      });
      lockedCard = null;
    }

    // Configurar cada card colapsable
    cards.forEach(card => {
      const header = card.querySelector('.side-panel-header');
      const content = card.querySelector('.side-panel-card-content');
      
      if (!header || !content) return;

      // Hover en la card -> expandir
      card.addEventListener('mouseenter', function() {
        clearTimeout(hoverTimeout);
        if (!card.classList.contains('locked')) {
          expandCard(card);
        }
      });

      // Mouse leave -> colapsar (si no esta locked)
      card.addEventListener('mouseleave', function() {
        hoverTimeout = setTimeout(() => {
          if (!card.classList.contains('locked')) {
            collapseCard(card);
          }
        }, 150); // Pequeno delay para evitar colapsos accidentales
      });

      // Click en el header -> toggle lock
      header.addEventListener('click', function(e) {
        e.stopPropagation();
        
        if (card.classList.contains('locked')) {
          unlockCard(card);
        } else {
          lockCard(card);
        }
      });

      // Click en el contenido -> bloquear
      content.addEventListener('click', function(e) {
        e.stopPropagation();
        lockCard(card);
      });

      // Click en inputs, selects, textareas, buttons -> bloquear
      const interactiveElements = content.querySelectorAll('input, select, textarea, button, .dropzone');
      interactiveElements.forEach(el => {
        el.addEventListener('focus', function() {
          lockCard(card);
        });

        el.addEventListener('click', function(e) {
          e.stopPropagation();
          lockCard(card);
        });
      });
    });

    // Click fuera del panel -> desbloquear todo
    document.addEventListener('click', function(e) {
      if (!sidePanel.contains(e.target)) {
        // Verificar que no se haya hecho click en un modal
        const modal = document.querySelector('.upload-modal-overlay.active');
        if (modal && modal.contains(e.target)) return;
        
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
    const forms = sidePanel.querySelectorAll('form');
    forms.forEach(form => {
      form.addEventListener('submit', function(e) {
        const card = form.closest('.side-panel-card.collapsible');
        if (card) {
          setTimeout(() => lockCard(card), 100);
        }
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
    if (iconEl) iconEl.textContent = getFileIcon(file.type);
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

function getFileIcon(mimeType) {
  if (!mimeType) return '📄';
  
  if (mimeType.startsWith('image/')) return '🖼️';
  if (mimeType.startsWith('video/')) return '🎬';
  if (mimeType.startsWith('audio/')) return '🎵';
  if (mimeType.includes('pdf')) return '📕';
  if (mimeType.includes('word') || mimeType.includes('document')) return '📘';
  if (mimeType.includes('excel') || mimeType.includes('spreadsheet')) return '📗';
  if (mimeType.includes('powerpoint') || mimeType.includes('presentation')) return '📙';
  if (mimeType.includes('zip') || mimeType.includes('compressed')) return '🗜️';
  if (mimeType.includes('text')) return '📝';
  
  return '📄';
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
window.getFileIcon = getFileIcon;
window.showSnackbar = showSnackbar;
