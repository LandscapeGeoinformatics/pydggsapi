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
from pydggsapi.routers.dggs_api import _get_collection, _get_dggrs_provider, list_dggrs_zones, dggrs_zones_data, _get_dggrs_description
from pydggsapi.routers.dggs_api import _get_collection_provider
from pydggsapi.routers.dggs_api import dggrs_providers as global_dggrs_providers

from starlette.datastructures import MutableHeaders
from urllib.parse import urlparse
import asyncio
import nest_asyncio
import pyproj
import json
import shapely
from shapely.geometry import box, shape
from shapely.ops import transform
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
    dggrs = _get_dggrs_provider(tilesreq.dggrsId)
    collection = collection_info[tilesreq.collectionId]

    bbox, tile = mercator.getWGS84bbox(tilesreq.z, tilesreq.x, tilesreq.y)
    res_info = mercator.get(tile.z)
    tile_width_km = float(res_info["Tile width deg lons"]) / 0.01 * 0.4  # in tile_width_km
    zone_level = dggrs.get_zone_level_by_cls(tile_width_km)
    if (tilesreq.relative_depth != 0):
        zone_level += tilesreq.relative_depth
    clip_bound = box(bbox.left, bbox.bottom, bbox.right, bbox.top)
    clip_bound = shapely.total_bounds(transform(project, clip_bound))
    if zone_level > collection.collection_provider.max_refinement_level:
        zone_level = collection.collection_provider.max_refinement_level
    if zone_level < collection.collection_provider.min_refinement_level:
        zone_level = collection.collection_provider.min_refinement_level

    logger.debug(f'{__name__} zone level:{zone_level}, tile width:{tile_width_km}, bbox:{bbox}')
    zonesReq = ZonesRequest(collectionId=tilesreq.collectionId, dggrsId=tilesreq.dggrsId, zone_level=zone_level,
                            compact_zone=False, bbox=clip_bound)
    collection_provider = _get_collection_provider(collection.collection_provider.providerId)
    zones_id_response = await list_dggrs_zones(req, zonesReq, _get_dggrs_description(tilesreq.dggrsId), dggrs,
                                               collection_info, collection_provider)
    if (type(zones_id_response) is Response):
        content = mapbox_vector_tile.encode({"name": tilesreq.collectionId, "features": []},
                                            quantize_bounds=bbox,
                                            default_options={"transformer": transformer.transform})
        return Response(bytes(content), media_type="application/x-protobuf")
    logger.info(f'{__name__} zones id list length: {len(zones_id_response.zones)}')
    new_header = MutableHeaders(req._headers)
    new_header['accept'] = 'application/geo+json'
    req._headers = new_header
    req.scope.update(headers=req.headers.raw)
    features = []
    tasks = []
    loop = asyncio.get_event_loop()
    for zoneid in zones_id_response.zones:
        zoneinfo = ZoneInfoRequest(zoneId=zoneid, dggrsId=tilesreq.dggrsId, )
        zonedatareq = ZonesDataRequest(collectionId=tilesreq.collectionId, depth="0")
        tasks.append(dggrs_zones_data(req, zoneinfo, zonedatareq,  _get_dggrs_description(tilesreq.dggrsId),
                     dggrs, collection_info, collection_provider))
    tasks = loop.run_until_complete(asyncio.gather(*tasks))
    features = [{'geometry': shapely.from_geojson(json.dumps(i.geometry.__dict__)), 'properties': i.properties}
                for t in tasks if (type(t) is not Response) for i in t.features]
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
    urls += [baseurl + '/{z}/{x}/{y}?' + f'dggrsId={dggrsId}' for dggrsId in conversion_dggrsId]
    if (collection_info.extent is None):
        bbox = [[]]
    elif (collection_info.extent.spatial is None):
        bbox = [[]]
    else:
        bbox = collection_info.extent.spatial.bbox
    return TilesJSON(**{'tilejson': '3.0.0', 'tiles': urls, 'vector_layers': [{'id': collectionId, 'fields': fields}],
                        'bounds': bbox, 'description': collection_info.description, 'name': collectionId})
