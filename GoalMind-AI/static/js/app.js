// static/js/app.js  <-- añade estas funciones al final de tu app.js existente
document.addEventListener('DOMContentLoaded', function () {
  const cells = document.querySelectorAll('.stats-cell[data-stat]');
  if (!cells || cells.length === 0) return;

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
});
