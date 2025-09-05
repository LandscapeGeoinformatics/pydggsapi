from pydggsapi.dependencies.collections_providers.abstract_collection_provider import AbstractCollectionProvider
from pydggsapi.schemas.api.collection_providers import CollectionProviderGetDataReturn, CollectionProviderGetDataDictReturn

from dataclasses import dataclass, field
import duckdb
from typing import List, Dict
import logging


logger = logging.getLogger()


@dataclass
class parquet_source():
    filepath: str
    id_col: str
    conn: duckdb.DuckDBPyConnection
    data_cols: List[str] = field(default_factory=["*"])
    exclude_data_cols: List[str] = field(default_factory=list)


# Parquet with in memory duckdb
class ParquetCollectionProvider(AbstractCollectionProvider):

    def __init__(self, params):
        self.datasources: Dict[str, parquet_source] = {}
        for k, v in params.get("datasources", {}).items():
            db = duckdb.connect(":memory:")
            db.install_extension("httpfs")
            db.load_extension("httpfs")
            if (v.get('credential') is not None):
                print(f"create secret ({v['credential']})")
                db.sql(f"create secret ({v['credential']})")
                v.pop('credential')
            v["conn"] = db
            self.datasources[k] = parquet_source(**v)

    def get_data(self, zoneIds: List[str], res: int, datasource_id: str) -> CollectionProviderGetDataReturn:
        result = CollectionProviderGetDataReturn(zoneIds=[], cols_meta={}, data=[])
        try:
            datasource = self.datasources[datasource_id]
        except KeyError:
            logger.error(f'{__name__} {datasource_id} not found')
            return result
        if ("*" in datasource.data_cols):
            cols = f"* EXCLUDE({','.join(datasource.exclude_data_cols)})" if (len(datasource.exclude_data_cols) > 0) else "*"
        else:
            cols_intersection = set(datasource.data_cols) - set(datasource.exclude_data_cols)
            cols = f"{','.join(cols_intersection)}, {datasource.id_col}"
        sql = f"""select {cols} from read_parquet('{datasource.filepath}')
                  where {datasource.id_col} in (SELECT UNNEST(?))"""
        try:
            result_df = datasource.conn.sql(sql, params=[zoneIds]).df()
        except Exception as e:
            logger.error(f'{__name__} {datasource_id} query data error: {e}')
            return result
        result_id = result_df[datasource.id_col]
        result_df = result_df.drop(datasource.id_col, axis=1)
        cols_meta = {k: v.name for k, v in dict(result_df.dtypes).items()}
        result_df = result_df.to_numpy()
        result_id = result_id.to_list()
        result_df = result_df.tolist()
        result.zoneIds, result.cols_meta, result.data = result_id, cols_meta, result_df
        return result

    def get_datadictionary(self, datasource_id: str) -> CollectionProviderGetDataReturn:
        result = CollectionProviderGetDataDictReturn(data={})
        try:
            datasource = self.datasources[datasource_id]
        except KeyError:
            logger.error(f'{__name__} {datasource_id} not found')
            return result
        if ("*" in datasource.data_cols):
            cols = f"* EXCLUDE({','.join(datasource.exclude_data_cols)})" if (len(datasource.exclude_data_cols) > 0) else "*"
        else:
            cols_intersection = set(datasource.data_cols) - set(datasource.exclude_data_cols)
            cols = f"{','.join(cols_intersection)}, {datasource.id_col}"
        sql = f"""select {cols} from read_parquet('{datasource.filepath}') limit 1"""
        try:
            result_df = datasource.conn.sql(sql).df()
        except Exception as e:
            logger.error(f'{__name__} {datasource_id} error: {e}')
            return result
        #result_df = result_df.drop(datasource.id_col, axis=1)
        data = dict(result_df.dtypes)
        for k, v in data.items():
            data[k] = str(v) if (type(v).__name__ != "ObjectDType") else "string"
        result.data = data
        return result
