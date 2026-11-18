/*
 * Recorrido guiado del Dashboard SEN.
 *
 * Se ejecuta en la página principal de Streamlit (app.py lo inserta como <script> en el documento padre).
 * Cada paso: abre la pestaña indicada, busca la sección (selector CSS), la enmarca, oscurece el resto y
 * muestra una ventana con la explicación. Teclado: → / Enter siguiente, ← anterior, Esc salir.
 */
(function () {
  "use strict";
  if (window.cenTour && window.cenTour.version === 4) return;

  var doc = document;
  var pasos = [];
  var i = 0;
  var activo = false;
  var token = 0;          // invalida búsquedas de pasos anteriores
  var objetivo = null;    // elemento enmarcado (o null = ventana centrada)
  var capa, marco, globo, timer;
  var MARGEN = 8;

  var CSS = [
    ".cen-tour-capa{position:fixed;inset:0;z-index:999990;background:transparent}",
    ".cen-tour-marco{position:fixed;z-index:999991;pointer-events:none;border-radius:10px;",
    "  border:3px solid #F5B83D;box-shadow:0 0 0 9999px rgba(15,23,42,.62);",
    "  transition:top .25s,left .25s,width .25s,height .25s}",
    ".cen-tour-marco.vacio{border-width:0}",
    ".cen-tour-globo{position:fixed;z-index:999992;width:400px;max-width:calc(100vw - 24px);",
    "  background:#fff;color:#1F2937;border-radius:12px;box-shadow:0 12px 32px rgba(0,0,0,.28);",
    "  font-family:'Source Sans Pro',system-ui,sans-serif;font-size:14px;line-height:1.45;",
    "  transition:top .25s,left .25s}",
    ".cen-tour-globo .cab{padding:14px 18px 0;font-size:12px;color:#6B7280;display:flex;justify-content:space-between}",
    ".cen-tour-globo .barra{height:4px;background:#EEF1F5;border-radius:2px;margin:8px 18px 0}",
    ".cen-tour-globo .barra i{display:block;height:100%;background:#1F5FA8;border-radius:2px}",
    ".cen-tour-globo h3{margin:10px 18px 4px;font-size:17px;font-weight:700;color:#111827}",
    ".cen-tour-globo .cuerpo{padding:0 18px;max-height:45vh;overflow:auto}",
    ".cen-tour-globo .cuerpo p{margin:6px 0}.cen-tour-globo ul{margin:6px 0;padding-left:18px}",
    ".cen-tour-globo li{margin:3px 0}",
    ".cen-tour-globo .limites{margin:10px 18px 0;padding:8px 10px;border-radius:8px;",
    "  background:#FFF8E6;border:1px solid #F5D78A;font-size:13px}",
    ".cen-tour-globo .limites b.t{display:block;color:#8A5A00;margin-bottom:2px}",
    ".cen-tour-globo .pie{display:flex;align-items:center;gap:8px;padding:14px 18px}",
    ".cen-tour-globo .pie .esp{flex:1}",
    ".cen-tour-globo button{font:inherit;border-radius:8px;padding:6px 14px;cursor:pointer;",
    "  border:1px solid #D1D5DB;background:#fff;color:#1F2937}",
    ".cen-tour-globo button.prim{background:#1F5FA8;border-color:#1F5FA8;color:#fff;font-weight:600}",
    ".cen-tour-globo button.salir{border:none;color:#6B7280;padding-left:0}",
    ".cen-tour-globo button:disabled{opacity:.4;cursor:default}",
    ".cen-tour-globo .cargando{color:#6B7280;font-style:italic}",
    "table.cen-tour-tabla{border-collapse:collapse;width:100%;font-size:12.5px;margin:6px 0}",
    "table.cen-tour-tabla th,table.cen-tour-tabla td{border-bottom:1px solid #EEF1F5;padding:4px 6px;",
    "  text-align:left;vertical-align:top}",
    "table.cen-tour-tabla th{color:#6B7280;font-weight:600}"
  ].join("\n");

  function espera(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function crearNodos() {
    if (!doc.getElementById("cen-tour-css")) {
      var st = doc.createElement("style");
      st.id = "cen-tour-css";
      st.textContent = CSS;
      doc.head.appendChild(st);
    }
    capa = doc.createElement("div"); capa.className = "cen-tour-capa";
    marco = doc.createElement("div"); marco.className = "cen-tour-marco";
    globo = doc.createElement("div"); globo.className = "cen-tour-globo";
    globo.setAttribute("role", "dialog");
    globo.setAttribute("aria-live", "polite");
    doc.body.appendChild(capa); doc.body.appendChild(marco); doc.body.appendChild(globo);
  }

  function quitarNodos() {
    [capa, marco, globo].forEach(function (n) { if (n && n.parentNode) n.parentNode.removeChild(n); });
    capa = marco = globo = null;
  }

  function visible(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  function panelVisible() {
    var ps = doc.querySelectorAll('[data-testid="stTabs"] [role="tabpanel"]');
    for (var k = 0; k < ps.length; k++) if (visible(ps[k])) return ps[k];
    return null;
  }

  function buscar(sel) {
    if (!sel) return null;
    if (sel === "@panel") return panelVisible();
    var el = doc.querySelector(sel);
    return visible(el) ? el : null;
  }

  function pestanaActiva() {
    var t = doc.querySelector('[data-testid="stTabs"] [role="tab"][aria-selected="true"]');
    return t ? t.innerText.trim() : null;
  }

  function abrirPestana(nombre) {
    if (!nombre || pestanaActiva() === nombre) return;
    var ts = doc.querySelectorAll('[data-testid="stTabs"] [role="tab"]');
    for (var k = 0; k < ts.length; k++) {
      if (ts[k].innerText.trim() === nombre) { ts[k].click(); return; }
    }
  }

  function contenido(p, cargando) {
    var n = pasos.length;
    var h = '<div class="cab"><span>Paso ' + (i + 1) + " de " + n + "</span><span>Recorrido guiado</span></div>"
      + '<div class="barra"><i style="width:' + Math.round((i + 1) / n * 100) + '%"></i></div>'
      + "<h3>" + p.titulo + "</h3>"
      + '<div class="cuerpo">' + p.html
      + (cargando ? '<p class="cargando">Cargando esta sección…</p>' : "") + "</div>"
      + (p.limites ? '<div class="limites"><b class="t">Límites de los datos del Coordinador</b>' + p.limites + "</div>" : "")
      + '<div class="pie"><button class="salir" data-a="salir">Salir</button><span class="esp"></span>'
      + '<button data-a="ant"' + (i === 0 ? " disabled" : "") + ">← Anterior</button>"
      + '<button class="prim" data-a="sig">' + (i === n - 1 ? "Terminar" : "Siguiente →") + "</button></div>";
    globo.innerHTML = h;
    globo.querySelector('[data-a="salir"]').onclick = terminar;
    globo.querySelector('[data-a="ant"]').onclick = function () { ir(i - 1); };
    globo.querySelector('[data-a="sig"]').onclick = function () { i === n - 1 ? terminar() : ir(i + 1); };
  }

  // Ubica el recuadro sobre el objetivo (recortado a la ventana) y la ventana explicativa donde quepa.
  function dibujar() {
    if (!activo || !globo) return;
    var vw = window.innerWidth, vh = window.innerHeight;
    var gw = globo.offsetWidth, gh = globo.offsetHeight;
    var el = objetivo && visible(objetivo) ? objetivo : null;
    if (!el) {
      marco.classList.add("vacio");
      marco.style.cssText = "top:" + vh / 2 + "px;left:" + vw / 2 + "px;width:0;height:0";
      globo.style.top = Math.max(12, (vh - gh) / 2) + "px";
      globo.style.left = Math.max(12, (vw - gw) / 2) + "px";
      return;
    }
    marco.classList.remove("vacio");
    var r = el.getBoundingClientRect();
    var top = Math.max(r.top - MARGEN, 6), left = Math.max(r.left - MARGEN, 6);
    var bottom = Math.min(r.bottom + MARGEN, vh - 6), right = Math.min(r.right + MARGEN, vw - 6);
    if (bottom - top < 20) { bottom = top + 20; }
    marco.style.top = top + "px"; marco.style.left = left + "px";
    marco.style.width = (right - left) + "px"; marco.style.height = (bottom - top) + "px";

    var gt, gl;
    if (vw - right >= gw + 24) {               // a la derecha (p. ej. panel lateral)
      gl = right + 14; gt = Math.min(Math.max(12, top), vh - gh - 12);
    } else if (vh - bottom >= gh + 20) {        // debajo
      gt = bottom + 12; gl = Math.min(Math.max(12, left), vw - gw - 12);
    } else if (top >= gh + 20) {                // encima
      gt = top - gh - 12; gl = Math.min(Math.max(12, left), vw - gw - 12);
    } else {                                    // sección más alta que la pantalla: esquina inferior
      gt = vh - gh - 16; gl = vw - gw - 24;
    }
    globo.style.top = gt + "px"; globo.style.left = gl + "px";
  }

  // Desplaza la página para que la sección y la ventana explicativa quepan juntas sin taparse:
  // si caben, ambas quedan centradas (sección arriba, ventana debajo); si no, la sección arriba.
  function desplazarA(el) {
    var main = doc.querySelector('[data-testid="stMain"]');
    var sidebar = doc.querySelector('[data-testid="stSidebar"]');
    if (sidebar && sidebar.contains(el)) return;   // el panel lateral no se desplaza con la página
    var r = el.getBoundingClientRect();
    var vh = window.innerHeight, gh = globo ? globo.offsetHeight : 280;
    var cabe = r.height + gh + 40 <= vh;
    var arriba = cabe ? Math.max(16, (vh - (r.height + gh + 24)) / 2) : 16;
    if (main && main.scrollHeight > main.clientHeight) {
      main.scrollBy({ top: r.top - arriba, behavior: "smooth" });
    } else {
      el.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }

  async function ir(n) {
    if (n < 0 || n >= pasos.length) return;
    i = n;
    var mio = ++token;
    var p = pasos[i];
    objetivo = null;
    contenido(p, !!p.objetivo);
    dibujar();
    abrirPestana(p.pestana);
    if (!p.objetivo) return;
    var t0 = Date.now(), el = null;
    while (Date.now() - t0 < 30000) {           // la pestaña puede tardar en dibujarse (datos, gráficos)
      if (mio !== token || !activo) return;
      el = buscar(p.objetivo);
      if (el && (p.objetivo !== "@panel" || Date.now() - t0 > 1500)) break;
      el = null;
      await espera(250);
    }
    if (mio !== token || !activo) return;
    contenido(p, false);
    if (!el) { dibujar(); return; }              // no apareció: queda centrada con el texto
    desplazarA(el);
    await espera(450);
    if (mio !== token || !activo) return;
    objetivo = el;
    dibujar();
  }

  function teclas(e) {
    if (!activo) return;
    if (e.key === "Escape") { e.preventDefault(); terminar(); }
    else if (e.key === "ArrowRight" || e.key === "Enter") { e.preventDefault(); i === pasos.length - 1 ? terminar() : ir(i + 1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); ir(i - 1); }
  }

  function iniciar() {
    if (!pasos.length) return;
    if (activo) terminar(true);
    activo = true;
    crearNodos();
    doc.addEventListener("keydown", teclas, true);
    window.addEventListener("resize", dibujar);
    timer = setInterval(dibujar, 300);            // sigue a la sección si la página se mueve o redimensiona
    ir(0);
  }

  function terminar(silencioso) {
    activo = false; token++;
    clearInterval(timer);
    doc.removeEventListener("keydown", teclas, true);
    window.removeEventListener("resize", dibujar);
    quitarNodos();
    if (silencioso !== true) {
      abrirPestana("Resumen");
      var main = doc.querySelector('[data-testid="stMain"]');
      if (main) main.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  window.cenTour = {
    version: 4,
    configurar: function (p) { pasos = p || []; },
    iniciar: iniciar,
    terminar: terminar,
    activo: function () { return activo; }
  };
})();
