"""Import UCI's verified Steel Plates Faults manufacturing dataset."""

import hashlib
import io
import os
import urllib.request
import zipfile

import psycopg

URL = "https://archive.ics.uci.edu/static/public/198/steel+plates+faults.zip"
EXPECTED_SHA256 = "CB8EB9859198B63F053E443513036B401746FA517EF58BD17C846C6741C93919".lower()
DATABASE_URL = os.getenv(
    "STEEL_DATABASE_URL",
    "postgresql://supplymind_demo_admin:supplymind-demo-admin@demo-postgres:5432/supplychain",
)


def download() -> bytes:
    with urllib.request.urlopen(URL, timeout=60) as response:  # noqa: S310
        payload = response.read()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"Steel Plates archive checksum mismatch: {digest}")
    return payload


def parse(payload: bytes) -> list[tuple]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        lines = io.TextIOWrapper(archive.open("Faults.NNA"), encoding="utf-8")
        rows = [line.split() for line in lines if line.strip()]
    if not rows or any(len(row) != 34 for row in rows):
        raise RuntimeError("Unexpected Steel Plates row shape")
    return [
        (index, *[float(value) for value in row[:10]], *[int(value) for value in row[27:]])
        for index, row in enumerate(rows, 1)
    ]


def import_rows(rows: list[tuple]) -> int:
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS steel_plate_defects (
                  source_row_id INTEGER PRIMARY KEY,
                  x_minimum DOUBLE PRECISION NOT NULL, x_maximum DOUBLE PRECISION NOT NULL,
                  y_minimum DOUBLE PRECISION NOT NULL, y_maximum DOUBLE PRECISION NOT NULL,
                  pixels_area DOUBLE PRECISION NOT NULL, x_perimeter DOUBLE PRECISION NOT NULL,
                  y_perimeter DOUBLE PRECISION NOT NULL, sum_luminosity DOUBLE PRECISION NOT NULL,
                  min_luminosity DOUBLE PRECISION NOT NULL, max_luminosity DOUBLE PRECISION NOT NULL,
                  pastry SMALLINT NOT NULL, z_scratch SMALLINT NOT NULL, k_scatch SMALLINT NOT NULL,
                  stains SMALLINT NOT NULL, dirtiness SMALLINT NOT NULL, bumps SMALLINT NOT NULL,
                  other_faults SMALLINT NOT NULL, dataset_source TEXT NOT NULL DEFAULT 'UCI Steel Plates Faults',
                  imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.executemany(
                """
                INSERT INTO steel_plate_defects
                  (source_row_id,x_minimum,x_maximum,y_minimum,y_maximum,pixels_area,x_perimeter,
                   y_perimeter,sum_luminosity,min_luminosity,max_luminosity,pastry,z_scratch,k_scatch,
                   stains,dirtiness,bumps,other_faults)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_row_id) DO UPDATE SET
                  pastry=EXCLUDED.pastry,z_scratch=EXCLUDED.z_scratch,k_scatch=EXCLUDED.k_scatch,
                  stains=EXCLUDED.stains,dirtiness=EXCLUDED.dirtiness,bumps=EXCLUDED.bumps,
                  other_faults=EXCLUDED.other_faults
                """,
                rows,
            )
        connection.commit()
    return len(rows)


if __name__ == "__main__":
    print(f"Imported {import_rows(parse(download()))} verified UCI Steel Plates rows")
