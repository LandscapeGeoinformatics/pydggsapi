from pydggsapi.dependencies.collections_providers.abstract_collection_provider import (
    AbstractCollectionProvider,
    AbstractDatasourceInfo,
    DatetimeNotDefinedError
)
from pydggsapi.schemas.api.collection_providers import (
    CollectionProviderGetDataReturn,
    CollectionProviderGetDataDictReturn
)
from pydggsapi.schemas.api.collections import collection_timestamp_placeholder
from pydggsapi.schemas.ogc_dggs.dggrs_zones import zone_datetime_placeholder
from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import Dimension, DimensionGrid
from dataclasses import dataclass
from datetime import datetime
from pygeofilter.ast import AstType
from pygeofilter.backends.sql import to_sql_where
from ordered_set import OrderedSet
import duckdb
import pandas as pd
import numpy as np
from copy import deepcopy
from typing import List, Any
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

    def get_data(self, zoneIds: List[Any], res: int, datasource_id: str,
                 cql_filter: AstType = None, include_datetime: bool = False,
                 include_properties: List[str] = None,
                 exclude_properties: List[str] = None,
                 input_zoneIds_padding: bool = True,
                 collection_timestamp: datetime = None) -> CollectionProviderGetDataReturn:
        result = CollectionProviderGetDataReturn(zoneIds=[], cols_meta={}, data=[])
        try:
            datasource = self.datasources[datasource_id]
        except KeyError:
            logger.error(f'{__name__} {datasource_id} not found')
            raise Exception(f'{__name__} {datasource_id} not found')
        datetime_col = datasource.datetime_col
        temporal_from_collection_timestamp = False
        # Set the `datetime_col` to the collection_timestamp for temporal query
        # Using `temporal_from_collection_timestamp` to indicate the datetime is comming from collection
        if (include_datetime and datetime_col is None and collection_timestamp is not None):
            datetime_col = collection_timestamp_placeholder
            temporal_from_collection_timestamp = True
        # even if 'datetime' was not requested/filtered, it must be reported in dimensions if present for that source
        # inject the datetime to include_properties
        # caution: since the `collection_timestamp` column doesn't exist, it should not included in the column list.
        if ((datetime_col is not None) and ("*" not in datasource.data_cols) and (not temporal_from_collection_timestamp)):
            if (include_properties is not None):
                include_properties = list(OrderedSet([datetime_col]) | OrderedSet(include_properties))
            else:
                include_properties = [datetime_col]
        if ("*" in datasource.data_cols):
            incl = ",".join(include_properties) if include_properties else "*"
            excl = datasource.exclude_data_cols or []
            excl.extend(exclude_properties or [])
            cols = f"{incl} EXCLUDE({','.join(excl)})" if (len(excl) > 0) else incl
        else:
            incl = OrderedSet(datasource.data_cols) - OrderedSet(datasource.exclude_data_cols)
            if include_properties and include_properties != [datasource.datetime_col]:
                incl = OrderedSet(include_properties) - OrderedSet(datasource.exclude_data_cols)
            elif include_properties:
                incl |= set(include_properties)
            if exclude_properties:
                incl -= set(exclude_properties)
            cols = f"{','.join(incl)}{',' if incl else ''}{datasource.id_col}"
        # even if 'datetime' was not requested/filtered, it must be reported in dimensions if present for that source
        # if datasource.datetime_col is not None:
        #    cols += f", {datasource.datetime_col}"

        # WARNING: 'zone-order' must remain consistent with the original input to respect DGGS definition
        #   it must NOT be sorted, see Req 24-E (https://docs.ogc.org/DRAFTS/21-038r1.html#_req_data-json_content)
        sql = f"""select {cols} """
        if (temporal_from_collection_timestamp):
            sql += f""", '{collection_timestamp}'::DATE AS '{datetime_col}' """
        sql += f"""from read_parquet('{datasource.filepath}')
                  where {datasource.id_col} in (SELECT UNNEST(?))"""
        if (cql_filter is not None):
            fieldmapping = self.get_datadictionary(datasource_id).data
            fieldmapping = {k: k for k, v in fieldmapping.items()}
            if (include_datetime and datetime_col is None):
                raise DatetimeNotDefinedError(f"{__name__} filter by datetime is not supported: datetime_col is none")
            if (include_datetime):
                fieldmapping.update({zone_datetime_placeholder: datetime_col})
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
        if (datetime_col):
            if (np.issubdtype(result_df[datetime_col].dtype, np.datetime64)):
                result_df[datetime_col] = np.datetime_as_string(result_df[datetime_col], 'ns', 'UTC')
            # pad any missing values to fill the dimension and sort accordingly along the dimensions for 1D output
            dates = sorted(result_df[datetime_col].unique())
            cols = [datasource.id_col, datetime_col]
            grid = pd.MultiIndex.from_product([zoneIds, dates], names=cols).to_frame(index=False)
            result_df = pd.merge(grid, result_df, how='left', on=cols)
            # define metadata for dggs response
            cols_dims = [
                Dimension(
                    name=datetime_col,
                    interval=[dates[0], dates[-1]],
                    grid=DimensionGrid(
                        cellsCount=len(dates),
                        coordinates=dates,
                    )
                )
            ]
            cols_meta.pop(datetime_col, None)
            zone_dates = result_df[datetime_col].astype(str).to_list()
            result_df.drop(datetime_col, axis=1, inplace=True)  # remove since reported as metadata

        # when no datetime requested, missing zones must still be padded for partial match
        # (notably for zone-depth requests)
        elif (input_zoneIds_padding):
            grid = pd.DataFrame({datasource.id_col: zoneIds})
            result_df = pd.merge(grid, result_df, how='left', on=datasource.id_col)

        result_id = result_df[datasource.id_col].to_list()
        result_df = result_df.drop(datasource.id_col, axis=1)
        result_df = result_df.to_numpy().tolist()
        result.zoneIds, result.cols_meta, result.data = result_id, cols_meta, result_df
        result.datetimes = zone_dates
        result.dimensions = cols_dims
        return result

    def get_datadictionary(self, datasource_id: str, include_zone_id: bool = True) -> CollectionProviderGetDataReturn:
        result = CollectionProviderGetDataDictReturn(data={})
        try:
            datasource = self.datasources[datasource_id]
        except KeyError:
            logger.error(f'{__name__} {datasource_id} not found.')
            raise Exception(f'{__name__} {datasource_id} not found.')
        if ("*" in datasource.data_cols):
            excl = datasource.exclude_data_cols or []
            excl = excl if include_zone_id else excl + [datasource.id_col]
            cols = f"* EXCLUDE({','.join(excl)})" if (excl) else "*"
        else:
            cols_intersection = OrderedSet(datasource.data_cols) - OrderedSet(datasource.exclude_data_cols)
            incl = f"{',' if cols_intersection else ''}{datasource.id_col}" if include_zone_id else ""
            cols = f"{','.join(cols_intersection)}{incl}"
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
