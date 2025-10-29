# here we should separate the routes that are only related to the MVT
# visualisation, the tiles.json, and the actual /x/y/z routes
# I suggest to bundle these under /tiles/ or /tiles-api/ (doesn't need a version, because standard)
from fastapi import APIRouter, Body, HTTPException, Depends, Response, Request
from typing import Annotated


from pydggsapi.schemas.tiles.tiles import TilesRequest, TilesJSON
from pydggsapi.schemas.ogc_dggs.dggrs_zones import ZonesRequest, ZonesResponse
from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoRequest
from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import ZonesDataRequest

from pydggsapi.dependencies.api.mercator import Mercator
from pydggsapi.routers.dggs_api import _get_collection, _get_dggrs_provider
from pydggsapi.routers.dggs_api import _get_collection_provider
from pydggsapi.routers.dggs_api import dggrs_providers as global_dggrs_providers

import nest_asyncio
import pyproj
import json
import shapely
from shapely.geometry import box
from shapely.ops import transform
import geopandas as gpd
import mapbox_vector_tile
import logging
# logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s {%(module)s} [%(funcName)s] %(message)s',
#                    datefmt='%Y-%m-%d,%H:%M:%S', level=logging.INFO)
logger = logging.getLogger()
nest_asyncio.apply()

router = APIRouter()


SRID_LNGLAT = 4326
SRID_SPHERICAL_MERCATOR = 3857
project = pyproj.Transformer.from_crs(SRID_SPHERICAL_MERCATOR, SRID_LNGLAT, always_xy=True).transform
transformer = pyproj.Transformer.from_crs(crs_from=SRID_LNGLAT, crs_to=SRID_SPHERICAL_MERCATOR, always_xy=True)


@router.get("/{collectionId}/{z}/{x}/{y}", tags=['tiles-api'])
async def query_mvt_tiles(req: Request, tilesreq: TilesRequest = Depends(),
                          mercator=Depends(Mercator)):
    logger.debug(f'{__name__} tiles info: {tilesreq.collectionId} {tilesreq.dggrsId} {tilesreq.z} {tilesreq.x} {tilesreq.y}')
    collection_info = _get_collection(tilesreq.collectionId, tilesreq.dggrsId if (tilesreq.dggrsId != '') else None)
    tilesreq.dggrsId = tilesreq.dggrsId if (tilesreq.dggrsId != '') else collection_info[tilesreq.collectionId].collection_provider.dggrsId
    collection = collection_info[tilesreq.collectionId]
    dggrs_provider = _get_dggrs_provider(tilesreq.dggrsId)
    collection = collection_info[tilesreq.collectionId]
    collection_provider = _get_collection_provider(collection.collection_provider.providerId)[collection.collection_provider.providerId]
    ds = collection_provider.datasources[collection.collection_provider.datasource_id]
    id_col = getattr(ds, "id_col", "zone_id")
    bbox, tile = mercator.getWGS84bbox(tilesreq.z, tilesreq.x, tilesreq.y)
    res_info = mercator.get(tile.z)
    tile_width_km = float(res_info["Tile width deg lons"]) / 0.01 * 0.4  # in tile_width_km
    zone_level = dggrs_provider.get_zone_level_by_cls(tile_width_km)
    if (tilesreq.relative_depth != 0):
        zone_level += tilesreq.relative_depth
    clip_bound = box(bbox.left, bbox.bottom, bbox.right, bbox.top)
    clip_bound = transform(project, clip_bound)
    if zone_level > collection.collection_provider.max_refinement_level:
        zone_level = collection.collection_provider.max_refinement_level
    if zone_level < collection.collection_provider.min_refinement_level:
        content = mapbox_vector_tile.encode({"name": tilesreq.collectionId, "features": []},
                                            quantize_bounds=bbox,
                                            default_options={"transformer": transformer.transform})
        return Response(bytes(content), media_type="application/x-protobuf")
    logger.debug(f'{__name__} zone level:{zone_level}, tile width:{tile_width_km}, bbox:{bbox}')
    zoneslist = dggrs_provider.zoneslist(clip_bound, zone_level, parent_zone=None, returngeometry='zone-region', compact=False)
    geometry = [shapely.from_geojson(json.dumps(g.__dict__)) for g in zoneslist.geometry]
    zoneslist = gpd.GeoDataFrame({'zone_id': zoneslist.zones}, geometry=geometry).set_index('zone_id')
    zones_data = collection_provider.get_data(zoneslist.index.to_list(), zone_level, collection.collection_provider.datasource_id)
    if (len(zones_data.zoneIds) == 0):
        content = mapbox_vector_tile.encode({"name": tilesreq.collectionId, "features": []},
                                            quantize_bounds=bbox,
                                            default_options={"transformer": transformer.transform})
        return Response(bytes(content), media_type="application/x-protobuf")
    zones_data = gpd.GeoDataFrame(zones_data.data, index=zones_data.zoneIds, columns=list(zones_data.cols_meta.keys()))
    zones_data = zones_data.join(zoneslist).reset_index(names=id_col)
    geometry = zones_data['geometry'].values
    zones_data = zones_data.drop(columns='geometry')
    features = zones_data.to_dict(orient='records')
    features = [{'geometry': geometry[i], 'properties': f} for i, f in enumerate(features)]
    content = mapbox_vector_tile.encode({"name": tilesreq.collectionId, "features": features},
                                        quantize_bounds=bbox,
                                        default_options={"transformer": transformer.transform})
    return Response(bytes(content), media_type="application/x-protobuf")


@router.get("/{collectionId}.json", tags=['tiles-api'])
async def get_tiles_json(req: Request, collectionId: str):
    logging.debug(f'{__name__} {collectionId} get_tiles_json called')
    collection_info = _get_collection(collectionId=collectionId)[collectionId]
    default_dggrsId = collection_info.collection_provider.dggrsId
    collection_providerId = collection_info.collection_provider.providerId
    conversion_dggrsId = []
    for id_, dggrs_provider in global_dggrs_providers.items():
        if (default_dggrsId in list(dggrs_provider.dggrs_conversion.keys())):
            conversion_dggrsId.append(id_)
    collection_provider = _get_collection_provider(collection_providerId)[collection_providerId]
    fields = collection_provider.get_datadictionary(collection_info.collection_provider.datasource_id).data
    baseurl = str(req.url).replace('.json', '')
    urls = [baseurl + '/{z}/{x}/{y}']
    if (collection_info.extent is None):
        bbox = []
    elif (collection_info.extent.spatial is None):
        bbox = []
    else:
        bbox = collection_info.extent.spatial.bbox[0]
    return TilesJSON(**{'tilejson': '3.0.0', 'tiles': urls, 'vector_layers': [{'id': collectionId, 'fields': fields}],
                        'bounds': bbox, 'description': collection_info.description, 'name': collectionId})
