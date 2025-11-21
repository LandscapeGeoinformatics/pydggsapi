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
from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import Dimension, DimensionGrid
from dataclasses import dataclass
from pygeofilter.ast import AstType
from pygeofilter.backends.sql import to_sql_where
import duckdb
import pandas as pd
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

        # even if 'datetime' was not requested/filtered, it must be reported in dimensions if present for that source
        if datasource.datetime_col is not None:
            cols += f", {datasource.datetime_col}"

        # WARNING: 'zone-order' must remain consistent with the original input to respect DGGS definition
        #   it must NOT be sorted, see Req 24-E (https://docs.ogc.org/DRAFTS/21-038r1.html#_req_data-json_content)
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
            sql += f" AND {cql_sql}"
        try:
            result_df = datasource.conn.sql(sql, params=[zoneIds]).df()
        except Exception as e:
            logger.error(f'{__name__} {datasource_id} query data error: {e}')
            raise Exception(f'{__name__} {datasource_id} query data error: {e}')

        # empty result can be skipped entirely
        if result_df.size == 0:
            return result

        cols_meta = {k: v.name for k, v in dict(result_df.dtypes).items() if k != datasource.id_col}
        cols_dims = None
        zone_dates = None

        # update result with datetime dimension as applicable + zone padding for partial matches
        if datasource.datetime_col:
            # pad any missing values to fill the dimension and sort accordingly along the dimensions for 1D output
            dates = sorted(result_df[datasource.datetime_col].unique())
            cols = [datasource.id_col, datasource.datetime_col]
            grid = pd.MultiIndex.from_product([zoneIds, dates], names=cols).to_frame(index=False)
            result_df = pd.merge(grid, result_df, how='left', on=cols)
            # define metadata for dggs response
            cols_dims = [
                Dimension(
                    name=datasource.datetime_col,
                    interval=[dates[0], dates[-1]],
                    grid=DimensionGrid(
                        cellsCount=len(dates),
                        coordinates=dates,
                    )
                )
            ]
            cols_meta.pop(datasource.datetime_col, None)
            zone_dates = result_df[datasource.datetime_col].astype(str).to_list()
            result_df.drop(datasource.datetime_col, axis=1, inplace=True)  # remove since reported as metadata

        # when no datetime requested, missing zones must still be padded for partial match
        # (notably for zone-depth requests)
        else:
            grid = pd.DataFrame({datasource.id_col: zoneIds})
            result_df = pd.merge(grid, result_df, how='left', on=datasource.id_col)

        result_id = result_df[datasource.id_col].to_list()
        result_df = result_df.drop(datasource.id_col, axis=1)
        result_df = result_df.to_numpy().tolist()
        result.zoneIds, result.cols_meta, result.data = result_id, cols_meta, result_df
        result.datetimes = zone_dates
        result.dimensions = cols_dims
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
