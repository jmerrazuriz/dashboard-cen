# Dashboard SEN: costos marginales, generación por tecnología y demanda

> **Versión pública.** Las claves de API fueron reemplazadas por `<clave-oculta>`. En el código se leen de variables de entorno (`CEN_USER_KEY`, `CEN_OPERACION_KEY`); ver `.env.example` y el README.

Documento de contexto para construir el dashboard con Claude Code. Contiene cómo acceder a las APIs del Coordinador Eléctrico Nacional (CEN), lo que ya se verificó con pruebas reales (17-11-2026) y el plan de implementación.

---

## 1. Objetivo

Un dashboard web que muestre:

1. **Costo marginal (CMg) de las barras que el usuario seleccione**: valores en línea (cada 15 min), programados para el día siguiente y, opcionalmente, reales/definitivos (históricos).
2. **Generación actual del SEN separada por tecnología** (Solar, Eólica, Hidráulica, Térmica, BESS, Geotérmica).
3. **Demanda nacional registrada** (horaria).

---

## 2. Acceso a la API

### 2.1 Credencial

- Servicio: **Información Pública (SIP)** en https://portal.api.coordinador.cl (app "Enel X's App").
- Todas las consultas de este dashboard usan **esa única API key**:

```
CEN_USER_KEY = <clave-oculta>
```

- Se envía como parámetro de query: `?user_key=<API_KEY>`.
- En el código, leerla de un archivo `.env` (no dejarla escrita en los `.py`). Crear el `.env` con:

```
# .env  (agregar .env a .gitignore)
CEN_USER_KEY=<clave-oculta>
```

Otras credenciales activas de la misma app (no se usan en este dashboard; solo como referencia):

| Servicio | Credencial | Estado |
|---|---|---|
| Información Pública (SIP) | `<clave-oculta>` | Activo (la que usa el dashboard) |
| Mercados | `<clave-oculta>` | Activo (solo recepción de pronósticos) |
| Utilidades | `<clave-oculta>` | Activo |
| BDUC API - DEV | `<clave-oculta>` | Activo |
| Plataforma de Cadena de Pagos y Garantías | `<clave-oculta>` | Pendiente |
| Operación | en `.env` como `CEN_OPERACION_KEY` (no se transcribe aquí) | Activo: verificada el 18-11-2026 (responde 200) |

> Las credenciales se transcribieron desde una captura del portal. Si una consulta responde `Authentication failed` (HTTP 403), compararla con https://portal.api.coordinador.cl/admin/applications.
>
> Las credenciales reales no están en este repositorio.

### 2.2 URL base

```
https://sipub.api.coordinador.cl
```

Documentación (Swagger): https://portal.api.coordinador.cl/documentacion?service=sipubv2

### 2.3 Límite de consultas (IMPORTANTE)

En las pruebas, varias consultas seguidas devolvieron **HTTP 429 `{"message": "Too Many Requests"}`**. El límite exacto no está documentado. Por eso, el backend debe:

- Hacer las consultas **en secuencia**, no en paralelo, con una pausa de unos 1–2 s entre ellas.
- Reintentar los 429 con *backoff* exponencial (2 s, 4 s, 8 s, 16 s; máximo 5 intentos).
- **Cachear** las respuestas: los datos se actualizan cada 15 min como mínimo, así que no se debe consultar más seguido que eso.
- Nunca descargar el CMg de todas las barras: siempre filtrar por barra (ver 3.1).

### 2.4 Formato general de respuesta

Casi todos los endpoints v4 responden así:

```json
{ "data": [ ... ], "totalPages": 3176, "page": 0, "limit": 50 }
```

La paginación cambia según el endpoint:

| Endpoint | Parámetro de página | Primera página | Tamaño de página |
|---|---|---|---|
| v4 (cmg, demanda) | `page` | **0** | `limit` |
| generacion-real v3 | `page` | **1** | `pageSize` |

Las fechas de los parámetros van en formato `YYYY-MM-DD`.

---

### 2.5 Servicio Operación y especificaciones

- Base URL: `https://operacion.api.coordinador.cl`. Autenticación igual que SIP: `?user_key=<CEN_OPERACION_KEY>` (confirmado en la especificación: `securitySchemes.api-key`, `in: query`, `name: user_key`).
- El cliente (`cen/client.py`) elige URL y clave según el servicio: `CENClient(service="sip")` usa `CEN_USER_KEY`; `CENClient(service="operacion")` usa `CEN_OPERACION_KEY`. Cada servicio tiene su propio throttle y cola de consultas.
- Especificaciones Swagger: `https://portal.api.coordinador.cl/swagger/spec/sip.json` (95 rutas) y `.../operaciones.json` (44 rutas, OpenAPI 3.0.3). **No documentan los campos de respuesta**: los campos de la sección 3.5 salen de las pruebas.
- `portal.api.coordinador.cl` sirve una cadena de certificados incompleta: Python (`requests`/`urllib`) no puede verificarla. Las especificaciones se leyeron desde un navegador; no se desactivó la verificación TLS.

## 3. Endpoints verificados

### 3.1 Costo marginal

#### a) CMg en línea (para ver lo "actual")

```
GET /costo-marginal-online/v4/findByDate?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD&bar_transf=<BARRA>&limit=500&page=0&user_key=...
```

- Se actualiza cada 15 minutos (según la documentación).
- **Verificado:** responde con los datos del día anterior.
- **Sin verificar:** con qué atraso llegan los datos del día actual y si el filtro `bar_transf` funciona. Ambas pruebas dieron 429. Es lo primero que hay que probar al empezar.
- Sin filtro, un día completo tiene unas 160.000 filas (1.654 barras × 96 cuartos de hora). **Siempre filtrar por `bar_transf`.**
- `bar_transf` distingue mayúsculas y minúsculas y debe ir exactamente como lo devuelve la API (por ejemplo `AJAHUEL_______500`, con los guiones bajos de relleno).

Ejemplo real de registro:

```json
{
  "id_info": 248,
  "barra_info": "BA S/E ARENAS BLANCAS 66KV B1",
  "barra_transf": "A.BLANCAS_____066",
  "fecha": "2026-11-16",
  "hra": 0,
  "min": 0,
  "cmg_clp_kwh_": 46.30066,
  "cmg_usd_mwh_": 46.65149,
  "version": "EN LINEA",
  "fecha_hora": "2026-11-16 00:00",
  "fecha_minuto": "2026-11-16 00:00"
}
```

#### b) CMg en línea de 8 barras principales (respaldo, liviano)

```
GET /costos-marginales-online-8b/v4/findAll?user_key=...
```

- **Verificado:** entrega las últimas 24 h con valores horarios para Tarapacá, Crucero, Atacama, Cardones, P. Azúcar, Quillota, Charrúa y P. Montt (220 kV).
- Las fechas vienen como **epoch en milisegundos**.
- Formato: `{"fecha": 1794934421403, "barras": [{"nombre": "Atacama 220 KV", "orden": 2, "valores": [{"fecha": 1794848400000, "valor": 41.18}, ...]}]}`
- Sirve como vista por defecto y como respaldo si el endpoint filtrado da problemas.

#### c) CMg programado (día siguiente)

```
GET /cmg-programado-pcp/v4/findByDate?startDate=<mañana>&endDate=<mañana>&limit=...&page=0&user_key=...
```

- **Verificado:** entrega datos para mañana.
- No tiene filtro por barra, así que hay que descargarlo una vez al día, cachearlo y filtrar localmente.
- La barra se identifica con `llave_cmg` / `nmb_barra_info`, **no** con `barra_transf`. Hay que construir un mapeo entre ambas usando `barra_info` del CMg en línea, `nmb_barra_info` del programado e Infotécnica si hace falta.

```json
{
  "id": 60944449,
  "llave_cmg": "Domeyko220",
  "id_barra_info": 2070,
  "nmb_barra_info": "BA S/E DOMEYKO 220KV BP1",
  "cmg_usd_mwh": 29.4786540708816,
  "fecha_hora": "2026-11-18 00:00:00",
  "fecha_programa": "2026-11-12",
  "zona": "Norte",
  "region": "Antofagasta"
}
```

#### d) CMg real (histórico oficial)

```
GET /costo-marginal-real/v4/findByDate?startDate=...&endDate=...&bar_transf=<BARRA>&type=DEFINITIVO&user_key=...
```

- **Verificado:** con fechas de hace unos 30 días (`version: "REAL-DEF"`). Para fechas recientes viene **vacío**, porque se publica con semanas de atraso.
- `type`: `DEFINITIVO` (por defecto) o `PRELIMINAR`.
- Tiene los mismos campos que el CMg en línea. Solo para la vista histórica.

### 3.2 Generación por tecnología

#### a) Detalle horario por central

```
GET /generacion-real/v3/findByDate?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD&pageSize=1000&page=1&user_key=...
```

- **Verificado:** a las 16:53 había datos de hoy hasta las 14:00, es decir, **unas 2–3 horas de atraso**.
- Un día completo son unas 35 páginas de 1.000 registros. Hay que recorrer todas las páginas (`totalPages`), respetando el límite de consultas.
- Filtro opcional: `tipoTecnologia` (no distingue mayúsculas y minúsculas) e `idCentral`.
- Tecnologías encontradas: `BESS`, `Eólica`, `Geotérmica`, `Hidráulica`, `Solar`, `Térmica`. El subtipo viene en `subtipo_tecnologia` (por ejemplo, Térmica → Diésel).
- Para graficar: sumar `gen_real_mw` agrupando por `fecha_hora` y `tipo_tecnologia`.
- Ojo: `hora` va de 1 a 24, mientras que `fecha_hora` usa 00–23 (`hora = hora de fecha_hora + 1`). Usar `fecha_hora`.

```json
{
  "id_opreal": 230,
  "llave_opreal": "TER ESPERANZA-DS2",
  "id_central": 144,
  "central": "TER ESPERANZA",
  "gen_real_mw": 0.0,
  "fecha_hora": "2026-11-17 14:00:00",
  "hora": 15,
  "potencia_maxima": "1.89",
  "propietario": "ENORCHILE S.A.",
  "coordinado": "ENORCHILE S.A.",
  "tipo_tecnologia": "Térmica",
  "subtipo_tecnologia": "Diésel",
  "factor_ernc": 0.0
}
```

#### b) Total del día por tecnología (liviano)

```
GET /generacion-real/v3/getDailySum?date=YYYY-MM-DD&user_key=...
```

- **Verificado:** funciona para hoy (acumulado del día). Responde con `{"fecha": ..., "data": [{"key": "BESS", "value": 26875.73}, ...]}`.
- La unidad no está documentada; presumiblemente es MWh acumulado. Útil para la tarjeta "mix del día" sin paginar.

### 3.3 Demanda nacional

#### a) Demanda neta / generación bruta horaria (fuente principal)

```
GET /demanda-neta/v4/findByDate?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD&limit=50&user_key=...
```

- **Verificado:** 24 registros horarios por día. A las 16:53, los datos de hoy llegaban solo hasta las 06:00, es decir, **unas 10 horas de atraso**.
- Campos: `gen_bruta_mwh`, `gen_erv_mwh`, `cons_propio_mwh`, `cons_propio_porc`, `demanda_neta_mwh`, `fecha_hora`, `hora`.
- Se cumple que `demanda_neta = gen_bruta − gen_erv − cons_propio`. **La "demanda neta" descuenta la generación solar, eólica y de pasada, así que NO es la demanda nacional.**
- Para la demanda nacional, usar **`gen_bruta_mwh`**, que es la generación bruta total que abastece la demanda más las pérdidas.

#### b) Proxy más actualizado

- La suma horaria de `gen_real_mw` del punto 3.2a, con unas 2–3 h de atraso, da una curva de demanda (generación total) más reciente.
- Recomendación: mostrar `gen_bruta_mwh` (fuente oficial) y completar las horas recientes con la suma de generación real, indicando visualmente cuál es cuál.

#### c) Demanda programada (opcional)

```
GET /demanda-programada-pcp/v4/findByDate?startDate=<mañana>&endDate=<mañana>&user_key=...
```

- **Verificado:** viene por barra (`llave_dem`, `demanda_prog_mw`). Sumar por `fecha_hora` para obtener el total nacional programado.

#### Descartado

- `/demanda-real-estimada/v4/findByDate`: devolvió vacío y se actualiza mensualmente. No sirve.

### 3.4 Resumen de atrasos observados (17-11-2026, 16:53)

| Fuente | Último dato disponible | Atraso aproximado |
|---|---|---|
| CMg en línea (barras filtradas) | Sin verificar para hoy | Documentado: 15 min |
| CMg en línea 8 barras | Últimas 24 h | Bajo |
| CMg programado PCP | Mañana completo | No aplica (proyección) |
| CMg real | Hace unos 30 días | Semanas |
| Generación real | Hoy 14:00 | 2–3 h |
| Demanda neta / gen. bruta | Hoy 06:00 | Unas 10 h |

### 3.5 Endpoints adicionales probados (18-11-2026, 10:10)

Prueba: `scripts/smoke_test_extra.py` (resultado completo en `scripts/smoke_test_extra.json`), con fechas de hoy, ayer y hace 7 días, `limit=100`. "Datos" indica qué fechas devolvieron registros.

**SIP: con datos**

| Endpoint | Datos (hoy/ayer/-7d) | Tamaño de un día | Campos principales | Notas |
|---|---|---|---|---|
| `cmg-programado-pid/v4` | sí/sí/sí | ~4.800 filas hoy; ~33.000 un día pasado | `llave_cmg`, `nmb_barra_info`, `cmg_usd_mwh`, `fecha_hora`, `fecha_programa`, `hora_programa`, `fecha_hora_programa` | Varias reprogramaciones por hora: quedarse con el `fecha_hora_programa`/`hora_programa` más reciente. Hoy cubre hasta ~17:00 a las 10:10. |
| `demanda-programada-pid/v4` | sí/sí/sí | igual que PID CMg | `llave_dem`, `demanda_prog_mw`, `fecha_hora`, `fecha_programa`, `hora_programa` | Por barra: sumar por hora tras deduplicar. |
| `pronosticos-demanda-corto-plazo/v4` | sí/sí/sí | ~3.400 filas | `barra`, `energia_mwh`, `fecha_hora`, `hora` | Por barra; día completo. |
| `pronosticos-demanda-mediano-plazo/v4` | sí/sí/sí | **48 filas** | `tipo_proceso` (SING/SIC), `energia_mwh`, `fecha_hora` | Liviano: total por sistema y hora. |
| `generacion-programada-pcp/v4` | sí/sí/sí | **~309.000 filas** (7 días hacia adelante) | `central`, `tipo_tecnologia` ("Solares"…), `gen_programada_mw`, `capacidad_disponible_mw`, costos, `fecha_programa` | Demasiado pesado para pedir completo (ver 6.3). |
| `generacion-programada-pid/v4` | 404/0/sí | ~88.000 filas | como PCP + `hora_programa` | Irregular: hoy 404 y ayer vacío. |
| `flujo-programado-pcp/v4` / `-pid/v4` | sí/sí/sí | 56.000 / 6.100–41.000 filas | `flujo_lineas`, `flujo_mw`, `perdidas_mw`, barras A/B | Por línea. |
| `potencia-transitada/v4` | no/sí/sí | 6.400–18.600 filas | `empresa`, `barra`, `nombre_linea`, `potencia_mwh`, `hora` | Atraso ~1 día. |
| `instrucciones-operacionales-cmg/v4` | no/sí/sí | ~3.700 filas | `central`, `despacho`, `consigna`, `instruccion_cmg`, `motivo` | Atraso ~1 día. Incluye instrucciones a BESS ("Termina descarga"). |
| `embalse-real/v3/findLast` | sí (sin fechas) | 10 embalses | `nombre`, `cotaActual`, `cotaMax`, `cotaMin`, `porcentajeActual`, `fecha` (epoch ms) | Liviano: tarjeta de embalses. |
| `unidades-generadoras/v4` | sí (independiente de la fecha) | ~3.400 unidades | `central`, `nombre_tecnologia`, `nombre_propietario`, `pot_max_bruta`, `pot_neta_efectiva` | Mejor fuente de capacidad y de propietarios (incluidos BESS). |
| `capacidad-instalada/v4` | sí (sin fechas) | ~1.300 centrales | `nombre_central`, `propietario`, `tipo_tecnologia_central`, `potencia_maxima` | Muchas filas `[EN_REVISION]` con campos vacíos y potencia 0. |
| `solicitudes-trabajo/v4` | no/sí/sí | 74–900 | `empresa_nombre`, `tipo_solicitud`, `type`, `fecha_inicio`, `fecha_fin`, `status` | Filtra por fecha de creación. |
| `programas-mantenimiento-mayor/v4` | vacío en los 3 días | 4.400 en 60 días | `correlativo`, `tipo_instalacion`, `descripcion_trabajo`… | Requiere rango amplio. |
| `stock-combustibles/v4`, `instrucciones-operacionales-sscc/v4`, `pronostico-centrales-pasada/v4` | no/no/sí | pequeños | ver JSON | Publicación semanal o con varios días de atraso. |
| `servicios-complementarios-programados-pcp/v4` | 504/sí/sí | ~617.000 filas | `central`, `provision_mw`, `tipo_servicio` | Muy pesado; hoy dio timeout. |

**SIP: sin datos o con error**

| Endpoint | Resultado |
|---|---|
| `pronostico-erv/v4` | **Vacío** para hoy, ayer, -7 días, los últimos 60 días y los próximos 7 días. No se publica por la API. |
| `limitaciones-transmision/v4`, `energia-no-suministrada/v4` | Vacíos también en un rango de 60 días. |
| `generacion-programada-sum/v3/getSumGeneration` | HTTP 500 siempre (con `technology=Solar` y `Solares`). |
| `api/v2/recursos/demanda_sistema_real/` | Exige `fecha`; con ella responde 200 pero `count: 0`. |
| `generacion-actual/v3`, `costo-marginal-proyectado/v4` | Marcados "No vigente" en la especificación (no probados). |

**Operación** (la clave funciona)

| Endpoint | Resultado |
|---|---|
| `servicios-complementarios/v1` | 200 con datos del mismo día: activaciones reales de SSCC (`instruccionSscc`, `centralUnidad`, `baja`/`sube` MW, `inicioPeriodo`/`finPeriodo`, `motivo`). **Páginas desde 0** (`page=1` es la segunda; una página inexistente da 400); ~300 filas/día. |
| `reportes/v3/generation` | 200 **con `page=0`** (con `page=1` responde "Exceeded the maximum number of pages"). Generación por tecnología del día, mes y año a la fecha (GWh). Hoy aún no publicado (404). |
| `reportes/v3/deviation` | 404 "report in this date not be approved" / 500 si no existe: depende de aprobación. |
| `operativos/v1/estados` | 200: catálogo de estados operativos (texto estático). |
| `mantenimiento-mayor/v1` | Con `fechaInicioLocalGte` 404; sin filtro 200 con 6.815 registros desde 2017 (hay que encontrar el filtro correcto). |
| `reduccion/v1/generacion`, `reduccion/v1/consumo` | **404 "No Mapping Rule matched"**: la ruta no está publicada para esta aplicación en el portal. No hay vertimiento disponible. |
| `unidades-generadoras/v1` | 502 en dos intentos. |
| `net-power/v1/` | No probado (exige `id` de unidad y `unidades-generadoras/v1` falló). |
| Topología, tramos, proyectos, giros, conexión | No aportan al dashboard (catálogos de infraestructura). |

### 3.6 Hallazgos que corrigen lo documentado

- **Paginación**: en casi todos los endpoints v4 nuevos `page=0` da HTTP 502 o repite la página 1: la numeración real parte en **1** (igual que en `cmg-programado-pcp` y `demanda-programada-pcp`). Solo `costo-marginal-online` y `demanda-neta` aceptan `page=0`. En Operación varía: `reportes/v3` parte en 0.
- **Endpoints PCP/PID**: `startDate`/`endDate` filtran por **fecha del programa**, no por la hora programada. Un mismo día aparece en varios programas (PCP: los 7 previos; PID: varias reprogramaciones diarias); hay que quedarse con el más reciente.
- **`demanda-neta`**: `endDate` se interpreta como "ese día 00:00"; hay que pedir hasta el día siguiente. Las últimas horas oficiales llegan incompletas. Se descartan si quedan bajo el 80 % de la generación real de esa hora o, si la generación aún no llega a esa hora, bajo el 80 % de la última hora oficial verificada.
- **`getDailySum`**: está en MWh (coincide con la suma horaria de `gen_real_mw`); claves `TOTAL SOLAR`, `TOTAL GENERACIÓN`, etc.
- **Límite de consultas**: tras un 200, la consulta siguiente a 1,5 s suele dar 429. La prueba completa (185 consultas) tomó 11 min con 46 reintentos.

---

## 4. Plan del dashboard

### 4.1 Stack sugerido

- **Python + Streamlit + Plotly**: es lo más rápido para un dashboard interno. Si se prefiere separar backend y frontend, la alternativa es FastAPI + React, pero no es necesario para empezar.
- `requests` o `httpx` para HTTP; `pandas` para agregaciones.
- Caché local en disco (SQLite o archivos Parquet) para respetar el límite de consultas y no perder el historial.
- `python-dotenv` para leer `CEN_USER_KEY`.

### 4.2 Estructura propuesta

```
dashboard-cen/
├── .env                  # CEN_USER_KEY=<clave-oculta> (no versionar)
├── .gitignore
├── requirements.txt
├── app.py                # UI Streamlit
├── cen/
│   ├── client.py         # cliente HTTP: user_key, throttle, reintentos 429, paginación
│   ├── endpoints.py      # funciones por endpoint (cmg_online, cmg_pcp, gen_real, demanda_neta...)
│   ├── cache.py          # caché en disco con TTL por fuente
│   └── transform.py      # agregaciones (gen por tecnología, mapeo de barras, demanda)
└── tests/
    └── test_transform.py
```

### 4.3 Cliente HTTP (`cen/client.py`)

- Agrega `user_key` a cada request.
- Throttle global: mínimo 1,5 s entre requests (configurable).
- Reintenta 429 y 5xx con backoff exponencial.
- Tiene una función de paginación que sabe si el endpoint empieza en `page=0` (v4) o en `page=1` (v3) y lee `totalPages`.
- Timeout de 60–120 s.

### 4.4 Caché y frecuencias de actualización

| Fuente | TTL de caché | Notas |
|---|---|---|
| CMg en línea por barra | 15 min | Una consulta por barra seleccionada |
| CMg 8 barras | 15 min | Una sola consulta |
| CMg programado PCP | 6 h | Descargar el día completo una vez y filtrar localmente |
| Generación real (hoy) | 30 min | Paginado; volver a consultar solo el día actual |
| Generación real (días pasados) | Permanente | Ya no cambia |
| getDailySum | 30 min | |
| Demanda neta | 1 h | |
| Lista de barras | 24 h | Se arma a partir del CMg en línea de ayer |

### 4.5 Selector de barras

1. Una vez al día, armar el catálogo de barras: descargar el CMg en línea de ayer (todas las páginas, pausadamente, o lo suficiente para obtener los 1.654 `barra_transf` distintos) y guardar `barra_transf` + `barra_info`.
2. En la UI, usar un `multiselect` con búsqueda que muestre `barra_info` (nombre legible) y use `barra_transf` como valor.
3. Barras por defecto: las 8 principales (Crucero 220, Quillota 220, Charrúa 220, etc.).
4. Limitar a unas 10 barras seleccionadas para no chocar con el límite de consultas.

### 4.6 Vistas

**Encabezado (KPIs)**
- CMg promedio de la última hora en las barras seleccionadas (USD/MWh).
- Generación total de la última hora disponible (MW) y su hora.
- Porcentaje renovable de la última hora (usar `factor_ernc` o las tecnologías Solar + Eólica + Hidráulica + Geotérmica).
- Demanda (generación bruta) de la última hora disponible.

**Pestaña 1: Costos marginales**
- Gráfico de líneas: CMg en línea (15 min) de hoy y ayer para cada barra seleccionada.
- Superpuesto, en línea punteada: CMg programado PCP de mañana para esas barras (si hay mapeo).
- Selector de moneda: USD/MWh o CLP/kWh.
- Tabla con mínimo, máximo y promedio por barra.
- Opcional: modo histórico con el CMg real DEFINITIVO para un rango de fechas.

**Pestaña 2: Generación por tecnología**
- Áreas apiladas por hora de hoy, por `tipo_tecnologia`, con un color fijo para cada tecnología.
- Gráfico de dona con el mix del día (getDailySum).
- Opcional: desglose por `subtipo_tecnologia` y top 10 de centrales.

**Pestaña 3: Demanda**
- Línea horaria de `gen_bruta_mwh` de hoy y ayer.
- Las horas recientes completadas con la suma de generación real, en otro estilo y con nota "estimado".
- Opcional: demanda programada PCP de mañana (suma por hora).
- Opcional: línea de `demanda_neta_mwh` como referencia, con explicación en el tooltip.

**Pie de página:** hora de la última actualización de cada fuente y su atraso.

### 4.7 Orden de implementación

1. **Cliente + verificación** (`client.py`, `endpoints.py`) y un script `scripts/smoke_test.py` que confirme:
   - Que `bar_transf` filtra el CMg en línea (con una sola barra).
   - El último `fecha_minuto` disponible hoy en el CMg en línea.
   - El comportamiento ante 429 (cuántas consultas seguidas aguanta).
2. Caché en disco con TTL.
3. Transformaciones y tests (agregación por tecnología, armado del catálogo de barras).
4. UI Streamlit: pestaña Generación (la fuente más simple y ya verificada).
5. Pestaña Demanda.
6. Pestaña CMg con selector de barras.
7. KPIs, pie de página con frescura de datos y autorrefresco cada 15 min (`st_autorefresh` o `st.rerun` con temporizador).
8. Mapeo `barra_transf` ↔ `llave_cmg` para superponer el CMg programado.

### 4.8 Pendientes y riesgos

- **Límite de consultas sin documentar**: medirlo en el paso 1 y ajustar el throttle.
- **Filtro `bar_transf`**: confirmar que funciona; si no, usar el endpoint de 8 barras como respaldo.
- **Atraso del CMg en línea del día actual**: confirmar.
- **Unidad de `getDailySum`**: confirmar (comparar con la suma horaria de `gen_real_mw`).
- La demanda oficial (`gen_bruta_mwh`) llega con unas 10 h de atraso; hay que dejarlo claro en la UI.
- Algunas centrales aparecen con la marca `[EN_REVISION]` en el nombre; limpiarla para mostrar.

---

## 5. Fuentes complementarias (sin API key)

- Infotécnica API pública (barras, centrales, empresas): https://api-infotecnica.coordinador.cl/v1/barras/, `/v1/centrales/`, `/v1/empresas/`. Sirve para enriquecer las barras con subestación, región o tensión.
- Programa de la operación (gráficos web): https://programa.coordinador.cl/operacion

---

## 6. Ampliación (implementada, fases 1–4, 18-11-2026)

### 6.1 Pestaña "Baterías"

| Vista | Fuente | Estado |
|---|---|---|
| Spread diario por barra (máx − mín con sus horas; promedio de 7 días) | CMg en línea ya descargado + historial de 7 días en segundo plano (1 consulta por barra) | Implementado |
| Mapa de calor barra × hora con CMg < umbral (1 USD/MWh por defecto, ajustable), con la curva solar | CMg en línea + generación real | Implementado |
| CMg real vs PCP vs PID del día elegido | `cmg-programado-pcp`, `cmg-programado-pid` (último programa por barra y hora) | Implementado. El PID observado cubre solo hasta ~17:00 y viene de un programa de días anteriores: la nota indica su fecha |
| Generación solar y eólica programada (en lugar del pronóstico ERV) + capacidad disponible + real | `generacion-programada-pcp` (~62 páginas): casilla opcional, segundo plano, caché 12 h | Implementado. `pronostico-erv` y `generacion-programada/v3/findAll` no sirven (vacío / HTTP 500) |
| Instrucciones del CEN a sistemas de almacenamiento | `instrucciones-operacionales-cmg` filtrando SAE/BESS | Implementado (día anterior cuando se mira hoy: ~1 día de atraso) |
| Vertimiento | `reduccion/v1/*` no accesible (404) | Descartado |

### 6.2 Cambios en pestañas existentes

- **Encabezado (KPIs)**: spread promedio del día y horas promedio con CMg ≈ 0.
- **Costos marginales**: línea PID (punteada) además del PCP (discontinua), solo para hoy.
- **Generación**: factor de planta del día por tecnología (capacidad = potencia neta efectiva de `unidades-generadoras/v4`; sin BESS), cota de embalses (`embalse-real/v3/findLast`), generación del día/mes/año a la fecha (`reportes/v3/generation`, servicio Operación, `page=0`, ~1 día de atraso) y programado vs real por tecnología (casilla; usa la misma descarga que el pronóstico solar/eólico).
- **Demanda**: líneas opcionales de demanda programada PID y pronóstico de mediano plazo (SING + SIC); cálculo de desviación programado (PCP o PID) vs real: desviación media, error absoluto medio y mayor desviación por hora.
- **Pestaña "Operación"** (nueva): activaciones reales de servicios complementarios (`servicios-complementarios/v1`, Operación), mantenimientos mayores vigentes (`programas-mantenimiento-mayor`, filtrados por `fecha_inicio_programa`/`fecha_fin_programa`) y solicitudes de trabajo vigentes (`solicitudes-trabajo`).

### 6.3 Descartado o pendiente

- **Propietarios de BESS**: `unidades-generadoras/v4` solo trae 2 unidades BESS (PMGD en revisión); no resuelve los 37 sistemas SAE/BESS sin propietario. Se mantiene la inferencia por nombre "SAE <central>".
- **Limitaciones de transmisión, energía no suministrada, pronóstico ERV, demanda real del sistema**: sin datos en la API.
- **`unidades-generadoras/v1` y `net-power/v1/` (Operación)**: HTTP 502; `mantenimiento-mayor/v1` (Operación): no se encontró el filtro de fechas (se usa el endpoint SIP).
- Todas las fuentes nuevas usan caché y descarga en segundo plano: la página nunca espera a la API.
