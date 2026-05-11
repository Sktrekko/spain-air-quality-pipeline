# Calidad del Aire España — Pipeline de Datos

Pipeline de datos en tiempo real que descarga mediciones de calidad del aire de la red de estaciones de Madrid, las almacena en Google Cloud y las transforma con dbt para análisis y alertas de contaminación.

---

## ¿Qué hace este proyecto?

Cada hora, un script descarga el CSV oficial del Ayuntamiento de Madrid con las mediciones de todos los contaminantes (NO₂, PM10, O₃, SO₂…) de todas las estaciones de la ciudad. Esos datos se guardan en la nube (Google Cloud) y se transforman automáticamente en tablas limpias listas para análisis o dashboards.

```
Portal Datos Madrid (CSV horario)
          │
          ▼
    fetch_aire.py          ← descarga y parsea el CSV
          │
     ┌────┴────┐
     ▼         ▼
    GCS      BigQuery      ← almacenamiento en la nube
  (backup     (raw)
  del CSV)      │
                ▼
              dbt           ← transformaciones SQL
                │
       ┌────────┼────────┐
       ▼        ▼        ▼
   staging  aggregados  alertas  ← tablas limpias y analizables
```

---

## Stack tecnológico

| Tecnología | Para qué se usa |
|---|---|
| **Python 3.11** | Script de ingesta (`fetch_aire.py`) |
| **Google Cloud Storage (GCS)** | Backup de los CSVs originales |
| **Google BigQuery** | Data warehouse — donde viven los datos |
| **dbt** | Transforma los datos crudos en tablas analizables |
| **GitHub Actions** | Ejecuta el pipeline automáticamente cada hora |

---

## Estructura del proyecto

```
aire-espana-pipeline/
│
├── ingestion/
│   ├── fetch_aire.py       # Script principal: descarga CSV → GCS → BigQuery
│   └── requirements.txt    # Dependencias Python
│
├── dbt_project/
│   ├── models/
│   │   ├── staging/
│   │   │   ├── sources.yml         # Define la tabla fuente en BigQuery
│   │   │   └── stg_mediciones.sql  # Limpia y tipifica los datos crudos
│   │   ├── intermediate/
│   │   │   └── int_no2_diario.sql  # Agrega NO₂ por estación y día
│   │   └── marts/
│   │       └── mart_alertas_no2.sql # Clasifica días según niveles UE
│   ├── tests/
│   │   └── assert_no2_valor_positivo.sql  # Test: no debe haber valores negativos
│   └── dbt_project.yml     # Configuración de dbt
│
├── .github/
│   └── workflows/
│       └── pipeline.yml    # CI/CD: ejecuta el pipeline cada hora en GitHub Actions
│
├── .env                    # Variables de entorno locales (NO se sube a Git)
└── README.md               # Este fichero
```

---

## Fuente de datos

**Ayuntamiento de Madrid — Red de Vigilancia de Calidad del Aire**

- URL: [datos.madrid.es](https://datos.madrid.es/portal/site/egob)
- Actualización: horaria
- Contaminantes incluidos: NO₂, NO, NOx, PM10, PM2.5, O₃, SO₂, CO, Tolueno, Benceno y más
- Licencia: [Creative Commons BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- Formato: CSV con separador `;`, una fila por estación/contaminante/día, columnas H01–H24 para cada hora

---

## Cómo ejecutar el proyecto

### Requisitos previos

- Python 3.11 (no 3.12+ ni 3.14 — dbt aún no es compatible)
- Una cuenta de Google Cloud con BigQuery y Cloud Storage habilitados
- `gcloud` CLI instalado y autenticado

### 1. Clonar el repo

```bash
git clone https://github.com/TU_USUARIO/aire-espana-pipeline.git
cd aire-espana-pipeline
```

### 2. Crear el entorno virtual e instalar dependencias

```bash
python3.11 -m venv venv
source venv/bin/activate          # En Windows: venv\Scripts\activate
pip install -r ingestion/requirements.txt
pip install dbt-bigquery
```

### 3. Configurar Google Cloud

```bash
# Autenticarse con tu cuenta de Google
gcloud auth application-default login

# Crear el bucket de GCS (solo la primera vez)
gcloud storage buckets create gs://TU_BUCKET --location=EU

# Crear los datasets de BigQuery (solo la primera vez)
# (o usa la consola web de GCP)
```

### 4. Configurar variables de entorno

Crea un fichero `.env` en la raíz con:

```env
GCS_BUCKET=nombre-de-tu-bucket
BQ_PROJECT=id-de-tu-proyecto-gcp
BQ_DATASET=raw
BQ_TABLE=mediciones_madrid
```

### 5. Ejecutar la ingesta

```bash
source venv/bin/activate
python ingestion/fetch_aire.py
```

Si todo va bien verás algo como:
```
INFO URL CSV: https://datos.madrid.es/...
INFO Descargando CSV...
INFO Subido a GCS: gs://tu-bucket/madrid/raw/2026/05/11/123456.csv
INFO Registros parseados: 1381551
INFO Pipeline completado. Filas insertadas en BQ: 1381551
```

### 6. Ejecutar dbt

```bash
cd dbt_project
dbt run    # ejecuta los modelos SQL
dbt test   # verifica la calidad de los datos
```

---

## Modelos dbt explicados

### `stg_mediciones` (staging)
Toma la tabla cruda `raw.mediciones_madrid` y:
- Convierte tipos de dato (strings → timestamps, floats)
- Filtra filas con valores nulos o negativos
- Añade columnas `fecha` y `hora` por conveniencia

### `int_no2_diario` (intermediate)
Filtra solo el contaminante NO₂ y agrega por estación y día:
- `no2_medio_ugm3` — media diaria
- `no2_max_ugm3` — máximo horario del día
- `no2_p98_ugm3` — percentil 98 (proxy del pico de contaminación)

### `mart_alertas_no2` (marts)
Clasifica cada día/estación según los **umbrales oficiales de la UE**:

| Nivel | Umbral |
|---|---|
| `NORMAL` | NO₂ máx < 180 µg/m³ |
| `INFORMACION` | NO₂ máx ≥ 180 µg/m³ |
| `ALERTA` | NO₂ máx ≥ 400 µg/m³ |
| `LIMITE_ANUAL_SUPERADO` | NO₂ media ≥ 40 µg/m³ |

---

## CI/CD con GitHub Actions

El fichero `.github/workflows/pipeline.yml` configura una ejecución automática **cada hora**.

Para activarlo en tu repo necesitas añadir tres **secrets** en GitHub:
(`Settings → Secrets and variables → Actions → New repository secret`)

| Secret | Valor |
|---|---|
| `GCP_SA_KEY` | JSON completo de la Service Account de GCP |
| `GCS_BUCKET` | Nombre de tu bucket |
| `BQ_PROJECT` | ID de tu proyecto GCP |

---

## Tests de calidad de datos

dbt incluye un test personalizado que verifica que ninguna medición de NO₂ tenga valor negativo (lo que indicaría un error en los datos fuente).

```bash
dbt test
```

---

## Licencia

MIT — úsalo, modifícalo y compártelo libremente.
