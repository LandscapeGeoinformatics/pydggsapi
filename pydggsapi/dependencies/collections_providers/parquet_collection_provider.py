from pydggsapi.dependencies.collections_providers.abstract_collection_provider import (
    AbstractCollectionProvider,
    AbstractDatasourceInfo,
    DatetimeNotDefinedError
)
from pydggsapi.schemas.api.collection_providers import (
    CollectionProviderGetDataReturn,
    CollectionProviderGetDataDictReturn
)
from pydggsapi.schemas.ogc_dggs.dggrs_zones import zone_datetime_placeholder
from dataclasses import dataclass
from pygeofilter.ast import AstType
from pygeofilter.backends.sql import to_sql_where
import duckdb
from typing import List
import logging

logger = logging.getLogger()


@dataclass
class ParquetDatasourceInfo(AbstractDatasourceInfo):
    filepath: str = ""
    id_col: str = ""
    credential: str = ""
    conn: duckdb.DuckDBPyConnection = None


# Parquet with in memory duckdb
class ParquetCollectionProvider(AbstractCollectionProvider):

    def __init__(self, datasources):
        self.datasources = {}
        for k, v in datasources.items():
            db = duckdb.connect(":memory:")
            db.install_extension("httpfs")
            db.load_extension("httpfs")
            if (v.get('credential') is not None):
                db.sql(f"create secret ({v['credential']})")
                v.pop('credential')
            v["conn"] = db
            if (v.get('filepath') is None or v.get('filepath') == ''):
                logger.error(f'{__name__} {k} filepath is missing')
                raise Exception(f'{__name__} {k} filepath is missing')
            self.datasources[k] = ParquetDatasourceInfo(**v)

    def get_data(self, zoneIds: List[str], res: int, datasource_id: str,
                 cql_filter: AstType = None, include_datetime: bool = False,
                 include_properties: List[str] = None,
                 exclude_properties: List[str] = None) -> CollectionProviderGetDataReturn:
        result = CollectionProviderGetDataReturn(zoneIds=[], cols_meta={}, data=[])
        try:
            datasource = self.datasources[datasource_id]
        except KeyError:
            logger.error(f'{__name__} {datasource_id} not found')
            raise Exception(f'{__name__} {datasource_id} not found')
        if ("*" in datasource.data_cols):
            incl = ",".join(include_properties) if include_properties else "*"
            excl = datasource.exclude_data_cols or []
            excl.extend(exclude_properties or [])
            cols = f"{incl} EXCLUDE({','.join(excl)})" if (len(excl) > 0) else incl
        else:
            incl = cols_intersection = set(datasource.data_cols) - set(datasource.exclude_data_cols)
            if include_properties:
                incl &= set(include_properties)
            if exclude_properties:
                incl -= set(exclude_properties)
            cols = f"{','.join(incl)}, {datasource.id_col}"
        sql = f"""select {cols} from read_parquet('{datasource.filepath}')
                  where {datasource.id_col} in (SELECT UNNEST(?))"""
        if (cql_filter is not None):
            fieldmapping = self.get_datadictionary(datasource_id).data
            fieldmapping = {k: k for k, v in fieldmapping.items()}
            if (include_datetime and datasource.datetime_col is None):
                raise DatetimeNotDefinedError(f"{__name__} filter by datetime is not supported: datetime_col is none")
            if (include_datetime):
                fieldmapping.update({zone_datetime_placeholder: datasource.datetime_col})
            cql_sql = to_sql_where(cql_filter, fieldmapping)
            sql += f"and {cql_sql}"
        try:
            result_df = datasource.conn.sql(sql, params=[zoneIds]).df()
        except Exception as e:
            logger.error(f'{__name__} {datasource_id} query data error: {e}')
            raise Exception(f'{__name__} {datasource_id} query data error: {e}')
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
            logger.error(f'{__name__} {datasource_id} not found.')
            raise Exception(f'{__name__} {datasource_id} not found.')
        if ("*" in datasource.data_cols):
            cols = f"* EXCLUDE({','.join(datasource.exclude_data_cols)})" if (len(datasource.exclude_data_cols) > 0) else "*"
        else:
            cols_intersection = set(datasource.data_cols) - set(datasource.exclude_data_cols)
            cols = f"{','.join(cols_intersection)}, {datasource.id_col}"
        sql = f"""select {cols} from read_parquet('{datasource.filepath}') limit 1"""
        try:
            result_df = datasource.conn.sql(sql).df()
        except Exception as e:
            logger.error(f'{__name__} {datasource_id} query error: {e}')
            raise Exception(f'{__name__} {datasource_id} query error: {e}')
        data = dict(result_df.dtypes)
        for k, v in data.items():
            data[k] = str(v) if (type(v).__name__ != "ObjectDType") else "string"
        result.data = data
        return result
