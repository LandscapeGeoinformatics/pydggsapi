from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import (
    Property, Schema, Shape, Value, ZonesDataDggsJsonResponse,
    Feature, ZonesDataGeoJson, Dimension, DimensionGrid
)
from pydggsapi.schemas.common_geojson import GeoJSONPolygon, GeoJSONPoint
from pydggsapi.schemas.api.dggrs_providers import DGGRSProviderZonesElement
from pydggsapi.schemas.api.collections import Collection
from pydggsapi.schemas.api.collection_providers import CollectionProviderGetDataReturn

from pydggsapi.models.ogc_dggs.core import get_json_schema_property

from pydggsapi.dependencies.dggrs_providers.abstract_dggrs_provider import AbstractDGGRSProvider
from pydggsapi.dependencies.collections_providers.abstract_collection_provider import AbstractCollectionProvider, DatetimeNotDefinedError
from pydggsapi.dependencies.api.utils import getCQLAttributes

from starlette.requests import Request
from fastapi.responses import FileResponse, Response
from numcodecs import Blosc
from typing import Any, List, Dict, Optional, Union, cast
from scipy.stats import mode
from pygeofilter.ast import AstType
from ordered_set import OrderedSet
import ubjson
import shapely
import tempfile
import numpy as np
import zarr
import xarray as xr
import geopandas as gpd
import pandas as pd
import json
import itertools
import logging

logger = logging.getLogger()


def query_zone_data(
    request: Request,
    zoneId: str | int,
    base_level: int,
    relative_levels: List[int],
    dggrs_desc: DggrsDescription,
    dggrs_provider: AbstractDGGRSProvider,
    collection: Dict[str, Collection],
    collection_provider: Dict[str, AbstractCollectionProvider],
    returntype='application/json',  # DGGS-JSON by default
    returngeometry='zone-region',
    cql_filter: AstType = None,
    include_datetime: bool = False,
    include_properties: Optional[List[str]] = None,
    exclude_properties: Optional[List[str]] = None,
) -> Optional[Union[ZonesDataDggsJsonResponse, ZonesDataGeoJson, FileResponse, Response]]:
    logger.debug(f'{__name__} query zone data {dggrs_desc.id}, zone id: {zoneId}, relative_levels: {relative_levels}, return: {returntype}, geometry: {returngeometry}')
    # generate cell ids, geometry for relative_depth, if the first element of relative_levels equal to base_level
    # skip it, add it manually
    if (base_level == relative_levels[0]):
        result = dggrs_provider.get_relative_zonelevels(zoneId, base_level, relative_levels[1:], returngeometry)
        parent_geometry = None
        if (returngeometry is not None):
            parent = dggrs_provider.zonesinfo([zoneId])
            parent_geometry = [parent.geometry[0]] if (returngeometry == 'zone-region') else [parent.centroids[0]]
        result.relative_zonelevels[base_level] = DGGRSProviderZonesElement(**{'zoneIds': [zoneId], 'geometry': parent_geometry})
    else:
        result = dggrs_provider.get_relative_zonelevels(zoneId, base_level, relative_levels, returngeometry)
    # get data and form a master dataframe (selected providers) for each zone level
    data = {}
    data_type = {}
    nodata_mapping = {}
    zone_level_dims: Dict[int, List[Dimension]] = {}  # per-collection dimensions to manage distinct ones per provider
    cql_attributes = set() if (cql_filter is None) else getCQLAttributes(cql_filter)
    skipped = 0
    for cid, c in collection.items():
        logger.debug(f"{__name__} handling {cid}")
        cp = collection_provider[c.collection_provider.providerId]
        datasource_id = c.collection_provider.datasource_id
        cmin_rf = c.collection_provider.min_refinement_level
        datasource_vars = list(cp.get_datadictionary(datasource_id).data.keys())
        intersection = (set(datasource_vars) & cql_attributes)
        zone_id_repr = c.collection_provider.dggrs_zoneid_repr
        # check if the cql attributes contain inside the datasource columns
        # The datasource of the collection must consist all columns that match with the attributes of the cql filter
        if ((len(cql_attributes) > 0)):
            if ((len(intersection) == 0) or (len(intersection) != len(cql_attributes))):
                skipped += 1
                continue
        convert = True if (c.collection_provider.dggrsId != dggrs_desc.id and
                           c.collection_provider.dggrsId in dggrs_provider.dggrs_conversion) else False

        # Prepare properties inclusion/exclusion taking into account that the names seen from API responses are
        # prefixed by collection ID for multi-collection aggregation. Drop the prefixed collection ID to compare
        # against the actual data, while ignoring properties not addressing that specific collection.
        # These are passed as is afterwards since CQL2 could use different filters than properties to preserve/omit.
        incl_props = [prop.split(".", 1)[-1] for prop in (include_properties or []) if prop.startswith(f"{cid}.")]
        excl_props = [prop.split(".", 1)[-1] for prop in (exclude_properties or []) if prop.startswith(f"{cid}.")]

        # get data for all relative_levels for the currnet datasource
        for z, v in result.relative_zonelevels.items():
            g = [shapely.from_geojson(json.dumps(g.__dict__))for g in v.geometry] if (returngeometry is not None) else None
            converted_z = z
            if (convert):
                # convert the source dggrs ID to the datasource dggrs zoneID.
                # To simplify the zoneId repr handling, we keep all zoneIds in str repr.
                converted = dggrs_provider.convert(v.zoneIds, c.collection_provider.dggrsId)
                tmp = gpd.GeoDataFrame({'vid': v.zoneIds}, geometry=g).set_index('vid')
                # Store the mapping in master pd
                master = pd.DataFrame({'vid': converted.zoneIds, 'zoneId': converted.target_zoneIds}).set_index('vid')
                master = master.join(tmp).reset_index().set_index('zoneId')
                converted_z = converted.target_res[0]

                from pydggsapi.routers.dggs_api import dggrs_providers as global_dggrs_providers
                tmp_dggrs_provider = global_dggrs_providers[c.collection_provider.dggrsId]
            else:
                cf_zoneIds = v.zoneIds
                master = gpd.GeoDataFrame(cf_zoneIds, geometry=g, columns=['zoneId']).set_index('zoneId')
                tmp_dggrs_provider = dggrs_provider

            idx = master.index.values.tolist()
            logger.debug(f"{__name__} {cid} get_data")
            collection_result = CollectionProviderGetDataReturn(zoneIds=[], cols_meta={}, data=[])
            if (converted_z >= cmin_rf):
                try:
                    idx = tmp_dggrs_provider.zone_id_from_textual(idx, zone_id_repr) if (zone_id_repr != 'textual') else idx
                    collection_result = cp.get_data(zoneIds=idx, res=converted_z, datasource_id=datasource_id, cql_filter=cql_filter,
                                                    include_datetime=include_datetime,
                                                    include_properties=incl_props,
                                                    exclude_properties=excl_props,
                                                    collection_timestamp=c.timestamp)
                    if (zone_id_repr != 'textual'):
                        collection_result.zoneIds = tmp_dggrs_provider.zone_id_to_textual(collection_result.zoneIds, zone_id_repr, converted_z)
                except DatetimeNotDefinedError:
                    pass
            logger.debug(f"{__name__} {cid} get_data done")
            # Changed to use MultiIndex for 2D collections (zoneId, datetime)
            if collection_result.zoneIds:
                cols_name = {f'{cid}.{k}': v for k, v in collection_result.cols_meta.items()}
                # data_col_dims.update({(cid, dim.name): dim for dim in collection_result.dimensions or []})
                cp_nodata_mapping = cp.datasources[datasource_id].nodata_mapping
                collection_nodata = {k: cp_nodata_mapping.get("default", np.nan) for k in list(cols_name.keys())}
                collection_nodata_keys = [k.lower() for k in cp_nodata_mapping.keys() if (k != "default")]
                [collection_nodata.update({k: cp_nodata_mapping[v.lower()]})
                 for k, v in cols_name.items() if (v.lower() in collection_nodata_keys)]
                nodata_mapping.update(collection_nodata)
                data_type.update(cols_name)
                id_ = np.array(collection_result.zoneIds).reshape(-1, 1)
                # since different collections will have different datetime_col name, so it is need to convert
                # all different datetime_col name into a standard `datetime` column name
                index = ['zoneId', 'datetime'] if (collection_result.datetimes) else ['zoneId']
                if (collection_result.datetimes):
                    dates = np.array(collection_result.datetimes).reshape(-1, 1)
                    array = np.concatenate([id_, collection_result.data, dates], axis=-1)
                    names = ['zoneId'] + list(cols_name) + ['datetime']
                else:
                    array = np.concatenate([id_, collection_result.data], axis=-1)
                    names = ['zoneId'] + list(cols_name)
                tmp = pd.DataFrame(array, columns=names)
                if (collection_result.datetimes):
                    # align datetime dtype from different collections (string, float)
                    tmp['datetime'] = pd.to_datetime(tmp['datetime'], utc=True)
                tmp.set_index(index, inplace=True)
                master = master.merge(tmp, how='outer', left_index=True, right_index=True)
                pre_numeric_cols = {c: str(dtype).replace('int', 'float') for c, dtype in cols_name.items()}
                post_numeric_cols = {c: str(dtype) for c, dtype in cols_name.items() if 'int' in str(dtype)}
                master = master.astype(pre_numeric_cols)
                for int_col, col_dtype in post_numeric_cols.items():
                    col_dtype = str(col_dtype).capitalize()  # pandas variant that allows nullable
                    master[int_col] = pd.to_numeric(master[int_col], errors='coerce').astype(col_dtype)
                if ('vid' in master.columns):
                    # we have to follow the original index from master, instead of index from the current dataset
                    original_index = master.index.name
                    master.reset_index(inplace=True)
                    if (returngeometry is not None):
                        tmp_geo = master.groupby('vid')['geometry'].last()
                        master.drop(columns=['geometry'], inplace=True)
                    master.drop(columns=['zoneId'], inplace=True)
                    master = master.groupby('vid').agg(lambda x: mode(x)[0])
                    if (returngeometry is not None):
                        master = master.join(tmp_geo)
                    master = master.reset_index().rename(columns={'vid': 'zoneId'})
                    master.set_index(original_index, inplace=True)
                # master = master if (returntype == 'application/geo+json') else master.drop(columns=['geometry'])
                try:
                    data[z] = data[z].merge(master, how='outer', suffixes=[None, cid], left_index=True, right_index=True)
                    data[z] = data[z].drop(columns=[f'geometry{cid}'], errors='ignore') if (returngeometry is not None) else data[z]
                except KeyError:
                    data[z] = master
    if not data:
        return None
    datatree, tmpfile = None, None
    features = []
    id_ = 0
    properties, values = {}, {}
    if (returntype == 'application/zarr+zip'):
        tmpfile = tempfile.mkstemp()
        zipstore = zarr.ZipStore(tmpfile[1], mode='w')
        datatree = xr.DataTree()
        # zarr_root = zarr.group(zipstore)
    for z, d in sorted(data.items()):  # in case of multiple depths, returned them ascending
        zone_level_dims_list = []
        for index_name in d.index.names:
            if (index_name != 'zoneId'):
                dim_values = d.index.get_level_values(index_name).values.astype(str)
                sorted_unique_dim_values = np.sort(np.unique(dim_values))
                zone_level_dims_list.append(Dimension(name=index_name, interval=[sorted_unique_dim_values[0], sorted_unique_dim_values[-1]],
                                            grid=DimensionGrid(cellsCount=len(dim_values), coordinates=dim_values.tolist())))
                zone_level_dims.update({z: zone_level_dims_list})
        if (returntype == 'application/geo+json'):
            d.reset_index(inplace=True)
            geometry = d['geometry'].values
            geojson = GeoJSONPolygon if (returngeometry == 'zone-region') else GeoJSONPoint
            d = d.drop(columns='geometry')
            d['depth'] = z - base_level
            feature = d.to_dict(orient='records')
            feature = [
                Feature(
                    type="Feature",
                    id=id_ + i,
                    geometry=geojson(**shapely.geometry.mapping(geometry[i])),
                    properties=f,
                )
                for i, f in enumerate(feature)
                # skip features with all-nan column properties, excluding datetime and zone ID/depth details
                if all([pd.notna(v) for k, v in f.items() if k in data_type.keys()])
            ]
            features += feature
            id_ += len(d)
            logger.debug(f'{__name__} query zone data {dggrs_desc.id}, zone id: {zoneId}@{z}, geo+json features len: {len(features)}')
        else:
            # For temporal df, it is a multi-index with (zoneId, datetime)
            zoneIds = d.index.get_level_values('zoneId').astype(str).tolist()
            zone_datetimes = None
            if ("datetime" in d.index.names):
                zone_datetimes = d.index.get_level_values('datetime').values
            d = d.T
            nan_mask = d.isna()
            v = d.values
            if v[nan_mask].size > 0:
                v[nan_mask] = np.nan
            diff = OrderedSet(list(d.index)) - OrderedSet(list(properties.keys()))
            properties.update({c: get_json_schema_property(data_type[c]) for c in diff})
            diff = OrderedSet(list(d.index)) - OrderedSet(list(values.keys()))
            values.update({c: [] for c in diff})
            sub_zones_count = len(set(zoneIds))
            # data_dims is responsible for the dimension of dggs json return
            data_dims = {dim.name: dim.grid.cellsCount for dim in zone_level_dims[z]} if (len(zone_level_dims.keys()) > 0) else {}
            # coords is responsible for the coordinates of zarr return
            coords = {"zoneId": np.unique(zoneIds), "datetime": zone_datetimes} if (zone_datetimes is not None) else {"zoneId": zoneIds}
            for i, column in enumerate(d.index):
                if (datatree is not None):
                    if (f"/zone_level_{z}" not in datatree.groups):
                        # create a datatree for the zone level if not exists
                        zone_ds = xr.Dataset(coords=coords)
                    else:
                        zone_ds = datatree[f"zone_level_{z}"].to_dataset()
                    # FIXME: if 'data_dims' exist, need to create dimension arrays...
                    # The dimension is handled by the variable coords for zarr return
                    export_data = v[i, :]
                    export_data[pd.isna(export_data)] = nodata_mapping[column]
                    export_data = export_data.astype(data_type[column].lower())
                    if (zone_datetimes is not None):
                        export_data = export_data.reshape(len(coords["zoneId"]), len(coords["datetime"]))
                    zone_ds.update({column: (tuple(coords.keys()), export_data)})
                    datatree = datatree.assign({f"zone_level_{z}": xr.DataTree(zone_ds)})
                else:  # DGGS-(UB)JSON
                    data_count = len(v[i, :])
                    values[column].append(Value(
                        depth=z - base_level,
                        shape=Shape(count=data_count, subZones=sub_zones_count, dimensions=data_dims),
                        data=v[i, :].tolist(),
                    ))
    if (datatree is not None):
        compressor = Blosc(cname='zstd', clevel=3, shuffle=Blosc.BITSHUFFLE)
        encode = {}
        for zone in datatree.groups:
            if (len(datatree[zone].data_vars) > 0):
                zone_encoder = {k: {'compressor': compressor} for k in datatree[zone].data_vars.keys()}
                encode[zone] = zone_encoder
        datatree.to_zarr(zipstore, encoding=encode)
        zipstore.close()
        return FileResponse(tmpfile[1], headers={'content-type': 'application/zarr+zip'})
    if (returntype == 'application/geo+json'):
        return ZonesDataGeoJson(type='FeatureCollection', features=features)
    col_schema_id = None
    if len(collection) == 1:  # no schema applicable if the response is a multi-collection aggregation
        col_id = list(collection.keys())[0]
        col_data_url = request.url.replace(query=None, fragment=None)
        col_desc_url = str(col_data_url).rsplit(f'/{col_id}/', 1)[0]
        col_schema_id = f"{col_desc_url}/{col_id}/schema"
    dggrs_link = [k.href for k in dggrs_desc.links if (k.rel == '[ogc-rel:dggrs-definition]')][0]
    relative_levels = [rl - base_level for rl in relative_levels]
    return_ = cast(ZonesDataDggsJsonResponse | Dict[str, Any], {
        'dggrs': dggrs_link,
        'zoneId': str(zoneId),
        'depths': relative_levels,
        'schema': Schema(properties=properties, id_=col_schema_id),
        'values': values,
    })
    if zone_level_dims:
        # temporary fix the issue https://github.com/LandscapeGeoinformatics/pydggsapi/issues/65#issuecomment-3618504418
        # by just return the deepest zone depth dimension
        deepest_zone_level = sorted(list(zone_level_dims.keys()))[-1]
        return_['dimensions'] = zone_level_dims[deepest_zone_level]
    dggs_json = ZonesDataDggsJsonResponse(**return_)
    if (returntype == 'application/ubjson'):
        dggs_ubjson = ubjson.dumpb(dggs_json.model_dump(mode='json'), no_float32=False)
        return Response(dggs_ubjson, headers={
            'content-type': 'application/ubjson',
            'content-disposition': 'attachment; name="dggs-zone-data"; filename="dggs-zone-data.ubjson"',
        })
    return dggs_json
