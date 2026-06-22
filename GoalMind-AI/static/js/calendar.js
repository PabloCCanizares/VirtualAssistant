/* ========= CONFIG ========= */
const API = {
  list:   (startISO, endISO) => `/api/events?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`,
  create: () => `/api/events`,
  update: (id) => `/api/events/${id}`,
  remove: (id) => `/api/events/${id}`
};
const DEFAULT_USER = null; // si quieres fijar un id_usuario por defecto (ObjectId string)

/* ========= Utilidades ========= */
const pad = n => String(n).padStart(2,'0');
const toISO = d => new Date(d).toISOString();
const startOfDay = d => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const endOfDay = d => new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate()+n);
const startOfWeek = (d) => { const day = (d.getDay()+6)%7; const s = addDays(startOfDay(d), -day); return s; }; // lunes
const fmtHM = d => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
const stripAccentsLower = s => s ? s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim() : s;

/* ========= Estado ========= */
const state = {
  view: 'week',           // 'week' | 'day'
  anchor: new Date(),     // fecha de referencia (día visible / semana visible)
  events: [],             // eventos cargados de la API (del rango)
};

/* ========= Montaje ========= */
document.addEventListener('DOMContentLoaded', () => {
  // referencias
  const calGrid = document.getElementById('calGrid');
  const rangeTitle = document.getElementById('rangeTitle');
  const viewSel = document.getElementById('viewSel');
  const prevBtn = document.getElementById('prevBtn');
  const nextBtn = document.getElementById('nextBtn');
  const todayBtn = document.getElementById('todayBtn');
  const newBtn = document.getElementById('newBtn');

  // modal refs
  const backdrop = document.getElementById('modalBackdrop');
  const modalTitle = document.getElementById('modalTitle');
  const fTitulo = document.getElementById('fTitulo');
  const fInicio = document.getElementById('fInicio');
  const fFin = document.getElementById('fFin');
  const fDesc = document.getElementById('fDesc');
  const fTipo = document.getElementById('fTipo');
  const fUsuario = document.getElementById('fUsuario');
  const fObjetivo = document.getElementById('fObjetivo');
  const cancelBtn = document.getElementById('cancelBtn');
  const saveBtn = document.getElementById('saveBtn');
  const deleteBtn = document.getElementById('deleteBtn');

  let editingId = null;

  function setView(v){
    state.view = v;
    render();
  }

  function nav(delta){
    state.anchor = (state.view === 'week')
      ? addDays(state.anchor, 7*delta)
      : addDays(state.anchor, 1*delta);
    render();
  }

  todayBtn?.addEventListener('click', ()=>{ state.anchor=new Date(); render(); });
  prevBtn?.addEventListener('click', ()=> nav(-1));
  nextBtn?.addEventListener('click', ()=> nav(1));
  viewSel?.addEventListener('change', e => setView(e.target.value));
  newBtn?.addEventListener('click', ()=> openModalForCreate());

  cancelBtn?.addEventListener('click', closeModal);
  backdrop?.addEventListener('click', (e)=>{ if(e.target===backdrop) closeModal(); });

  saveBtn?.addEventListener('click', async ()=>{
    const body = collectForm();
    if(!body.titulo) return alert('El título es obligatorio');
    if(new Date(body.fecha_fin) < new Date(body.fecha_inicio)) return alert('La fecha fin no puede ser anterior a la de inicio');

    try{
      if(editingId){
        await fetch(API.update(editingId), {
          method:'PUT',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify(body)
        });
      }else{
        await fetch(API.create(), {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify(body)
        });
      }
      closeModal();
      await loadEvents();
      drawEvents();
    }catch(err){
      console.error(err); alert('No se pudo guardar el evento');
    }
  });

  deleteBtn?.addEventListener('click', async ()=>{
    if(!editingId) return;
    if(!confirm('¿Eliminar este evento?')) return;
    try{
      await fetch(API.remove(editingId), { method:'DELETE' });
      closeModal();
      await loadEvents();
      drawEvents();
    }catch(err){
      console.error(err); alert('No se pudo eliminar');
    }
  });

  function openModalForCreate(slotDate){
    editingId = null;
    modalTitle.textContent = 'Nuevo evento';
    deleteBtn.classList.add('hidden');

    const start = slotDate || new Date();
    const end = new Date(start.getTime() + 60*60*1000);

    fTitulo.value = '';
    fInicio.value = toLocalInputValue(start);
    fFin.value = toLocalInputValue(end);
    fDesc.value = '';
    fTipo.value = 'reunion';
    fUsuario.value = DEFAULT_USER || '';
    fObjetivo.value = '';
    backdrop.style.display='flex';
  }

  function openModalForEdit(ev){
    editingId = ev._id;
    modalTitle.textContent = 'Editar evento';
    deleteBtn.classList.remove('hidden');

    fTitulo.value = ev.titulo || '';
    fInicio.value = toLocalInputValue(new Date(ev.fecha_inicio));
    fFin.value = toLocalInputValue(new Date(ev.fecha_fin));
    fDesc.value = ev.descripcion || '';
    fTipo.value = stripAccentsLower(ev.tipo_evento || 'reunion');
    fUsuario.value = ev.id_usuario || '';
    fObjetivo.value = ev.id_objetivo || '';
    backdrop.style.display='flex';
  }

  function closeModal(){
    backdrop.style.display='none';
  }

  function collectForm(){
    return {
      titulo: fTitulo.value.trim(),
      fecha_inicio: new Date(fInicio.value).toISOString(),
      fecha_fin: new Date(fFin.value).toISOString(),
      descripcion: fDesc.value.trim(),
      tipo_evento: stripAccentsLower(fTipo.value),
      id_usuario: fUsuario.value.trim() || null,
      id_objetivo: fObjetivo.value.trim() || null
    };
  }

  function toLocalInputValue(d){
    // yyyy-MM-ddTHH:mm para <input type="datetime-local">
    const y=d.getFullYear(), m=pad(d.getMonth()+1), day=pad(d.getDate());
    const h=pad(d.getHours()), min=pad(d.getMinutes());
    return `${y}-${m}-${day}T${h}:${min}`;
  }

  async function loadEvents(){
    const [start, end] = currentRange();
    const url = API.list(start.toISOString(), end.toISOString());
    const res = await fetch(url);
    const data = await res.json();
    state.events = (data || []).map(x => ({
      ...x,
      _id: x._id?.$oid || x._id || null, // soporta Extended JSON
    }));
  }

  function currentRange(){
    if(state.view==='week'){
      const s = startOfWeek(state.anchor);
      const e = endOfDay(addDays(s, 6));
      return [s,e];
    }else{
      const s = startOfDay(state.anchor);
      const e = endOfDay(state.anchor);
      return [s,e];
    }
  }

  function render(){
    buildGrid();
    loadEvents().then(drawEvents);
  }

  /* ====== Construir grid (horas + columnas) ====== */
  function buildGrid(){
    const calGrid = document.getElementById('calGrid');
    if(!calGrid) return;
    calGrid.innerHTML = '';
    const [start, end] = currentRange();

    // header title
    const opts = { month:'short', day:'numeric' };
    if(state.view==='week'){
      document.getElementById('rangeTitle').textContent =
        `${start.toLocaleDateString(undefined, opts)} — ${end.toLocaleDateString(undefined, opts)}`;
    }else{
      const opts2 = { weekday:'long', year:'numeric', month:'long', day:'numeric' };
      document.getElementById('rangeTitle').textContent =
        `${state.anchor.toLocaleDateString(undefined, opts2)}`;
    }

    // columna de horas
    const timeCol = el('div','time-col');
    for(let h=0; h<24; h++){
      const slot = el('div','time-slot', `${pad(h)}:00`);
      timeCol.appendChild(slot);
    }
    calGrid.appendChild(timeCol);

    // días
    const days = state.view==='week' ? 7 : 1;
    for(let i=0;i<days;i++){
      const dayDate = state.view==='week' ? addDays(start, i) : state.anchor;
      const col = el('div','day-col');
      if(isSameDay(dayDate, new Date())) col.classList.add('today');

      // cabecera del día
      const head = el('div','date-head');
      head.innerHTML = `<span class="dow">${dayDate.toLocaleDateString(undefined,{weekday:'short'})}</span>
                        <span class="dnum">${dayDate.getDate()}</span>`;
      col.appendChild(head);

      // slots horarios (doble click para crear)
      for(let h=0; h<24; h++){
        const slot = el('div','day-grid-slot');
        slot.dataset.h = h;
        slot.addEventListener('dblclick', ()=>{
          const s = new Date(dayDate); s.setHours(h, 0, 0, 0);
          openModalForCreate(s);
        });
        col.appendChild(slot);
      }
      calGrid.appendChild(col);
    }

    // línea de ahora
    drawNowLine();
  }

  function drawNowLine(){
    const isInRange = isSameDay(state.anchor, new Date()) || state.view==='week';
    const grid = document.getElementById('calGrid');
    if(!grid) return;
    const old = grid.querySelector('.now-line');
    if(old) old.remove();
    if(!isInRange) return;

    const line = el('div','now-line');
    const minutes = new Date().getHours()*60 + new Date().getMinutes();
    const top = minutes * (getHourHeight()/60);
    line.style.top = (top + 26) + 'px'; // +head aprox
    grid.appendChild(line);
  }

  function getHourHeight(){
    const s = getComputedStyle(document.querySelector('.calendar-container'));
    const h = parseFloat(s.getPropertyValue('--hour-h'));
    return isNaN(h) ? 48 : h;
  }

  function drawEvents(){
    const grid = document.getElementById('calGrid');
    if(!grid) return;
    const hourH = getHourHeight();
    const dayCols = [...grid.querySelectorAll('.day-col')];
    const [rangeStart] = currentRange();

    for(const ev of state.events){
      const s = new Date(ev.fecha_inicio);
      const f = new Date(ev.fecha_fin);
      if(isNaN(s) || isNaN(f)) continue;

      const dayIdx = (state.view==='week')
        ? diffDays(rangeStart, startOfDay(s))
        : 0;

      if(dayIdx < 0 || dayIdx >= dayCols.length) continue;

      const col = dayCols[dayIdx];
      const minutesStart = s.getHours()*60 + s.getMinutes();
      const minutesDur = Math.max(30, (f - s)/60000); // mínimo 30 min

      const top = 26 + (minutesStart/60)*hourH; // 26 aprox: head + borde
      const height = (minutesDur/60)*hourH;

      const node = el('div','event');
      node.style.top = `${top}px`;
      node.style.height = `${height}px`;
      const t = stripAccentsLower(ev.tipo_evento || '');
      if(t) node.dataset.type = t;

      node.innerHTML = `
        <div class="title">${escapeHTML(ev.titulo || '(sin título)')}</div>
        <div class="meta">${fmtHM(s)}–${fmtHM(f)}${ev.descripcion ? ' · ' + escapeHTML(ev.descripcion) : ''}</div>
      `;

      node.addEventListener('click', ()=> openModalForEdit(ev));
      col.appendChild(node);
    }
  }

  /* ========= Helpers ========= */
  function el(tag, cls, text){
    const n = document.createElement(tag);
    if(cls) n.className = cls;
    if(text) n.textContent = text;
    return n;
  }

  function isSameDay(a,b){
    return a.getFullYear()===b.getFullYear() && a.getMonth()===b.getMonth() && a.getDate()===b.getDate();
  }
  function diffDays(a,b){ // b - a en días
    const aa = startOfDay(a).getTime(), bb = startOfDay(b).getTime();
    return Math.round((bb-aa)/(24*3600*1000));
  }
  function escapeHTML(s){
    return String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }

  // refrescar línea “ahora” cada minuto
  setInterval(drawNowLine, 60*1000);

  // primera renderización
  render();
});
