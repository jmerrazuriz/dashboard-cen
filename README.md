# Dashboard SEN

CMg por barra, generación por tecnología y demanda del SEN, con la API SIP del Coordinador (ver `docs/API_CEN.md`).

## Ejecutar

```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\streamlit run app.py
```

Requiere `.env` con `CEN_USER_KEY=...`. Opcional: `CEN_MIN_INTERVAL` (pausa mínima entre consultas, s).

- `scripts/smoke_test.py`: verificación contra la API real (filtro `bar_transf`, atraso del CMg de hoy; `--burst N` mide el 429).
- `tests/`: `.venv\Scripts\python -m pytest -q tests`
- Caché en `.cache/` (borrarla fuerza una descarga completa).

## Hallazgos verificados (17-11-2026)

- `bar_transf` sí filtra el CMg en línea; el dato de hoy llega con ~40 min de atraso.
- La primera página de 2.000 filas del CMg en línea sin filtro ya trae las 1.654 barras (catálogo en 1 consulta).
- Límite de consultas más estricto que lo esperado: tras un 200, la siguiente a 1,5 s suele dar 429. El cliente usa un throttle adaptativo (sube la pausa con cada 429 hasta 15 s y la relaja con cada éxito).
- `demanda-neta`: `endDate` se interpreta como "ese día 00:00"; se pide hasta+1 día. Las últimas horas oficiales llegan incompletas; se descartan si `gen_bruta_mwh` < 80 % de la generación real de esa hora y se completan con el estimado.
- `getDailySum` está en MWh (coincide exacto con la suma horaria de `gen_real_mw`); las claves vienen como `TOTAL SOLAR`, `TOTAL GENERACIÓN`, etc. No incluye geotérmica.
- `generacion-real` acepta `pageSize=5000` (≈4 páginas por día).
- Endpoints PCP (`cmg-programado-pcp`, `demanda-programada-pcp`): **numeran páginas desde 1**, no desde 0 como los demás v4. En `cmg-programado-pcp`, `page=0` responde HTTP 502; en `demanda-programada-pcp`, `page=0` repite la página 1.
- Los PCP traen el mismo día en **7 programas** (`fecha_programa` de los 7 días previos, con valores distintos): se usa el más reciente por barra y hora. Un día de CMg programado son ~44.500 filas (9 páginas de 5.000, ~14 s c/u), por eso se descarga en segundo plano.
- Mapeo `barra_transf → llave_cmg`: 202 de 1.654 barras tienen equivalente en el PCP (263 barras programadas); las 8 principales sí.
- La caché devuelve la copia vencida al tiro y actualiza en segundo plano (la página no queda en blanco mientras la API responde).

## Días pasados

- Selector de fecha en la barra lateral (desde 01-01-2026) y botón **Hoy** para volver.
- La primera vez que se abre un día pasado sus datos (generación, demanda, mix y una consulta por barra) se descargan **en segundo plano** con barra de progreso; la página muestra lo que ya está listo y se actualiza sola cada 15 s. Las fuentes que fallan (casi siempre 429) se reintentan una vez tras 20 s. Lo descargado queda en caché: cambiar de día o volver a hoy no pierde avance.
- Al agregar barras, solo se descargan las nuevas (en segundo plano: la página no se queda opaca esperando); el CMg se guarda por barra y por día, y una consulta trae el día y los 7 anteriores.
- En días pasados la línea discontinua del CMg es lo que **se programó para ese mismo día** (para comparar con lo ocurrido); hoy, el programa de mañana.

## Ampliación (fases 1–4)

- Pestañas nuevas **Baterías** (spread, horas con CMg ≈ 0, PCP/PID vs real, generación solar/eólica programada, instrucciones a BESS) y **Operación** (servicios complementarios, mantenimientos mayores, solicitudes de trabajo). Detalle de fuentes en `docs/API_CEN.md`, sección 6.
- Segundo servicio de la API (Operación) con su propia clave `CEN_OPERACION_KEY` en `.env`.
- `scripts/smoke_test_extra.py` prueba los endpoints adicionales y guarda el resultado en `scripts/smoke_test_extra.json`.

## Despliegue en línea (Streamlit Community Cloud)

GitHub Pages no ejecuta Python, así que la app se despliega en **Streamlit Community Cloud** desde este repositorio.

1. Entra a <https://share.streamlit.io> con tu cuenta de GitHub → **Create app** → elige este repo, rama `main`, archivo principal `app.py`.
2. En **Advanced settings**: Python **3.13** y pega en **Secrets** (ver `.streamlit/secrets.toml.example`):
   ```toml
   CEN_USER_KEY = "tu-clave-SIP"
   CEN_OPERACION_KEY = "tu-clave-Operación"
   CEN_MODO_PUBLICO = "1"
   ```
3. **Deploy**. Cada `git push` a `main` actualiza la app.

Notas del despliegue público:

- Las claves viven solo en los *Secrets* del hosting; este repositorio no las contiene (`.env` y `.streamlit/secrets.toml` están en `.gitignore`).
- `CEN_MODO_PUBLICO=1` oculta «Forzar actualización» y limita a 6 barras por consulta: todos los visitantes comparten las mismas claves y la API responde 429 con poco uso.
- El disco es efímero: la caché (`.cache/`) se pierde al reiniciar o dormir la app, y la primera visita de cada día vuelve a descargar los datos (varios minutos por el límite de la API; la página muestra el progreso).
- Si una clave se expone por error, pide otra en <https://portal.api.coordinador.cl/admin/applications> y actualiza el Secret.

### Solución de problemas: «La API rechazó la clave (403)»

La app te dice el **largo** de la clave cargada (nunca su contenido). Una clave del CEN tiene **32 caracteres** (letras a–f y números).

- **Menos o más de 32:** el valor está incompleto o con texto de más. Vuelve a copiarlo desde el portal, en *Settings → Secrets*, entre comillas y sin espacios.
- **32 y sigue el 403:** revisa que no hayas cruzado las claves (`CEN_USER_KEY` es del servicio *Información Pública* y `CEN_OPERACION_KEY` del servicio *Operación*) o que la clave siga activa en el portal.
- Después de corregir los Secrets, usa *Manage app → Reboot app*: tras un error, la app no reintenta durante unos minutos.

## Guía del usuario y favicon

- **Recorrido guiado** sobre el propio dashboard (17 pasos): cada paso abre la pestaña que corresponde, enmarca la sección real, oscurece el resto y muestra una ventana con qué hay, cómo usarla y los límites de los datos del Coordinador. Se inicia con «Hacer el recorrido» (aviso de la primera visita) o con «Recorrido guiado» en el panel lateral; teclado: → / Enter, ←, Esc.
  - Contenido de los pasos: `cen/guia.py`. Motor (JavaScript propio, sin librerías externas): `assets/recorrido.js`.
  - Las secciones se marcan en `app.py` con `st.container(key="tour_…")` o `grafico(..., tour="…")`; `tests/test_guia.py` falla si un paso apunta a una sección que no existe. Si se cambia el motor, sube su `version` (en el JS y en `app.py`) para que las páginas abiertas lo recarguen.
- El favicon (una lupa mirando un rayo) está en `assets/favicon.png`; se regenera con `python scripts/generar_favicon.py`.
