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
        "titulo": "Baterías: tablas de instrucciones",
        "pestana": "Baterías",
        "objetivo": ".st-key-tour_bat_bess_tablas",
        "html": """
<p><b>Izquierda</b>: cuántas instrucciones recibió cada sistema de almacenamiento y su despacho máximo (la
barra permite comparar de un vistazo).</p>
<p><b>Derecha</b>: cada instrucción con su hora, consigna, MW y la <b>acción</b> en color: comienza carga
(verde), termina carga (azul), comienza descarga (ámbar), termina descarga (rojo).</p>""",
        "limites": "La consigna es el código que usa el CEN; la API no publica su significado.",
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
        "titulo": "Costos marginales: tabla resumen",
        "pestana": "Costos marginales",
        "objetivo": ".st-key-tour_cmg_resumen",
        "html": """
<p>Por barra, para el día elegido: CMg <b>mínimo</b>, <b>máximo</b>, <b>promedio</b> (con barra para
comparar entre barras), el <b>rango</b> máximo − mínimo y el <b>último</b> valor publicado. Se muestra en la
moneda elegida en el panel lateral.</p>""",
        "limites": "Hoy el resumen cubre solo hasta el último cuarto de hora publicado (~30–45 min de atraso).",
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
        "titulo": "Tabla del top 10",
        "pestana": "Generación por tecnología",
        "objetivo": ".st-key-tour_top10_tabla",
        "html": """
<p>Las mismas 10 centrales con su <b>empresa propietaria</b>, tecnología (punto de color), generación,
<b>% del total</b> del sistema (barra) y el <b>% acumulado</b>: cuánto suman entre todas hasta esa fila.</p>""",
        "limites": """Las baterías no traen propietario en la API: si se llaman «SAE &lt;central&gt;» se muestra
el dueño de esa central, marcado con *.""",
    },
    {
        "titulo": "Factor de planta",
        "pestana": "Generación por tecnología",
        "objetivo": ".st-key-tour_factor",
        "html": """
<p>Cuánto de su capacidad instalada usó cada tecnología: <b>generación media ÷ capacidad</b>. La tabla
muestra ambos valores, el factor (barra de 0 a 100 %) y cuántas horas se usaron en el cálculo.</p>""",
        "limites": """Temprano en el día no es representativo (el solar sale ~0 antes del amanecer). La
capacidad incluye unidades en revisión y no incluye baterías.""",
    },
    {
        "titulo": "Embalses",
        "pestana": "Generación por tecnología",
        "objetivo": ".st-key-tour_embalses",
        "html": """
<p>Los 10 embalses principales: <b>llenado</b> (dónde está la cota entre el mínimo y el máximo de
operación) y la cota actual en metros sobre el nivel del mar. Más agua embalsada suele significar más
generación hidráulica disponible.</p>""",
        "limites": "Se actualiza una vez al día.",
    },
    {
        "titulo": "Generación acumulada del mes y del año",
        "pestana": "Generación por tecnología",
        "objetivo": ".st-key-tour_reporte",
        "html": """
<p>Reporte oficial del CEN por tecnología: generación del día, del mes y del año a la fecha (GWh), y la
<b>participación de cada tecnología en el año</b>.</p>""",
        "limites": "Se publica con ~1 día de atraso: al mirar hoy se muestra el reporte de ayer.",
    },
    {
        "titulo": "Programado vs real por tecnología",
        "pestana": "Generación por tecnología",
        "objetivo": ".st-key-tour_gen_prog",
        "html": """
<p>Marca la casilla para comparar lo que el CEN <b>programó</b> generar con lo que realmente se generó, por
tecnología: un gráfico de barras y una tabla con la <b>desviación</b> en MWh y % (verde = se generó más de lo
programado; rojo = menos).</p>""",
        "limites": """Usa el programa completo del CEN (~300.000 filas): la primera vez tarda varios minutos y
queda guardado 12 h. Solo compara las horas con generación real.""",
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
        "titulo": "Desviación de la demanda",
        "pestana": "Demanda",
        "objetivo": ".st-key-tour_dem_desv",
        "html": """
<p>Elige el programa (<b>PCP</b> del día anterior o <b>PID</b> intradiario) y marca «Calcular desviación»: verás
la desviación media, el error medio y la mayor desviación, y una tabla hora por hora (verde = demanda mayor
que la programada; rojo = menor).</p>""",
        "limites": """La demanda real es la generación bruta (incluye pérdidas), así que suele quedar algo sobre lo
programado por barra. Hoy solo hay horas reales hasta ~10 h atrás.""",
    },
    {
        "titulo": "Operación: servicios complementarios",
        "pestana": "Operación",
        "objetivo": ".st-key-tour_op_sscc",
        "html": """
<p>Ajustes reales que el CEN ordenó a las centrales para mantener la frecuencia de la red. <b>Izquierda</b>:
resumen por tipo de servicio (verde = subir generación, rojo = bajar). <b>Derecha</b>: cada activación con
su hora, unidad, MW y motivo.</p>""",
        "limites": "Solo se publican las activaciones del servicio Operación del CEN (OpReal).",
    },
    {
        "titulo": "Operación: mantenimientos mayores",
        "pestana": "Operación",
        "objetivo": ".st-key-tour_op_mant",
        "html": """
<p>Obras programadas en instalaciones del sistema que están vigentes el día elegido: periodo, instalación,
<b>estado</b> (aprobado en verde, pendiente en ámbar), <b>riesgo</b> y si afecta a consumos. Las descripciones
largas tienen «ver más».</p>""",
        "limites": "Se consideran las solicitudes de los 60 días previos: una obra muy antigua puede no aparecer.",
    },
    {
        "titulo": "Operación: trabajos y desconexiones",
        "pestana": "Operación",
        "objetivo": ".st-key-tour_op_trab",
        "html": """
<p>Arriba, cuántas solicitudes hay por tipo y elemento (subestación, línea, central). Abajo, cada trabajo
vigente con su periodo, instalación, empresa y estado.</p>""",
        "limites": """Se consideran las solicitudes de los 30 días previos y se excluyen las anuladas, los borradores y
las rechazadas. Incluye muchas intervenciones menores.""",
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
