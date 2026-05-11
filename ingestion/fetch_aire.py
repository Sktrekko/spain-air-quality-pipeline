"""
Descarga el CSV horario de calidad del aire de Madrid (Ayuntamiento)
y lo sube a GCS + BigQuery.

La URL del CSV se obtiene dinámicamente vía CKAN API para evitar
depender de un nombre de fichero con fecha embebida.
"""

import io
import os
import sys
import logging
from datetime import datetime, timezone

import pandas as pd
import requests
from dotenv import load_dotenv
from google.cloud import bigquery, storage

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# CKAN API del portal de datos abiertos de Madrid
CKAN_API = "https://datos.madrid.es/api/action/resource_show"
RESOURCE_ID = "201200-1-calidad-aire-horario-csv"

GCS_BUCKET = os.environ["GCS_BUCKET"]
BQ_PROJECT = os.environ["BQ_PROJECT"]
BQ_DATASET = os.environ.get("BQ_DATASET", "raw")
BQ_TABLE   = os.environ.get("BQ_TABLE", "mediciones_madrid")

MAGNITUDES = {
    1: "SO2", 6: "CO", 7: "NO", 8: "NO2", 9: "PM2_5",
    10: "PM10", 12: "NOx", 14: "O3", 20: "TOL", 30: "BEN",
    35: "EBE", 37: "MXI", 38: "NMHC", 42: "TCH", 44: "CH4",
}


def get_csv_url() -> str:
    r = requests.get(CKAN_API, params={"id": RESOURCE_ID}, timeout=15)
    r.raise_for_status()
    url = r.json()["result"]["url"]
    log.info("URL CSV: %s", url)
    return url


def fetch_csv(url: str) -> bytes:
    log.info("Descargando CSV...")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def parse_csv(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(
        io.BytesIO(raw),
        sep=";",
        encoding="latin-1",
        dtype=str,
        quotechar='"',
    )
    df.columns = df.columns.str.strip().str.upper()

    hora_cols = [c for c in df.columns if c.startswith("H") and c[1:].isdigit()]
    rows = []
    ingestado = datetime.now(timezone.utc).isoformat()

    for _, row in df.iterrows():
        try:
            magnitud_cod = int(row.get("MAGNITUD", 0))
        except (ValueError, TypeError):
            continue

        magnitud_nombre = MAGNITUDES.get(magnitud_cod, f"MAG_{magnitud_cod}")
        anio = row.get("ANO", "")
        mes  = row.get("MES", "")
        dia  = row.get("DIA", "")

        for hcol in hora_cols:
            hora = int(hcol[1:])
            vcol = f"V{hcol[1:]}"
            valor_str = row.get(hcol, "").strip().replace(",", ".")
            valido = row.get(vcol, "").strip().upper() == "V"

            if not valido or valor_str == "":
                continue

            try:
                valor = float(valor_str)
            except ValueError:
                continue

            try:
                dt = datetime(int(anio), int(mes), int(dia), hora - 1, tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            rows.append({
                "provincia":     str(row.get("PROVINCIA", "")).strip(),
                "municipio":     str(row.get("MUNICIPIO", "")).strip(),
                "estacion":      str(row.get("ESTACION", "")).strip(),
                "punto_muestreo":str(row.get("PUNTO_MUESTREO", "")).strip(),
                "magnitud":      magnitud_nombre,
                "magnitud_cod":  magnitud_cod,
                "fecha_hora":    dt.isoformat(),
                "valor":         valor,
                "ingestado_en":  ingestado,
            })

    return pd.DataFrame(rows)


def upload_to_gcs(raw: bytes, bucket_name: str) -> str:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    ts = datetime.now(timezone.utc).strftime("%Y/%m/%d/%H%M%S")
    blob_name = f"madrid/raw/{ts}.csv"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(raw, content_type="text/csv")
    log.info("Subido a GCS: gs://%s/%s", bucket_name, blob_name)
    return f"gs://{bucket_name}/{blob_name}"


def upload_to_bigquery(df: pd.DataFrame) -> int:
    if df.empty:
        log.warning("DataFrame vacío, nada que subir a BigQuery.")
        return 0

    client = bigquery.Client(project=BQ_PROJECT)
    table_ref = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"

    schema = [
        bigquery.SchemaField("provincia",      "STRING"),
        bigquery.SchemaField("municipio",      "STRING"),
        bigquery.SchemaField("estacion",       "STRING"),
        bigquery.SchemaField("punto_muestreo", "STRING"),
        bigquery.SchemaField("magnitud",       "STRING"),
        bigquery.SchemaField("magnitud_cod",   "INTEGER"),
        bigquery.SchemaField("fecha_hora",     "TIMESTAMP"),
        bigquery.SchemaField("valor",          "FLOAT"),
        bigquery.SchemaField("ingestado_en",   "TIMESTAMP"),
    ]

    df["fecha_hora"]   = pd.to_datetime(df["fecha_hora"],   utc=True)
    df["ingestado_en"] = pd.to_datetime(df["ingestado_en"], utc=True)

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )

    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()
    log.info("Cargadas %d filas en %s", len(df), table_ref)
    return len(df)


def main():
    csv_url = get_csv_url()
    raw = fetch_csv(csv_url)
    upload_to_gcs(raw, GCS_BUCKET)

    df = parse_csv(raw)
    log.info("Registros parseados: %d", len(df))
    if df.empty:
        log.error("No se obtuvieron datos válidos.")
        sys.exit(1)

    log.info("Muestra de magnitudes: %s", df["magnitud"].value_counts().head(5).to_dict())
    filas = upload_to_bigquery(df)
    log.info("Pipeline completado. Filas insertadas en BQ: %d", filas)


if __name__ == "__main__":
    main()
