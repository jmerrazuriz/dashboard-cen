"""Contenido del recorrido guiado del dashboard (datos puros, sin Streamlit).

Cada paso: titulo, nombre corto, pestaña a la que lleva (o None), qué hay, cómo usarlo y los límites de los
datos que entrega el Coordinador Eléctrico Nacional (CEN). Los atrasos y faltantes salen de las pruebas hechas
contra la API (ver docs/API_CEN.md).
"""
from __future__ import annotations

PASOS: list[dict] = [
    {
        "corto": "Inicio",
        "titulo": "Bienvenida: el panel lateral y las tarjetas del encabezado",
        "pestana": None,
        "que_hay": """
Este dashboard muestra datos del **Sistema Eléctrico Nacional (SEN)** de Chile, tomados de las APIs públicas del
**Coordinador Eléctrico Nacional (CEN)**: costos marginales (CMg), generación por tecnología, demanda e
indicadores pensados para evaluar **baterías (BESS)**.

**Panel lateral (izquierda)**
- **Fecha** y botón **Hoy**: elige el día a mostrar (desde enero de 2026) y vuelve al día actual con un clic.
- **Barras**: las barras (puntos de la red) cuyo CMg quieres ver. Por defecto, las 8 principales de 220 kV.
- **Moneda CMg**: USD/MWh o CLP/kWh.
- **Umbral CMg ≈ 0**: bajo cuántos USD/MWh consideras que el precio es «cero» (1 por defecto).
- **Superponer CMg programado**: dibuja sobre el CMg real lo que el CEN había programado.

**Tarjetas del encabezado**: CMg promedio de la última hora, generación total, % renovable, demanda,
**spread promedio** y **horas con CMg ≈ 0** del día elegido.
""",
        "como_usar": """
- Cambia el día con el calendario; si el día es pasado, la primera vez los datos se descargan **en segundo plano**
  y verás una barra de progreso (la página se actualiza sola).
- Abajo del todo hay una tabla de **frescura de los datos**: cuándo se consultó cada fuente, cuál es su último dato
  y cuánto atraso trae.
- La página se refresca sola cada 15 minutos.
""",
        "limites": """
- La API del CEN **limita las consultas**: responde «demasiadas solicitudes» (HTTP 429) con poco uso. Por eso hay
  un máximo de barras por consulta (**10; 6 en la versión pública**) y los datos nuevos tardan en cargar.
- Las tarjetas muestran la **última hora disponible de cada fuente**, y cada fuente llega con un atraso distinto
  (ver el último paso de esta guía).
""",
    },
    {
        "corto": "Resumen",
        "titulo": "Resumen: las tres gráficas principales",
        "pestana": "Resumen",
        "que_hay": """
La pestaña de entrada reúne las tres gráficas clave del día elegido:
1. **Costos marginales** de las barras seleccionadas (hoy y ayer), con el CMg programado en líneas
   discontinuas y punteadas.
2. **Generación por tecnología** (áreas apiladas, MW).
3. **Demanda** (oficial, estimada y pronóstico, MWh).
""",
        "como_usar": """
- Haz clic en el **título de una gráfica** (lleva una flecha →) para ir a la pestaña con todo su detalle.
- Pasa el cursor sobre una curva (o su nombre en la leyenda): se **destaca** y las demás se opacan. Un clic en la
  leyenda la oculta.
- **Ctrl + rueda del mouse** hace zoom; la barra inferior también sirve para acotar el rango. Los iconos de la
  esquina permiten restablecer o descargar la imagen.
""",
        "limites": """
- La **demanda real** llega con unas 10 horas de atraso; por eso se agrega el **pronóstico** del CEN para ver el
  día completo.
""",
    },
    {
        "corto": "Baterías",
        "titulo": "Baterías: dónde está la oportunidad",
        "pestana": "Baterías",
        "que_hay": """
Indicadores para evaluar el negocio de una batería, calculados con el CMg de las barras seleccionadas:
- **Spread diario por barra**: CMg máximo − mínimo, con la hora de cada uno y el promedio de los 7 días previos.
  Es el margen bruto que capturaría una batería que carga en la hora más barata y descarga en la más cara.
- **Mapa de horas con CMg ≈ 0** (barra × hora) con la **curva solar** debajo: muestra cuándo sobra energía.
- **Spread de los últimos 7 días** como tendencia.
- **CMg real vs programado** (PCP del día anterior y PID, la reprogramación intradiaria).
- **Generación solar y eólica programada** (7 días) y su capacidad disponible.
- **Instrucciones del CEN a sistemas de almacenamiento** y un gráfico de cuántos comienzan a cargar o descargar
  en cada hora.
""",
        "como_usar": """
- Ajusta el **umbral de CMg ≈ 0** en el panel lateral para endurecer o relajar lo que cuenta como «energía gratis».
- El gráfico de generación solar y eólica está **desactivado por defecto**: marca la casilla para cargarlo
  (descarga pesada, varios minutos, queda guardada 12 horas).
- Compara el mapa de calor con el gráfico de instrucciones: las baterías **cargan en las horas de sol (CMg ≈ 0)** y
  **descargan al atardecer**, cuando el CMg sube.
""",
        "limites": """
- El **spread es bruto**: no descuenta pérdidas de la batería, límites de energía y potencia, ni costos. **No es una
  proyección de ingresos.**
- El CEN **no publica el pronóstico de generación renovable (ERV)** por esta API; se usa en su lugar la generación
  programada del PCP (un programa, no un pronóstico meteorológico).
- **No hay datos de vertimiento** (energía renovable desperdiciada): esa ruta de la API no está disponible. Lo más
  cercano es la diferencia entre lo disponible y lo programado, que es una estimación.
- El **PID** publicado cubre solo parte del día (en las pruebas, hasta las 17:00) y solo existe para el día actual.
- Las **instrucciones a baterías** se publican con ~1 día de atraso; se muestra el día anterior cuando miras hoy.
  Los sistemas se reconocen por su nombre («SAE», «BESS»).
- Solo algunas barras tienen su equivalente en los programas PCP/PID (≈200 de ~1.650); a las demás no se les
  dibuja la línea programada, y la nota bajo el gráfico lo avisa.
""",
    },
    {
        "corto": "Costos marginales",
        "titulo": "Costos marginales: el precio de la energía en cada barra",
        "pestana": "Costos marginales",
        "que_hay": """
El **costo marginal (CMg)** es el costo de abastecer un MWh adicional en una barra; varía por zona y hora.
- **En línea**: valores cada 15 minutos de ayer y del día elegido, una curva por barra, con el CMg programado:
  **PCP** (programa del día anterior, línea discontinua) y **PID** (reprogramación intradiaria, punteada).
- Una **tabla resumen** del día (mínimo, máximo, promedio y último valor por barra).
- **Histórico (CMg real)**: valores oficiales definitivos o preliminares para un rango de fechas.
""",
        "como_usar": """
- Elige las barras en el panel lateral; el buscador filtra por nombre de subestación.
- En el histórico, define el rango (hasta 31 días), el tipo (DEFINITIVO o PRELIMINAR) y pulsa **Consultar histórico**.
- Cambia entre **USD/MWh** y **CLP/kWh** (las líneas programadas solo existen en USD/MWh).
- Mirando un día pasado, la línea discontinua es lo que **se programó para ese mismo día**, para compararlo con lo
  que realmente ocurrió.
""",
        "limites": """
- El CMg en línea llega con **~30–45 minutos de atraso**.
- El **CMg real** (oficial) se publica con **semanas de atraso**: para fechas recientes el histórico sale vacío.
- Cada barra seleccionada es **una consulta** a la API, por eso el máximo de barras.
- No hay datos de **limitaciones de transmisión** (congestiones) por esta API, así que no se pueden marcar en el
  gráfico las causas de las alzas de precio.
""",
    },
    {
        "corto": "Generación",
        "titulo": "Generación por tecnología: quién produce y cuánto",
        "pestana": "Generación por tecnología",
        "que_hay": """
- **Generación horaria por tecnología** (solar, eólica, hidráulica, geotérmica, BESS, térmica) en áreas apiladas, y
  el **mix del día** en un gráfico de dona con el total en GWh.
- **Top 10 centrales**: cuánto aportan al total, la **empresa propietaria** y su aporte acumulado; por hora o
  acumulado del día.
- **Factor de planta** por tecnología, **cota de embalses**, **generación acumulada del mes y del año**, y un
  **desglose por subtipo**.
- **Programado vs real** por tecnología (casilla opcional).
""",
        "como_usar": """
- En el top 10, cambia entre «Hora» y «Acumulado del día»; pasa el cursor por una barra para ver empresa y MW.
- La zona sombreada del gráfico marca la **hora incompleta**: aún no han reportado todas las centrales.
- Marca «Comparar con la generación programada» para ver la desviación en MWh y % (descarga pesada la primera vez).
""",
        "limites": """
- La **generación real** llega con **2 a 7 horas de atraso**, y la última hora suele venir incompleta (se marca y se
  excluye de los cálculos).
- El **factor de planta** temprano en el día no es representativo (p. ej. el solar sale ~0 antes del amanecer): la
  nota indica qué horas se usaron. Se calcula con la potencia neta efectiva de las unidades generadoras
  (incluye unidades en revisión) y **no incluye BESS**.
- Los **sistemas de almacenamiento no traen propietario** en la API: cuando se llaman «SAE <central>» se muestra el
  dueño de esa central, marcado con **\\***; otros quedan como «Sin dato en la API».
- El reporte de **acumulados del mes y del año** se publica con ~1 día de atraso.
- La **cota de embalses** se actualiza una vez al día (solo los 10 principales).
""",
    },
    {
        "corto": "Demanda",
        "titulo": "Demanda: cuánta energía consume el país",
        "pestana": "Demanda",
        "que_hay": """
- Curva horaria de **demanda de hoy y ayer**: la parte **oficial** (línea continua) y la **estimada** (discontinua)
  con la generación real de las horas que el CEN aún no publica.
- Opcionales: **demanda neta**, **demanda programada** de mañana (PCP) o intradiaria (PID), y el **pronóstico de
  mediano plazo** del CEN.
- **Desviación programado vs real**: error medio y mayor desviación por hora.
""",
        "como_usar": """
- Marca las casillas para sumar líneas al gráfico; pasa el cursor para leer todas las curvas de una hora.
- En «Desviación» elige el programa (PCP o PID) y marca «Calcular desviación».
""",
        "limites": """
- La **«demanda» oficial es la generación bruta** (incluye pérdidas y consumos propios): no es la demanda de los
  clientes. Llega con **~10 horas de atraso** y sus últimas horas vienen a medio cargar, por lo que se descartan
  automáticamente.
- La **demanda neta** descuenta solar, eólica y pasada: **no es la demanda nacional**.
- La «demanda real del sistema» **no está disponible** por la API.
- Para el día actual, la desviación solo cubre las horas con datos reales.
""",
    },
    {
        "corto": "Operación",
        "titulo": "Operación: lo que ocurre en la red",
        "pestana": "Operación",
        "que_hay": """
Información operativa del CEN para el día elegido:
- **Servicios complementarios activados**: ajustes reales que el CEN ordena a las unidades para mantener la
  frecuencia (CPF, CSF, CTF), con hora, unidad y MW.
- **Mantenimientos mayores vigentes**: obras programadas en instalaciones del sistema, con riesgo y consumos
  afectados.
- **Trabajos y desconexiones programados** por las empresas.
""",
        "como_usar": """
- Las descripciones largas muestran las primeras líneas y un enlace **«ver más»** para leerlas completas.
- Cambia el día en el panel lateral para ver lo vigente en otra fecha.
""",
        "limites": """
- Los **mantenimientos** consideran solicitudes de los 60 días previos y los **trabajos**, de los 30 días previos:
  una obra muy larga solicitada antes puede no aparecer.
- Las solicitudes incluyen muchas intervenciones menores (se excluyen las anuladas, los borradores y las rechazadas).
- No hay datos de **energía no suministrada** por la API.
""",
    },
    {
        "corto": "Datos y límites",
        "titulo": "Datos y límites: qué tan fresca es cada información",
        "pestana": None,
        "que_hay": """
Todo viene de las **APIs públicas del Coordinador Eléctrico Nacional**, que publica cada fuente con un retraso
distinto. La tabla resume lo observado:
""",
        "como_usar": """
La tabla de **frescura de los datos** al final de cada pestaña muestra el último dato real de cada fuente en este
momento.
""",
        "limites": """
- **Este dashboard es informativo.** No reemplaza las fuentes oficiales del CEN ni es una proyección financiera o
  recomendación de inversión.
- Las horas son hora de Chile. Los datos más recientes pueden ser **preliminares** y cambiar cuando el CEN los
  complete.
- Si la API del CEN falla o responde lento, la página muestra lo último guardado y reintenta más tarde.
""",
    },
]

# (fuente, atraso, comentario)
ATRASOS: list[tuple[str, str, str]] = [
    ("CMg en línea", "30–45 min", "Cada 15 minutos; una consulta por barra."),
    ("CMg programado PCP", "Sin atraso (proyección)", "Programa del día anterior; ~44.500 filas por día, descarga en segundo plano."),
    ("CMg programado PID", "Parcial", "Reprogramación intradiaria; solo el día actual y no cubre todas las horas."),
    ("CMg real (oficial)", "Semanas", "Para fechas recientes el histórico sale vacío."),
    ("Generación real", "2–7 horas", "La última hora suele venir incompleta."),
    ("Demanda oficial (generación bruta)", "~10 horas", "Las últimas horas vienen a medio cargar."),
    ("Reporte de generación (día, mes, año)", "~1 día", "Servicio Operación."),
    ("Instrucciones a baterías", "~1 día", "Se muestra el día anterior al mirar hoy."),
    ("Cota de embalses", "Diaria", "Los 10 embalses principales."),
    ("Mantenimientos y solicitudes de trabajo", "Variable", "Según fecha de solicitud (60 y 30 días previos)."),
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
    ("CMg", "Costo marginal: precio de la energía en una barra y hora, en USD/MWh o CLP/kWh."),
    ("Barra", "Punto de la red eléctrica (una subestación y su nivel de tensión) donde se mide el CMg."),
    ("PCP", "Programa de Corto Plazo: lo que el CEN programa el día anterior para el día siguiente."),
    ("PID", "Programa Intradiario: la reprogramación que el CEN hace durante el mismo día."),
    ("BESS / SAE", "Sistema de almacenamiento de energía con baterías."),
    ("ERV", "Energías renovables variables: solar y eólica."),
    ("Spread", "Diferencia entre el CMg máximo y mínimo del día: margen bruto de una batería."),
    ("SSCC", "Servicios complementarios (control de frecuencia, etc.) que el CEN ordena a las unidades."),
    ("Factor de planta", "Generación media dividida por la capacidad instalada."),
    ("MW / MWh", "Potencia (MW) y energía (MWh = potencia × horas)."),
]
