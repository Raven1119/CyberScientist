"""Read nullable CSV/Parquet tables without loading unrelated wide columns."""
import csv
import sys
from pathlib import Path

from .common import DEFAULT_DATA


def duckdb_module():
    dependencies=Path(__file__).resolve().parents[2]/'.package-checks/s4_analysis/deps'
    sys.path.insert(0,str(dependencies))
    import duckdb
    return duckdb


def read_table(name, columns=None, root=DEFAULT_DATA):
    csv.field_size_limit(100_000_000)
    path=Path(root)/name
    if path.exists():
        with path.open(newline='') as source:
            for row in csv.DictReader(source):
                yield {key:(row.get(key) or None) for key in (columns or row)}
    else:
        path=path.with_suffix('.parquet')
        duckdb=duckdb_module()
        with duckdb.connect() as connection:
            connection.execute("SET threads=2")
            projection=','.join('"'+key.replace('"','""')+'"' for key in columns) if columns else '*'
            result=connection.execute('SELECT '+projection+' FROM read_parquet(?)',[str(path)])
            fields=[c[0] for c in result.description]
            while batch:=result.fetchmany(1000):
                for values in batch:yield dict(zip(fields,values))


def truth(value):
    return value is True or isinstance(value,str) and value.lower()=='true'
