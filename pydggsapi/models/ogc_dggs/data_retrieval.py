from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import Property, Value, ZonesDataDggsJsonResponse, Feature, ZonesDataGeoJson
from pydggsapi.schemas.common_geojson import GeoJSONPolygon, GeoJSONPoint
from pydggsapi.schemas.api.dggrs_providers import DGGRSProviderZonesElement
from pydggsapi.schemas.api.collections import Collection
from pydggsapi.schemas.api.collection_providers import CollectionProviderGetDataReturn


from pydggsapi.dependencies.dggrs_providers.abstract_dggrs_provider import AbstractDGGRSProvider
from pydggsapi.dependencies.collections_providers.abstract_collection_provider import AbstractCollectionProvider, DatetimeNotDefinedError
from pydggsapi.dependencies.api.utils import getCQLAttributes

from fastapi.responses import FileResponse
from urllib import parse
from numcodecs import Blosc
from typing import List, Dict, Optional, Union
from scipy.stats import mode
from pygeofilter.ast import AstType
import shapely
import tempfile
import numpy as np
import zarr
import geopandas as gpd
import pandas as pd
import json
import logging

logger = logging.getLogger()

def query_zone_data(
    zoneId: str | int,
    base_level: int,
    relative_levels: List[int],
    dggrs_desc: DggrsDescription,
    dggrs_provider: AbstractDGGRSProvider,
    collection: Dict[str, Collection],
    collection_provider: List[AbstractCollectionProvider],
    returntype='application/dggs-json',
    returngeometry='zone-region',
    cql_filter: AstType = None,
    include_datetime: bool = False,
    include_properties: Optional[List[str]] = None,
    exclude_properties: Optional[List[str]] = None,
) -> Optional[Union[ZonesDataDggsJsonResponse, ZonesDataGeoJson, FileResponse]]:
    logger.debug(f'{__name__} query zone data {dggrs_desc.id}, zone id: {zoneId}, relative_levels: {relative_levels}, return: {returntype}, geometry: {returngeometry}')
    # generate cell ids, geometry for relative_depth, if the first element of relative_levels equal to base_level
    # skip it, add it manually
    if (base_level == relative_levels[0]):
        result = dggrs_provider.get_relative_zonelevels(zoneId, base_level, relative_levels[1:], returngeometry)
        parent = dggrs_provider.zonesinfo([zoneId])
        g = parent.geometry[0] if (returngeometry == 'zone-region') else parent.centroids[0]
        result.relative_zonelevels[base_level] = DGGRSProviderZonesElement(**{'zoneIds': [zoneId], 'geometry': [g]})
    else:
        result = dggrs_provider.get_relative_zonelevels(zoneId, base_level, relative_levels, returngeometry)
    # get data and form a master dataframe (seleceted providers) for each zone level
    data = {}
    data_type = {}
    data_col_dims = {}
    cql_attributes = set() if (cql_filter is None) else getCQLAttributes(cql_filter)
    skipped = 0
    for cid, c in collection.items():
        logger.debug(f"{__name__} handling {cid}")
        cp = collection_provider[c.collection_provider.providerId]
        datasource_id = c.collection_provider.datasource_id
        cmin_rf = c.collection_provider.min_refinement_level
        datasource_vars = list(cp.get_datadictionary(datasource_id).data.keys())
        intersection = (set(datasource_vars) & cql_attributes)
        # check if the cql attributes contain inside the datasource
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
            g = [shapely.from_geojson(json.dumps(g.__dict__))for g in v.geometry]
            converted_z = z
            if (convert):
                # convert the source dggrs ID to the datasource dggrs zoneID
                converted = dggrs_provider.convert(v.zoneIds, c.collection_provider.dggrsId)
                tmp = gpd.GeoDataFrame({'vid': v.zoneIds}, geometry=g).set_index('vid')
                # Store the mapping in master pd
                master = pd.DataFrame({'vid': converted.zoneIds, 'zoneId': converted.target_zoneIds}).set_index('vid')
                master = master.join(tmp).reset_index().set_index('zoneId')
                converted_z = converted.target_res[0]
            else:
                cf_zoneIds = v.zoneIds
                master = gpd.GeoDataFrame(cf_zoneIds, geometry=g, columns=['zoneId']).set_index('zoneId')
            idx = master.index.values.tolist()
            logger.debug(f"{__name__} {cid} get_data")
            collection_result = CollectionProviderGetDataReturn(zoneIds=[], cols_meta={}, data=[])
            if (converted_z >= cmin_rf):
                try:
                    collection_result = cp.get_data(
                        idx, converted_z, datasource_id, cql_filter, include_datetime, incl_props, excl_props
                    )
                except DatetimeNotDefinedError:
                    pass
            logger.debug(f"{__name__} {cid} get_data done")
            if (len(collection_result.zoneIds) > 0):
                cols_name = {f'{cid}.{k}': v for k, v in collection_result.cols_meta.items()}
                data_type.update(cols_name)
                id_ = np.array(collection_result.zoneIds).reshape(-1, 1)
                tmp = pd.DataFrame(np.concatenate([id_, collection_result.data], axis=-1),
                                   columns=['zoneId'] + list(cols_name.keys())).set_index('zoneId')
                master = master.join(tmp)
                pre_numeric_cols = {c: str(dtype).replace("int", "float") for c, dtype in cols_name.items()}
                master = master.astype(pre_numeric_cols).astype(cols_name)
                if ('vid' in master.columns):
                    master.reset_index(inplace=True)
                    tmp_geo = master.groupby('vid')['geometry'].last()
                    master.drop(columns=['zoneId', 'geometry'], inplace=True)
                    master = master.groupby('vid').agg(lambda x: mode(x)[0])
                    master = master.join(tmp_geo).reset_index().rename(columns={'vid': 'zoneId'})
                    master.set_index('zoneId', inplace=True)
                master = master if (returntype == 'application/geo+json') else master.drop(columns=['geometry'])
                try:
                    data[z] = data[z].join(master, rsuffix=cid)
                    data[z] = data[z].drop(columns=[f'geometry{cid}'], errors='ignore')
                except KeyError:
                    data[z] = master
                if 'dimensions' in collection_result.cols_meta:
                    data_col_dims.update(collection_result.cols_meta['dimensions'])
                if include_datetime:
                    data_col_dims.update()
                sub_zones = len(idx)
    if (len(data.keys()) == 0):
        return None
    zarr_root, tmpfile = None, None
    features = []
    id_ = 0
    properties, values = {}, {}
    if (returntype == 'application/zarr+zip'):
        tmpfile = tempfile.mkstemp()
        zipstore = zarr.ZipStore(tmpfile[1], mode='w')
        zarr_root = zarr.group(zipstore)

    for z, d in data.items():
        if (returntype == 'application/geo+json'):
            d.reset_index(inplace=True)
            geometry = d['geometry'].values
            geojson = GeoJSONPolygon if (returngeometry == 'zone-region') else GeoJSONPoint
            d = d.drop(columns='geometry')
            d['depth'] = z - base_level
            feature = d.to_dict(orient='records')
            feature = [Feature(**{'type': "Feature", 'id': id_ + i, 'geometry': geojson(**shapely.geometry.mapping(geometry[i])), 'properties': f}) for i, f in enumerate(feature)]
            features += feature
            id_ += len(d)
            logger.debug(f'{__name__} query zone data {dggrs_desc.id}, zone id: {zoneId}@{z}, geo+json features len: {len(features)}')
        else:
            zoneIds = d.index.values.astype(str).tolist()
            d = d.T
            nan_mask = d.isna()
            v = d.values
            if v[nan_mask].size > 0:
                v[nan_mask] = np.nan
            diff = set(list(d.index)) - set(list(properties.keys()))
            properties.update({c: Property(**{'type': data_type[c]}) for c in diff})
            diff = set(list(d.index)) - set(list(values.keys()))
            values.update({c: [] for c in diff})
            for i, column in enumerate(d.index):
                values[column].append(Value(**{'depth': z - base_level, 'shape': {'count': len(v[i, :])}, "data": v[i, :].tolist()}))
                if (zarr_root is not None):
                    root = zarr_root
                    if (f'zone_level_{z}' not in zarr_root.group_keys()):
                        root = zarr_root.create_group(f'zone_level_{z}')
                    else:
                        root = zarr_root[f'zone_level_{z}']
                    compressor = Blosc(cname='zstd', clevel=3, shuffle=Blosc.BITSHUFFLE)
                    if ('zoneId' not in root.array_keys()):
                        sub_zarr = root.create_dataset('zoneId', data=zoneIds, compressor=compressor)
                        sub_zarr.attrs.update({'_ARRAY_DIMENSIONS': ["zoneId"]})
                    sub_zarr = root.create_dataset(f'{column}_zone_level_' + str(z), data=v[i, :].astype(data_type[column].lower()), compressor=compressor)
                    sub_zarr.attrs.update({'_ARRAY_DIMENSIONS': ["zoneId"]})
    if (zarr_root is not None):
        zarr_root.attrs.update({k: v.__dict__ for k, v in properties.items()})
        zarr.consolidate_metadata(zipstore)
        zipstore.close()
        return FileResponse(tmpfile[1], headers={'content-type': 'application/zarr+zip'})
    if (returntype == 'application/geo+json'):
        return ZonesDataGeoJson(**{'type': 'FeatureCollection', 'features': features})
    link = [k.href for k in dggrs_desc.links if (k.rel == '[ogc-rel:dggrs-definition]')][0]
    relative_levels if (base_level == relative_levels[0]) else relative_levels[1:]
    relative_levels = [rl - base_level for rl in relative_levels]
    return_ = {'dggrs': link, 'zoneId': str(zoneId), 'depths': relative_levels,
               'properties': properties, 'values': values}
    if data_col_dims:
        return_['dimensions'] = [{'name': dim, **dim_info} for dim, dim_info in data_col_dims.items()]
    return ZonesDataDggsJsonResponse(**return_)
