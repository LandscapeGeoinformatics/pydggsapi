from pydggsapi.dependencies.collections_providers.abstract_collection_provider import (
    AbstractCollectionProvider,
    AbstractDatasourceInfo,
    DatetimeNotDefinedError
)
from pydggsapi.schemas.api.collections import collection_timestamp_placeholder
from pydggsapi.schemas.api.collection_providers import CollectionProviderGetDataReturn, CollectionProviderGetDataDictReturn
from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import Dimension, DimensionGrid
from pydggsapi.schemas.ogc_dggs.dggrs_zones import zone_datetime_placeholder

from pygeofilter.ast import AstType
from pygeofilter.backends.sql import to_sql_where
from ordered_set import OrderedSet
import xarray as xr
import xarray_sql as xql
import numpy as np
import pandas as pd
from datetime import datetime
from copy import deepcopy
from typing import List, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger()


@dataclass
class ZarrDatasourceInfo(AbstractDatasourceInfo):
    filepath: str = ""
    filehandle: object = None
    # the column name of the zone ID, if not given,
    # it is assume to be the same with the zarr group name
    id_col: str = ""


# Zarr with Xarray DataTree
class ZarrCollectionProvider(AbstractCollectionProvider):

    def __init__(self, datasources):
        self.datasources = {}
        try:
            for k, v in datasources.items():
                datasource = ZarrDatasourceInfo(**v)
                datasource.filehandle = xr.open_datatree(datasource.filepath, engine="zarr", chunks="auto")
                self.datasources[k] = datasource
        except Exception as e:
            logger.error(f'{__name__} create datasource failed: {e}')
            raise Exception(f'{__name__} create datasource failed: {e}')

    def get_data(self, zoneIds: List[Any], res: int, datasource_id: str,
                 cql_filter: AstType = None, include_datetime: bool = False,
                 include_properties: List[str] = None,
                 exclude_properties: List[str] = None,
                 input_zoneIds_padding: bool = True,
                 collection_timestamp: datetime = None) -> CollectionProviderGetDataReturn:
        result = CollectionProviderGetDataReturn(zoneIds=[], cols_meta={}, data=[])
        # For non-temporal datasources with the collection_timestamp is set
        # The datetime_col is set to `collection_timestamp` to indicate the datetime is comming from collection
        # So create a copy of the DatasourceInfo obj to avoid persistent changes to the object's attribute.
        try:
            datasource = self.datasources[datasource_id]
        except KeyError:
            logger.error(f'{__name__} {datasource_id} not found')
            raise ValueError(f'{__name__} {datasource_id} not found')
        try:
            zone_grp = datasource.zone_groups[str(res)]
        except KeyError as e:
            logger.error(f'{__name__} get zone_grp for resolution {res} failed: {e}')
            return result
        ds = datasource.filehandle[zone_grp].to_dataset().chunk('auto')
        datetime_col = datasource.datetime_col
        # create the temporal dim for non-temporal datasource if collection_timestamp is set
        # only for temporal query (include_datetime == True)
        if (include_datetime and datetime_col is None and collection_timestamp is not None):
            datetime_col = collection_timestamp_placeholder
            ds = ds.expand_dims(datetime_col)
            ds = ds.assign_coords({datetime_col: [collection_timestamp]})
        id_col = datasource.id_col if (datasource.id_col != "") else zone_grp
        # in future, we may consider using xdggs-dggrid4py
        try:
            if (cql_filter is not None):
                fieldmapping = self.get_datadictionary(datasource_id).data
                fieldmapping = {k: k for k, v in fieldmapping.items()}
                if (include_datetime and datetime_col is None):
                    raise DatetimeNotDefinedError(f"{__name__} filter by datetime is not supported: datetime_col is none")
                if (include_datetime):
                    fieldmapping.update({zone_datetime_placeholder: datetime_col})
                cql_sql = to_sql_where(cql_filter, fieldmapping)
                ctx = xql.XarrayContext()
                ctx.from_dataset('ds', ds)
                if ("*" in datasource.data_cols):
                    incl = ",".join(include_properties) if include_properties else "*"
                    excl = datasource.exclude_data_cols or []
                    excl.extend(exclude_properties or [])
                    cols = f"{incl} EXCLUDE({','.join(excl)})" if (len(excl) > 0) else incl
                else:
                    incl = OrderedSet(datasource.data_cols) - OrderedSet(datasource.exclude_data_cols)
                    if include_properties:
                        incl &= set(include_properties)
                    if exclude_properties:
                        incl -= set(exclude_properties)
                    cols = f"{','.join(incl)}, {id_col}"
                sql = f"""select {cols} from ds where ("{id_col}" in ({', '.join(f"'{z}'" for z in zoneIds)})) and ({cql_sql}) """
                zarr_result = xr.Dataset.from_dataframe(ctx.sql(sql).to_pandas().set_index(id_col))
            else:
                cols = OrderedSet(ds.data_vars) if ("*" in datasource.data_cols) else OrderdSet(datasource.data_cols)
                cols = list(cols - OrderedSet(datasource.exclude_data_cols))
                idx_mask = ds[id_col].isin(np.array(zoneIds, dtype=ds[id_col].dtype))
                zarr_result = ds.sel({id_col: idx_mask})
                zarr_result = zarr_result[cols]
        except Exception as e:
            # Zarr will raise exception if nothing matched
            logger.error(f'{__name__} {datasource_id} sel failed: {e}')
            return result
        if (zarr_result[id_col].size == 0):
            return result
        if ('spatial_ref' in list(zarr_result.coords.keys())):
            zarr_result = zarr_result.drop('spatial_ref')
        cols_dims = []
        grid_indexs_value = [zoneIds]
        grid_cols = [id_col]
        cols_meta = {k: v.name for k, v in dict(zarr_result.data_vars.dtypes).items()}
        # follows the datetime handling from parquet provider.
        if (datetime_col):
            cols_meta.pop(datetime_col, None)
            if (datetime_col not in list(zarr_result.coords.keys())):
                zarr_result = zarr_result.assign_coords({datetime_col: zarr_result[datetime_col]})
        # Create the Dimension retrun from coordinates
        for dim_name, dim_value in zarr_result.coords.items():
            if (dim_name != id_col):
                values = np.sort(np.unique(dim_value.values))
                grid_indexs_value.append(values)
                grid_cols.append(dim_name)
                if (dim_name == datasource.datetime_col):
                    values = np.sort(dim_value.values.astype(str).tolist())
                cols_dims.append(Dimension(name=dim_name,
                                           interval=[values[0], values[-1]],
                                           grid=DimensionGrid(cellsCount=len(values), coordinates=values.tolist())
                                           )
                                 )

        grid = pd.MultiIndex.from_product(grid_indexs_value, names=grid_cols).to_frame(index=False)
        # flatten the zarr dataset to pandas dataframe and apply paddding
        zarr_result = zarr_result.to_dataframe().reset_index()
        if (input_zoneIds_padding):
            zarr_result = pd.merge(grid, zarr_result, how='left', on=grid_cols)
        zone_dates = zarr_result[datetime_col].values.astype(str).tolist() if (datetime_col) else None
        zoneIds = zarr_result[id_col].tolist()
        zarr_result = zarr_result.drop(grid_cols, axis=1)
        result.zoneIds, result.cols_meta, result.data = zoneIds, cols_meta, zarr_result.to_numpy().tolist()
        result.dimensions = cols_dims if (len(cols_dims) > 0) else None
        result.datetimes = zone_dates
        return result

    def get_datadictionary(self, datasource_id: str, include_zone_id: bool = True) -> CollectionProviderGetDataDictReturn:
        try:
            datatree = self.datasources[datasource_id]
        except KeyError as e:
            logger.error(f'{__name__} {datasource_id} not found: {e}.')
            raise Exception(f'{__name__} {datasource_id} not found: {e}.')
        datatree = datatree.filehandle[list(datatree.zone_groups.values())[0]]
        data = {i[0]: str(i[1].dtype) for i in datatree.data_vars.items()}
        if include_zone_id:
            data.update({'zone_id': 'string'})
        return CollectionProviderGetDataDictReturn(data=data)
