// static/js/app.js
document.addEventListener('DOMContentLoaded', function () {
  // ===== DASHBOARD STATS CELLS =====
  const cells = document.querySelectorAll('.dashboard-stats-cell[data-stat]');

  // Mapea cell -> endpoint (puedes ajustar nombres)
  cells.forEach(cell => {
    const stat = cell.getAttribute('data-stat');
    if (!stat) return;
    const endpoint = `/stats/${stat}`;

    // Fetch el HTML del endpoint y lo inyecta en la celda
    fetch(endpoint, { credentials: 'same-origin' })
      .then(resp => {
        if (!resp.ok) throw new Error('No se pudo cargar ' + endpoint);
        return resp.text();
      })
      .then(html => {
        // insertar HTML (las plantillas devuelven un <div class="panel ..."> completo)
        cell.innerHTML = html;
        // Chart.js debe estar disponible (chart.umd.js cargado en base.html)
        // Si las plantillas contienen scripts inline para inicializar los charts, estos scripts ejecutarán automáticamente (browsers evalúan scripts insertados por innerHTML? No siempre)
        // Para asegurar ejecución de scripts inline, re-ejecutamos cualquier <script> del HTML insertado:
        const temp = document.createElement('div');
        temp.innerHTML = html;
        const scripts = temp.querySelectorAll('script');
        scripts.forEach(s => {
          const newScript = document.createElement('script');
          if (s.src) {
            newScript.src = s.src;
          } else {
            newScript.textContent = s.textContent;
          }
          document.body.appendChild(newScript);
          // opcional: remover el script añadido para no contaminar DOM
          setTimeout(() => newScript.remove(), 2000);
        });
      })
      .catch(err => {
        console.error(err);
        cell.innerHTML = '<div class="panel-error" style="color:#ffb4b4;padding:12px">Error cargando estadística.</div>';
      });
  });

  // ===== DASHBOARD MINI CALENDAR =====
  initDashboardMiniCalendar();
});

/**
 * Inicializa el mini calendario del dashboard con tareas
 */
function initDashboardMiniCalendar() {
  const container = document.querySelector('.dashboard-mini-calendar');
  const grid = document.getElementById('mini-cal-grid');
  const titleEl = document.getElementById('mini-cal-month');
  const prevBtn = document.getElementById('mini-cal-prev');
  const nextBtn = document.getElementById('mini-cal-next');

  if (!grid || !titleEl) return;

  let currentDate = new Date();
  let tasksData = {};
  let activePopup = null;

  const monthNames = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
  ];

  const dayNames = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];

  // Cargar tareas del mes actual
  function loadTasks(year, month) {
    const startDate = new Date(year, month, 1).toISOString().split('T')[0];
    const endDate = new Date(year, month + 1, 0).toISOString().split('T')[0];

    fetch('/tasks/api/by-date-range?start=' + startDate + '&end=' + endDate, {
      credentials: 'same-origin'
    })
      .then(function(resp) {
        if (!resp.ok) return {};
        return resp.json();
      })
      .then(function(data) {
        tasksData = data || {};
        renderCalendar();
      })
      .catch(function() {
        tasksData = {};
        renderCalendar();
      });
  }

  function renderCalendar() {
    // Limpiar grid completamente
    grid.innerHTML = '';

    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();

    // Actualizar titulo
    titleEl.textContent = monthNames[month] + ' ' + year;

    // Agregar headers de dias
    dayNames.forEach(function(name) {
      const header = document.createElement('div');
      header.className = 'dashboard-mini-calendar-day-header';
      header.textContent = name;
      grid.appendChild(header);
    });

    // Primer dia del mes y ultimo dia
    const lastDay = new Date(year, month + 1, 0);
    const totalDays = lastDay.getDate();

    // Dia de la semana del primer dia (0=Dom, 1=Lun...)
    let startDay = new Date(year, month, 1).getDay();
    startDay = startDay === 0 ? 6 : startDay - 1; // Convertir a Lun=0

    // Dias del mes anterior para rellenar
    const prevMonthLastDay = new Date(year, month, 0).getDate();

    // Hoy
    const today = new Date();
    const isCurrentMonth = today.getFullYear() === year && today.getMonth() === month;

    // Dias del mes anterior
    for (let i = startDay - 1; i >= 0; i--) {
      const dayNum = prevMonthLastDay - i;
      const dayEl = createDayElement(dayNum, true, null, 0);
      grid.appendChild(dayEl);
    }

    // Dias del mes actual
    for (let d = 1; d <= totalDays; d++) {
      const dateKey = year + '-' + String(month + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
      const dayTasks = tasksData[dateKey] || [];
      const taskCount = Math.min(dayTasks.length, 4);

      const dayEl = createDayElement(d, false, dateKey, taskCount);

      if (isCurrentMonth && d === today.getDate()) {
        dayEl.classList.add('today');
      }

      // Click para mostrar tareas
      if (dayTasks.length > 0) {
        dayEl.addEventListener('click', function(e) {
          e.stopPropagation();
          showTasksPopup(dayEl, dateKey, dayTasks, d, month, year);
        });
      }

      grid.appendChild(dayEl);
    }

    // Dias del mes siguiente para completar 6 filas
    const totalCells = startDay + totalDays;
    const remaining = (Math.ceil(totalCells / 7) * 7) - totalCells;
    for (let i = 1; i <= remaining; i++) {
      const dayEl = createDayElement(i, true, null, 0);
      grid.appendChild(dayEl);
    }
  }

  function createDayElement(day, isOtherMonth, dateKey, taskCount) {
    const el = document.createElement('div');
    el.className = 'dashboard-mini-calendar-day';
    if (isOtherMonth) {
      el.classList.add('other-month');
    }

    // Numero del dia
    const numEl = document.createElement('span');
    numEl.className = 'day-number';
    numEl.textContent = day;
    el.appendChild(numEl);

    // Puntos de tareas (max 4)
    if (taskCount > 0 && !isOtherMonth) {
      const dotsContainer = document.createElement('div');
      dotsContainer.className = 'day-task-dots';
      for (let i = 0; i < taskCount; i++) {
        const dot = document.createElement('span');
        dot.className = 'day-task-dot';
        dotsContainer.appendChild(dot);
      }
      el.appendChild(dotsContainer);
      el.classList.add('has-tasks');
    }

    return el;
  }

  function showTasksPopup(dayEl, dateKey, tasks, day, month, year) {
    // Cerrar popup anterior
    closePopup();

    const popup = document.createElement('div');
    popup.className = 'mini-calendar-popup';

    // Header del popup
    const header = document.createElement('div');
    header.className = 'mini-calendar-popup-header';
    header.textContent = day + ' de ' + monthNames[month] + ', ' + year;
    popup.appendChild(header);

    // Lista de tareas
    const list = document.createElement('ul');
    list.className = 'mini-calendar-popup-list';
    tasks.forEach(function(task) {
      const item = document.createElement('li');
      item.className = 'mini-calendar-popup-item';
      item.textContent = task.titulo || task.title || '(Sin titulo)';
      list.appendChild(item);
    });
    popup.appendChild(list);

    // Añadir popup al body para posicionamiento absoluto en viewport
    document.body.appendChild(popup);
    activePopup = popup;

    // Obtener dimensiones
    const dayRect = dayEl.getBoundingClientRect();
    const popupWidth = 220;
    const popupHeight = popup.offsetHeight || 150;
    const gap = 8;

    let left, top;

    // Calcular posicion vertical: centrado con el dia
    top = dayRect.top + (dayRect.height / 2) - (popupHeight / 2);

    // Ajustar si se sale por arriba
    if (top < 10) {
      top = 10;
    }
    // Ajustar si se sale por abajo
    if (top + popupHeight > window.innerHeight - 10) {
      top = window.innerHeight - popupHeight - 10;
    }

    // Calcular posicion horizontal: preferir derecha, sino izquierda
    if (dayRect.right + gap + popupWidth < window.innerWidth - 10) {
      // Hay espacio a la derecha
      left = dayRect.right + gap;
      popup.classList.remove('popup-left');
      popup.classList.add('popup-right');
    } else {
      // Posicionar a la izquierda
      left = dayRect.left - popupWidth - gap;
      popup.classList.remove('popup-right');
      popup.classList.add('popup-left');
    }

    // Ajustar si se sale por la izquierda
    if (left < 10) {
      left = 10;
    }

    popup.style.left = left + 'px';
    popup.style.top = top + 'px';

    // Marcar dia como activo
    dayEl.classList.add('active');
  }

  function closePopup() {
    if (activePopup) {
      activePopup.remove();
      activePopup = null;
    }
    const activeDay = grid.querySelector('.dashboard-mini-calendar-day.active');
    if (activeDay) {
      activeDay.classList.remove('active');
    }
  }

  // Cerrar popup al hacer click fuera
  document.addEventListener('click', function(e) {
    if (activePopup && !activePopup.contains(e.target) && !e.target.closest('.dashboard-mini-calendar-day')) {
      closePopup();
    }
  });

  // Navegacion
  if (prevBtn) {
    prevBtn.addEventListener('click', function() {
      closePopup();
      currentDate.setMonth(currentDate.getMonth() - 1);
      loadTasks(currentDate.getFullYear(), currentDate.getMonth());
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener('click', function() {
      closePopup();
      currentDate.setMonth(currentDate.getMonth() + 1);
      loadTasks(currentDate.getFullYear(), currentDate.getMonth());
    });
  }

  // Cargar tareas iniciales
  loadTasks(currentDate.getFullYear(), currentDate.getMonth());
}
