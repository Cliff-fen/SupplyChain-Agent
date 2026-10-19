"""Import the public UCI SECOM semiconductor manufacturing dataset.

Only the first ten sensor measurements are materialized as typed columns. The
original archive remains the source of truth and provenance is stored in the
database. Re-running the importer is idempotent by source row id.
"""

import hashlib
import io
import os
import urllib.request
import zipfile
from datetime import datetime

import psycopg

URL = "https://archive.ics.uci.edu/static/public/179/secom.zip"
EXPECTED_SHA256 = "EEA568BAF3C2229096D7D294CF0B096B5502BD96D92C0B80A65B84714059BE8E".lower()
DATABASE_URL = os.getenv(
    "SECOM_DATABASE_URL",
    "postgresql://supplymind_demo_admin:supplymind-demo-admin@demo-postgres:5432/supplychain",
)


def download_archive() -> bytes:
    with urllib.request.urlopen(URL, timeout=60) as response:  # noqa: S310
        payload = response.read()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"SECOM archive checksum mismatch: {digest}")
    return payload


def parse_rows(payload: bytes) -> list[tuple]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        measurements = io.TextIOWrapper(archive.open("secom.data"), encoding="utf-8")
        labels = io.TextIOWrapper(archive.open("secom_labels.data"), encoding="utf-8")
        measurement_rows = [line.split() for line in measurements if line.strip()]
        label_rows = [line.strip().split(maxsplit=1) for line in labels if line.strip()]
    if len(measurement_rows) != len(label_rows):
        raise RuntimeError("SECOM measurement and label row counts differ")
    rows = []
    for index, (values, label) in enumerate(
        zip(measurement_rows, label_rows, strict=True), start=1
    ):
        if len(values) < 10:
            raise RuntimeError(f"SECOM row {index} has too few measurements")
        outcome, timestamp = label
        timestamp = timestamp.strip('"')
        parsed = []
        missing = 0
        for value in values[:10]:
            if value in {"NaN", ""}:
                parsed.append(None)
                missing += 1
            else:
                parsed.append(float(value))
        rows.append(
            (
                index,
                datetime.strptime(timestamp, "%d/%m/%Y %H:%M:%S"),
                int(outcome),
                missing,
                *parsed,
            )
        )
    return rows


def import_rows(rows: list[tuple]) -> int:
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS manufacturing_quality_events (
                  source_row_id INTEGER PRIMARY KEY,
                  measured_at TIMESTAMP NOT NULL,
                  outcome SMALLINT NOT NULL CHECK (outcome IN (-1, 1)),
                  missing_sensor_count SMALLINT NOT NULL,
                  sensor_01 DOUBLE PRECISION, sensor_02 DOUBLE PRECISION,
                  sensor_03 DOUBLE PRECISION, sensor_04 DOUBLE PRECISION,
                  sensor_05 DOUBLE PRECISION, sensor_06 DOUBLE PRECISION,
                  sensor_07 DOUBLE PRECISION, sensor_08 DOUBLE PRECISION,
                  sensor_09 DOUBLE PRECISION, sensor_10 DOUBLE PRECISION,
                  dataset_source TEXT NOT NULL DEFAULT 'UCI SECOM',
                  imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.executemany(
                """
                INSERT INTO manufacturing_quality_events
                  (source_row_id, measured_at, outcome, missing_sensor_count,
                   sensor_01, sensor_02, sensor_03, sensor_04, sensor_05,
                   sensor_06, sensor_07, sensor_08, sensor_09, sensor_10)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_row_id) DO UPDATE SET
                  measured_at = EXCLUDED.measured_at,
                  outcome = EXCLUDED.outcome,
                  missing_sensor_count = EXCLUDED.missing_sensor_count,
                  sensor_01 = EXCLUDED.sensor_01, sensor_02 = EXCLUDED.sensor_02,
                  sensor_03 = EXCLUDED.sensor_03, sensor_04 = EXCLUDED.sensor_04,
                  sensor_05 = EXCLUDED.sensor_05, sensor_06 = EXCLUDED.sensor_06,
                  sensor_07 = EXCLUDED.sensor_07, sensor_08 = EXCLUDED.sensor_08,
                  sensor_09 = EXCLUDED.sensor_09, sensor_10 = EXCLUDED.sensor_10
                """,
                rows,
            )
        connection.commit()
    return len(rows)


if __name__ == "__main__":
    imported = import_rows(parse_rows(download_archive()))
    print(f"Imported {imported} verified UCI SECOM manufacturing rows")
