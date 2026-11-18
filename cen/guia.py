"""Contenido del recorrido guiado (datos puros, sin Streamlit).

El recorrido se dibuja SOBRE el dashboard: cada paso enmarca una sección real, oscurece el resto y muestra
una ventana con la explicación (motor en assets/recorrido.js). Cada paso define:

- ``titulo`` y ``html``: el texto de la ventana (HTML simple y fijo, escrito aquí).
- ``limites``: límites de los datos del Coordinador para esa sección (HTML; puede ir vacío).
- ``pestana``: pestaña que hay que abrir antes de enmarcar (o None).
- ``objetivo``: selector CSS de la sección a enmarcar; ``"@panel"`` = la pestaña visible; None = ventana
  centrada sin recuadro. Las secciones se marcan en app.py con ``st.container(key="tour_...")``, que
  Streamlit expone como la clase ``st-key-tour_...``.

Los atrasos y faltantes salen de las pruebas hechas contra la API (ver docs/API_CEN.md).
"""
from __future__ import annotations

import html
import json

# (fuente, atraso, comentario)
ATRASOS: list[tuple[str, str, str]] = [
    ("CMg en línea", "30–45 min", "Cada 15 minutos; una consulta por barra."),
    ("CMg programado PCP", "Proyección", "Programa del día anterior para el día siguiente."),
    ("CMg programado PID", "Parcial", "Solo el día actual y no cubre todas las horas."),
    ("CMg real (oficial)", "Semanas", "Para fechas recientes el histórico sale vacío."),
    ("Generación real", "2–7 horas", "La última hora suele venir incompleta."),
    ("Demanda oficial", "~10 horas", "Es la generación bruta; las últimas horas vienen a medio cargar."),
    ("Acumulados del mes y año", "~1 día", "Reporte del servicio Operación."),
    ("Instrucciones a baterías", "~1 día", "Al mirar hoy se muestra el día anterior."),
    ("Cota de embalses", "Diaria", "Los 10 embalses principales."),
]

# Lo que el CEN no entrega por la API (probado)
NO_DISPONIBLE: list[str] = [
    "Pronóstico de generación renovable (ERV)",
    "Vertimiento (energía renovable desperdiciada)",
    "Limitaciones de transmisión (congestiones)",
    "Energía no suministrada",
    "Demanda real del sistema",
    "Propietario de los sistemas de almacenamiento (BESS)",
]

GLOSARIO: list[tuple[str, str]] = [
    ("CMg", "Costo marginal: precio de la energía en una barra y hora (USD/MWh o CLP/kWh)."),
    ("Barra", "Punto de la red (una subestación y su tensión) donde se mide el CMg."),
    ("PCP", "Programa de Corto Plazo: lo que el CEN programa el día anterior."),
    ("PID", "Programa Intradiario: la reprogramación del mismo día."),
    ("BESS / SAE", "Sistema de almacenamiento de energía con baterías."),
    ("ERV", "Energías renovables variables: solar y eólica."),
    ("Spread", "CMg máximo − mínimo del día: margen bruto de una batería."),
    ("SSCC", "Servicios complementarios (control de frecuencia) que ordena el CEN."),
    ("Factor de planta", "Generación media ÷ capacidad instalada."),
    ("MW / MWh", "Potencia (MW) y energía (MWh = potencia × horas)."),
]


def _tabla(filas: list[tuple], cabecera: tuple) -> str:
    th = "".join(f"<th>{html.escape(c)}</th>" for c in cabecera)
    tr = "".join("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in f) + "</tr>" for f in filas)
    return f'<table class="cen-tour-tabla"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'


PASOS: list[dict] = [
    {
        "titulo": "Bienvenida al Dashboard SEN",
        "pestana": "Resumen",
        "objetivo": None,
        "html": """
<p>Datos del <b>Sistema Eléctrico Nacional</b> tomados de las APIs públicas del <b>Coordinador Eléctrico
Nacional (CEN)</b>: costos marginales, generación, demanda e indicadores para evaluar <b>baterías</b>.</p>
<p>En unos pocos pasos te mostramos cada parte. Usa <b>Siguiente</b> / <b>Anterior</b> (o las flechas del
teclado) y <b>Esc</b> para salir. Puedes repetir el recorrido desde el panel lateral.</p>""",
        "limites": "",
    },
    {
        "titulo": "Panel lateral: qué mirar",
        "pestana": None,
        "objetivo": '[data-testid="stSidebar"]',
        "html": """
<ul>
<li><b>Fecha</b> y <b>Hoy</b>: elige el día (desde enero de 2026) y vuelve al actual.</li>
<li><b>Barras</b>: puntos de la red cuyo CMg quieres ver; busca por subestación.</li>
<li><b>Moneda</b>: USD/MWh o CLP/kWh.</li>
<li><b>Umbral CMg ≈ 0</b>: bajo cuántos USD/MWh el precio cuenta como «cero».</li>
<li><b>Superponer CMg programado</b>: dibuja lo que el CEN había programado.</li>
</ul>
<p>Un día pasado se descarga la primera vez en segundo plano, con barra de progreso.</p>""",
        "limites": """La API limita las consultas: cada barra es una consulta, por eso hay un máximo
(10; 6 en la versión pública) y los días nuevos tardan unos minutos en cargar.""",
    },
    {
        "titulo": "Tarjetas: el día en una mirada",
        "pestana": None,
        "objetivo": ".kpi-grid",
        "html": """
<p>CMg promedio de la última hora, generación total, % renovable, demanda, <b>spread</b> (CMg máximo −
mínimo) y <b>horas con CMg ≈ 0</b> del día elegido. Bajo cada valor se indica de qué hora es.</p>""",
        "limites": """Cada fuente llega con un atraso distinto: CMg ~30–45 min, generación 2–7 h y
demanda ~10 h. Por eso las tarjetas no son todas de la misma hora.""",
    },
    {
        "titulo": "Las secciones del dashboard",
        "pestana": None,
        "objetivo": '[data-testid="stTabs"] [role="tablist"]',
        "html": """
<p><b>Resumen</b> (vista general), <b>Baterías</b>, <b>Costos marginales</b>, <b>Generación</b>,
<b>Demanda</b> y <b>Operación</b>. En el Resumen, el título de cada gráfico (con la flecha →) lleva a su
sección.</p>""",
        "limites": "",
    },
    {
        "titulo": "Resumen: cómo leer los gráficos",
        "pestana": "Resumen",
        "objetivo": ".st-key-tour_res_cmg",
        "html": """
<ul>
<li>Pasa el cursor sobre una curva o su nombre en la leyenda: se <b>destaca</b> y el resto se opaca.</li>
<li>Clic en la leyenda para <b>ocultar</b> una curva.</li>
<li><b>Ctrl + rueda</b> o la barra inferior para hacer zoom; los iconos de la esquina restablecen o
descargan la imagen.</li>
<li>Línea discontinua: CMg programado (PCP); punteada: reprogramación del día (PID).</li>
</ul>
<p>Todos los gráficos del dashboard funcionan igual.</p>""",
        "limites": "",
    },
    {
        "titulo": "Baterías: spread por barra",
        "pestana": "Baterías",
        "objetivo": ".st-key-tour_bat_spread",
        "html": """
<p>El <b>spread</b> es CMg máximo − mínimo del día, con la hora de cada uno y el promedio de los 7 días
previos: el margen que capturaría una batería que carga en la hora más barata y descarga en la más cara.</p>""",
        "limites": """Es un margen <b>bruto</b>: no descuenta pérdidas, límites de energía y potencia ni costos.
No es una proyección de ingresos.""",
    },
    {
        "titulo": "Baterías: horas con CMg ≈ 0",
        "pestana": "Baterías",
        "objetivo": ".st-key-tour_bat_mapa",
        "html": """
<p>Cada celda muestra cuántos minutos de esa hora el CMg estuvo bajo el umbral. Coinciden con la
<b>curva solar</b> de abajo: son las horas en que sobra energía y conviene cargar.</p>""",
        "limites": """El CEN no publica el <b>vertimiento</b> (energía renovable desperdiciada) por esta API; el
mapa es la mejor señal disponible.""",
    },
    {
        "titulo": "Baterías: real vs programado",
        "pestana": "Baterías",
        "objetivo": ".st-key-tour_bat_prog",
        "html": """
<p>Compara el CMg real del día con lo que programó el CEN el día anterior (PCP) y su reprogramación
intradiaria (PID). Más abajo puedes cargar la <b>generación solar y eólica programada</b> de 7 días
(descarga pesada, opcional).</p>""",
        "limites": """No hay pronóstico renovable (ERV) en la API: se usa el programa del CEN. El PID solo
cubre parte del día actual, y solo ~200 de ~1.650 barras tienen equivalente en los programas.""",
    },
    {
        "titulo": "Baterías: cuándo cargan y descargan",
        "pestana": "Baterías",
        "objetivo": ".st-key-tour_bat_bess",
        "html": """
<p>Instrucciones del CEN a los sistemas de almacenamiento: cuántos <b>comienzan a cargar</b> (horas de sol)
y a <b>descargar</b> (atardecer) en cada hora, con el detalle por sistema.</p>""",
        "limites": """Se publican con ~1 día de atraso (al mirar hoy se muestra ayer). Los sistemas se
reconocen por su nombre («SAE», «BESS»).""",
    },
    {
        "titulo": "Costos marginales",
        "pestana": "Costos marginales",
        "objetivo": ".st-key-tour_cmg_online",
        "html": """
<p>CMg cada 15 minutos de ayer y del día elegido, una curva por barra, con su resumen (mínimo, máximo,
promedio). Arriba puedes cambiar a <b>Histórico</b> para ver el CMg real oficial de un rango de fechas.</p>""",
        "limites": """El CMg real oficial se publica con <b>semanas</b> de atraso. No hay datos de
<b>congestiones de transmisión</b> en la API para explicar las alzas.""",
    },
    {
        "titulo": "Generación por tecnología",
        "pestana": "Generación por tecnología",
        "objetivo": ".st-key-tour_gen_tec",
        "html": """
<p>Generación horaria por tecnología (áreas apiladas) y, al lado, el mix del día. La zona sombreada es la
<b>hora incompleta</b>: aún no reportan todas las centrales.</p>""",
        "limites": "La generación real llega con 2 a 7 horas de atraso.",
    },
    {
        "titulo": "Top 10 centrales y más",
        "pestana": "Generación por tecnología",
        "objetivo": ".st-key-tour_top10",
        "html": """
<p>Las 10 centrales que más aportan, con su <b>empresa</b> propietaria (por hora o acumulado). Más abajo:
factor de planta, cota de embalses, acumulados del mes y año, y programado vs real.</p>""",
        "limites": """Las baterías no traen propietario en la API: si se llaman «SAE &lt;central&gt;» se muestra
el dueño de esa central, marcado con *. El factor de planta temprano en el día no es representativo.""",
    },
    {
        "titulo": "Demanda",
        "pestana": "Demanda",
        "objetivo": ".st-key-tour_demanda",
        "html": """
<p>Demanda de hoy y ayer: <b>oficial</b> (continua), <b>estimada</b> con la generación real (discontinua) y
<b>pronóstico</b> del CEN. Las casillas suman la demanda programada (PCP/PID) y la neta; abajo se calcula la
desviación programado vs real.</p>""",
        "limites": """La «demanda» oficial es la <b>generación bruta</b> (incluye pérdidas) y llega con ~10 h de
atraso. La demanda neta descuenta solar, eólica y pasada: no es la demanda del país.""",
    },
    {
        "titulo": "Operación",
        "pestana": "Operación",
        "objetivo": "@panel",
        "html": """
<p>Lo que ocurre en la red el día elegido: <b>servicios complementarios</b> activados, <b>mantenimientos
mayores</b> vigentes y <b>trabajos y desconexiones</b>. Las descripciones largas tienen «ver más».</p>""",
        "limites": """Se consideran solicitudes de los 60 días (mantenimientos) y 30 días (trabajos) previos:
una obra muy antigua puede no aparecer.""",
    },
    {
        "titulo": "¿Qué tan frescos están los datos?",
        "pestana": None,
        "objetivo": ".st-key-tour_frescura",
        "html": """
<p>Al final de cada sección: cuándo se consultó cada fuente, cuál es su último dato y cuánto atraso
trae. La página se actualiza sola cada 15 minutos.</p>""",
        "limites": "",
    },
    {
        "titulo": "Límites de los datos del Coordinador",
        "pestana": "Resumen",
        "objetivo": None,
        "html": _tabla(ATRASOS, ("Fuente", "Atraso", "Comentario"))
        + "<p><b>No disponible en la API</b> (probado): " + "; ".join(html.escape(x) for x in NO_DISPONIBLE)
        + ".</p>",
        "limites": """Dashboard <b>informativo</b>: no reemplaza las fuentes oficiales del CEN ni es una
recomendación de inversión. Horas de Chile; los datos recientes pueden ser preliminares.""",
    },
    {
        "titulo": "Glosario",
        "pestana": "Resumen",
        "objetivo": None,
        "html": _tabla(GLOSARIO, ("Término", "Significado"))
        + "<p>Listo. Repite el recorrido cuando quieras con <b>Recorrido guiado</b> en el panel lateral.</p>",
        "limites": "",
    },
]

# Secciones que app.py debe marcar con st.container(key=...) para que el recorrido las encuentre
SECCIONES_MARCADAS: list[str] = sorted({p["objetivo"][len(".st-key-"):] for p in PASOS
                                        if p["objetivo"] and p["objetivo"].startswith(".st-key-")})


def pasos_json() -> str:
    """Pasos serializados para el motor JS (se insertan en un <script>: se escapa «</»)."""
    datos = [{k: p[k] for k in ("titulo", "html", "limites", "pestana", "objetivo")} for p in PASOS]
    return json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
