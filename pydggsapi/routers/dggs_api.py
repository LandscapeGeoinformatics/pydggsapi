# here should be all OGC DGGS API related routes
# they should all live under e.g. /dggs-api/v1-pre
# that means this module export a FastAPI router that gets mounted
# in the main api.py under /dggs-api/v1-pre

from fastapi import APIRouter, HTTPException, Depends, Request, Path, Query
from typing import Annotated, Optional, Dict, Union

from pydggsapi.schemas.ogc_dggs.dggrs_list import DggrsListResponse
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescriptionRequest, DggrsDescription
from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoRequest, ZoneInfoResponse
from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import ZonesDataRequest, ZonesDataDggsJsonResponse, ZonesDataGeoJson, support_returntype
from pydggsapi.schemas.ogc_dggs.dggrs_zones import ZonesRequest, ZonesResponse, ZonesGeoJson, zone_query_support_returntype
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import LandingPageResponse, Link
from pydggsapi.schemas.api.collections import Collection
from pydggsapi.schemas.ogc_collections.collections import CollectionDesc as ogc_CollectionDesc
from pydggsapi.schemas.ogc_collections.collections import Collections as ogc_Collections
from pydggsapi.schemas.ogc_collections.collections import CollectionDesc
from pydggsapi.schemas.ogc_collections.queryables import CollectionQueryables
from pydggsapi.schemas.ogc_collections.queryables import Properties as QueryablesProperties


from pydggsapi.models.ogc_dggs.core import query_support_dggs, query_dggrs_definition, query_zone_info, landingpage
from pydggsapi.models.ogc_dggs.data_retrieval import query_zone_data
from pydggsapi.models.ogc_dggs.zone_query import query_zones_list

from pydggsapi.dependencies.api.collections import get_collections_info
from pydggsapi.dependencies.api.collection_providers import get_collection_providers
from pydggsapi.dependencies.api.dggrs import get_dggrs_descriptions, get_dggrs_class, get_conformance_classes

from pydggsapi.dependencies.dggrs_providers.abstract_dggrs_provider import AbstractDGGRSProvider
from pydggsapi.dependencies.collections_providers.abstract_collection_provider import AbstractCollectionProvider

from fastapi.responses import JSONResponse, FileResponse, Response
import logging
import copy
import pyproj
import importlib
import traceback
from shapely.geometry import box
from shapely.ops import transform

logger = logging.getLogger()
router = APIRouter()

dggrs, dggrs_providers, collections, collection_providers = {}, {}, {}, {}


def _import_dggrs_class(dggrsId):
    try:
        classname, initial_params = get_dggrs_class(dggrsId)
        if (classname is None):
            logger.error(f'{__name__} {dggrsId} class not found.')
            raise Exception(f'{__name__} {dggrsId} class not found.')
    except Exception as e:
        logger.error(f'{__name__} {e}')
        raise HTTPException(status_code=500, detail=f'{__name__} {e}')
    try:
        module, classname = classname.split('.') if (len(classname.split('.')) == 2) else (classname, classname)
        cls_ = getattr(importlib.import_module(f'pydggsapi.dependencies.dggrs_providers.{module}'), classname)
        return cls_(**initial_params)
    except Exception as e:
        logger.error(f'{__name__} {dggrsId} class: {classname} not imported, {e}')
        raise Exception(f'{__name__} {dggrsId} class: {classname} not imported, {e}')


def _import_collection_provider(providerConfig: dict):
    try:
        classname = providerConfig.classname
        module, classname = classname.split('.') if (len(classname.split('.')) == 2) else (classname, classname)
        cls_ = getattr(importlib.import_module(f'pydggsapi.dependencies.collections_providers.{module}'), classname)
        return cls_(providerConfig.datasources)
    except Exception as e:
        logger.error(f'{__name__} {providerConfig.classname} import failed, {e}')
        raise Exception(f'{__name__} {providerConfig.classname} import failed, {e}')


def _get_dggrs_provider(dggrsId):
    global dggrs_providers
    try:
        return dggrs_providers[dggrsId]
    except KeyError:
        logger.error(f'{__name__} _get_dggrs_provider: {dggrsId} not found in dggrs providers')
        raise HTTPException(status_code=500, detail=f'{__name__} _get_dggrs_provider: {dggrsId} not found in dggrs providers')


def _get_collection_provider(providerId=None):
    global collection_providers
    if (providerId is None):
        return collection_providers
    try:
        return {providerId: collection_providers[providerId]}
    except KeyError:
        logger.error(f'{__name__} _get_collection_provider: {providerId} not found in collection providers')
        raise HTTPException(status_code=500, detail=f'{__name__} _get_collection_provider: {providerId} not found in collection providers')


def _get_dggrs_description(dggrsId: str = Path(...)):
    global dggrs
    try:
        return dggrs[dggrsId]
    except KeyError as e:
        logger.error(f'{__name__} {dggrsId} not supported : {e}')
        raise HTTPException(status_code=400, detail=f'{__name__}  _get_dggrs_description failed:  {dggrsId} not supported: {e}')


def _get_collection(collectionId=None, dggrsId=None):
    global collections, dggrs_providers
    if (collectionId is None):
        return collections
    try:
        c = {collectionId: collections[collectionId]}
    except KeyError:
        logger.error(f'{__name__} : {collectionId} not found')
        raise HTTPException(status_code=400, detail=f'{__name__}  _get_collection failed: {collectionId} not found')
    collection_dggrs = c[collectionId].collection_provider.dggrsId
    if (dggrsId is not None):
        _get_dggrs_description(dggrsId)
        if (collection_dggrs != dggrsId):
            if (collection_dggrs not in dggrs_providers[dggrsId].dggrs_conversion):
                raise HTTPException(status_code=400, detail=f"{__name__} _get_collection failed: collection don't support {dggrsId}.")
    return c


def _get_return_type(req: Request, support_returntype, default_return='application/json'):
    returntypes = req.headers.get('accept').lower() if (req.headers.get('accept') is not None) else default_return
    returntypes = returntypes.split(',')
    intersection = [i for i in returntypes if i in support_returntype]
    returntype = intersection[0] if (len(intersection) > 0) else default_return
    return returntype


# API Initialization checking and setup.
try:
    dggrs = get_dggrs_descriptions()
    collections = get_collections_info()
    collection_providers = get_collection_providers()
except Exception as e:
    logger.error(f'{__name__} {e}')
    raise Exception(f'{__name__} {e}')

# check if dggrs and collection providerID defined in collections are exists
c1 = set([v.collection_provider.dggrsId for k, v in collections.items()]) <= set(dggrs.keys())
c2 = set([v.collection_provider.providerId for k, v in collections.items()]) <= set(collection_providers.keys())
if (c1 is False or c2 is False):
    logger.error(f'{__name__} collection_provider: either collection providerId or dggrsId not exists ')
    raise Exception(f'{__name__} collection_provider: either collection providerId or dggrsId not exists ')

for dggrsId in dggrs.keys():
    dggrs_providers[dggrsId] = _import_dggrs_class(dggrsId)

for providerId, providerConfig in collection_providers.items():
    collection_providers[providerId] = _import_collection_provider(providerConfig)




# Landing page and conformance
@router.get(
    "/",
    tags=['ogc-dggs-api'],
    response_model=LandingPageResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def landing_page(req: Request):
    return landingpage(req.url, req.app)


@router.get("/collections", tags=['ogc-dggs-api'])
async def list_collections(req: Request, response_model=ogc_Collections):
    collectionsResponse = ogc_Collections(
        links=[
            Link(
                href=f"{req.url}",
                rel="self",
                type="application/json",
                title="this document"
            )
        ],
        collections=[]
    )
    try:
        collections_info = _get_collection()
        # logger.info(f'{collections_info.keys()}')
        for collectionId, collection in collections_info.items():
            # logger.info(f'{dir(collection)}')
            collection_links = [
                Link(
                    href=f"{req.url}/{collectionId}",
                    rel="self",
                    type="application/json",
                    title="this document"
                ),
                Link(
                    href=f"{req.url}/{collectionId}/dggs",
                    rel="[ogc-rel:dggrs-list]",
                    type="application/json",
                    title="DGGS list"
                )
            ]
            collection.links = collection_links
            collection.__class__ = ogc_CollectionDesc
            collectionsResponse.collections.append(collection)
    except Exception as e:
        logger.error(f'{__name__} {e}')
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f'{__name__} {e}')

    # return JSONResponse(content=collectionsResponse)
    return collectionsResponse


@router.get("/collections/{collectionId}", tags=['ogc-dggs-api'])
async def list_collection_by_id(collectionId: str, req: Request, response_model=ogc_CollectionDesc):

    collections_info = _get_collection()
    # logger.info(f'{collections_info.keys()}')
    if collectionId in collections_info.keys():
        collection = collections_info[collectionId]
        collection_links = [
            Link(
                href=f"{req.url}",
                rel="self",
                type="application/json",
                title="this document"
            ),
            Link(
                href=f"{req.url}/dggs",
                rel="[ogc-rel:dggrs-list]",
                type="application/json",
                title="DGGS list"
            )
        ]
        collection.links = collection_links
        collection.__class__ = ogc_CollectionDesc

        return collection
    else:
        raise HTTPException(status_code=404, detail=f'{__name__} {collectionId} not found')


@router.get("/collections/{collectionId}/queryables", tags=['ogc-dggs-api'])
async def get_collection_queryables(req: Request, collection: Dict[str, Collection] = Depends(_get_collection),
                                    response_model=CollectionQueryables):
    _, collection = collection.popitem()
    if (collection is None):
        # Error, should not be None, it should be handled by _get_collection
        raise HTTPException(status_code=404, detail=f'{__name__} collection is None')

    collection_provider = _get_collection_provider(collection.collection_provider.providerId)
    _, collection_provider = collection_provider.popitem()
    if (collection_provider is None):
        # Error, should not be None, it should be handled by _get_collection_provider
        raise HTTPException(status_code=404, detail=f'{__name__} {collection.collection_provider.providerId} not found')
    fields = collection_provider.get_datadictionary(collection.collection_provider.datasource_id).data
    items = [QueryablesProperties(id=k, type=v) for k, v in fields.items()]
    return CollectionQueryables(queryables=items)


@router.get("/conformance", tags=['ogc-dggs-api'])
async def conformance(conformance_classes=Depends(get_conformance_classes)):
    return JSONResponse(content={'conformsTo': conformance_classes})


# Core conformance class

# dggrs-list
@router.get("/dggs", response_model=DggrsListResponse, tags=['ogc-dggs-api'])
@router.get("/collections/{collectionId}/dggs", response_model=DggrsListResponse, tags=['ogc-dggs-api'])
async def support_dggs(req: Request, collectionId: Optional[str] = None,
                       collection: Dict[str, Collection] = Depends(_get_collection)):
    logger.info(f'{__name__} called.')
    global dggrs, dggrs_providers
    selected_dggrs = copy.deepcopy(dggrs)
    try:
        if (collectionId is not None):
            collection = collection[collectionId]
            dggrsId = collection.collection_provider.dggrsId
            selected_dggrs = {dggrsId: selected_dggrs[dggrsId]}
            selected_dggrs[dggrsId].maxRefinementLevel = collection.collection_provider.max_refinement_level
            # find other dggrs provider support for conversion
            for k, v in dggrs_providers.items():
                if (dggrsId in v.dggrs_conversion.keys()):
                    selected_dggrs[k] = dggrs[k]
                    selected_dggrs[k].maxRefinementLevel = collection.collection_provider.max_refinement_level - v.dggrs_conversion[dggrsId].zonelevel_offset
        result = query_support_dggs(req.url, selected_dggrs)
    except Exception as e:
        logger.error(f'{__name__} dggrs-list failed: {e}')
        raise HTTPException(status_code=500, detail=f'{__name__} dggrs-list failed: {e}')
    return result


# dggrs description
@router.get("/dggs/{dggrsId}", response_model=DggrsDescription, tags=['ogc-dggs-api'])
@router.get("/collections/{collectionId}/dggs/{dggrsId}", response_model=DggrsDescription, tags=['ogc-dggs-api'],
            dependencies=[])
async def dggrs_description(req: Request, dggrs_req: DggrsDescriptionRequest = Depends(),
                            dggrs_description: DggrsDescription = Depends(_get_dggrs_description),
                            collection: Dict[str, Collection] = Depends(_get_collection),
                            dggrs_provider=Depends(_get_dggrs_provider)):
    current_url = str(req.url)
    if (dggrs_req.collectionId is not None):
        collection = collection[dggrs_req.collectionId]
        dggrs_description.maxRefinementLevel = collection.collection_provider.max_refinement_level
        # update the maxRefinementLevel if it is belongs to dggrs conversion
        if (dggrs_req.dggrsId != collection.collection_provider.dggrsId
                and dggrs_req.dggrsId in dggrs_provider.dggrs_conversion.keys()):
            dggrs_description.maxRefinementLevel += dggrs_provider.dggrs_conversion[collection.collection_provider.dggrsId].zonelevel_offset
    return query_dggrs_definition(current_url, dggrs_description)


# zone-info
@router.get("/dggs/{dggrsId}/zones/{zoneId}",  response_model=ZoneInfoResponse, tags=['ogc-dggs-api'])
@router.get("/collections/{collectionId}/dggs/{dggrsId}/zones/{zoneId}", response_model=ZoneInfoResponse, tags=['ogc-dggs-api'])
async def dggrs_zone_info(req: Request, zoneinfoReq: ZoneInfoRequest = Depends(),
                          dggrs_descrption: DggrsDescription = Depends(_get_dggrs_description),
                          dggrs_provider: AbstractDGGRSProvider = Depends(_get_dggrs_provider),
                          collection: Dict[str, Collection] = Depends(_get_collection),
                          collection_provider: Dict[str, AbstractCollectionProvider] = Depends(_get_collection_provider)):
    try:
        info = query_zone_info(zoneinfoReq, req.url, dggrs_descrption, dggrs_provider, collection, collection_provider)
    except ValueError as e:
        logger.error(f'{__name__} query zone info fail: {e}')
        raise HTTPException(status_code=400, detail=f'{__name__} query zone info fail: {e}')
    except Exception as e:
        logger.error(f'{__name__} query zone info fail: {e}')
        raise HTTPException(status_code=500, detail=f'{__name__} query zone info fail: {e}')
    if (info is None):
        return Response(status_code=204)
    return info


# Zone query conformance class

@router.get("/dggs/{dggrsId}/zones", response_model=Union[ZonesResponse, ZonesGeoJson], tags=['ogc-dggs-api'])
@router.get("/collections/{collectionId}/dggs/{dggrsId}/zones", response_model=Union[ZonesResponse, ZonesGeoJson], tags=['ogc-dggs-api'])
async def list_dggrs_zones(req: Request, zonesReq: Annotated[ZonesRequest, Depends()],
                           dggrs_description: DggrsDescription = Depends(_get_dggrs_description),
                           dggrs_provider: AbstractDGGRSProvider = Depends(_get_dggrs_provider),
                           collection: Dict[str, Collection] = Depends(_get_collection),
                           collection_provider: Dict[str, AbstractCollectionProvider] = Depends(_get_collection_provider)):

    returntype = _get_return_type(req, zone_query_support_returntype, 'application/json')
    returngeometry = zonesReq.geometry if (zonesReq.geometry is not None) else 'zone-region'
    zone_level = zonesReq.zone_level if (zonesReq.zone_level is not None) else dggrs_description.defaultDepth
    compact_zone = zonesReq.compact_zone if (zonesReq.compact_zone is not None) else True
    limit = zonesReq.limit if (zonesReq.limit is not None) else 100000
    parent_zone = zonesReq.parent_zone
    bbox = zonesReq.bbox
    include_datetime = True if (zonesReq.datetime is not None) else False
    filter = zonesReq.filter
    # Parameters checking
    if (parent_zone is not None):
        parent_level = dggrs_provider.get_cells_zone_level([parent_zone])[0]
        if (parent_level > zone_level):
            logger.error(f'{__name__} query zones list, parent level({parent_level}) > zone level({zone_level})')
            raise HTTPException(status_code=400, detail=f"query zones list, parent level({parent_level}) > zone level({zone_level})")
    skip_collection = []
    for k, v in collection.items():
        max_ = v.collection_provider.max_refinement_level
        min_ = v.collection_provider.min_refinement_level
        # if the dggrsId is not the primary dggrs supported by the collection.
        if (zonesReq.dggrsId != v.collection_provider.dggrsId
                and zonesReq.dggrsId in dggrs_provider.dggrs_conversion):
            max_ = v.collection_provider.max_refinement_level + dggrs_provider.dggrs_conversion[v.collection_provider.dggrsId].zonelevel_offset
        if (zone_level > max_ or zone_level < min_):
            logger.warning(f'{__name__} query zones list, zone level {zone_level} is not within the collection\'s refinement level: {min_} {max_}')
            skip_collection.append(k)
    [collection.pop(k) for k in skip_collection]
    if (len(collections) == 0):
        raise HTTPException(status_code=400, detail=f"f'{__name__} query zones list, zone level {zone_level} is over refinement for all collections")
    if (bbox is not None):
        try:
            bbox = box(*bbox)
            bbox_crs = zonesReq.bbox_crs if (zonesReq.bbox_crs is not None) else "wgs84"
            if (bbox_crs != 'wgs84'):
                logger.info(f'{__name__} query zones list {zonesReq.dggrsId}, original bbox: {bbox}')
                project = pyproj.Transformer.from_crs(bbox_crs, "wgs84", always_xy=True).transform
                bbox = transform(project, bbox)
                logger.info(f'{__name__} query zones list {zonesReq.dggrsId}, transformed bbox: {bbox}')
        except Exception as e:
            logger.error(f'{__name__} query zones list, bbox converstion failed : {e}')
            raise HTTPException(status_code=400, detail=f"{__name__} query zones list, bbox converstion failed : {e}")
    try:
        result = query_zones_list(bbox, zone_level, limit, dggrs_description, dggrs_provider, collection, collection_provider,
                                  compact_zone, zonesReq.parent_zone, returntype, returngeometry, filter, include_datetime)
        if (result is None):
            return Response(status_code=204)
        return result
    except ValueError as e:
        logger.error(f'{__name__} query zones list failed: {e}')
        raise HTTPException(status_code=400, detail=f'{__name__} query zones list failed: {e}')
    except Exception as e:
        logger.error(f'{__name__} query zones list failed: {e}')
        raise HTTPException(status_code=500, detail=f'{__name__} query zones list failed: {e}')

# Data-retrieval conformance class


@router.get("/dggs/{dggrsId}/zones/{zoneId}/data", response_model=None, tags=['ogc-dggs-api'])
@router.get("/collections/{collectionId}/dggs/{dggrsId}/zones/{zoneId}/data", response_model=None, tags=['ogc-dggs-api'])
async def dggrs_zones_data(req: Request,
                           zonedataReq: Annotated[ZoneInfoRequest, Path()],
                           zonedataQuery: Annotated[ZonesDataRequest, Query()],
                           dggrs_description: DggrsDescription = Depends(_get_dggrs_description),
                           dggrs_provider: AbstractDGGRSProvider = Depends(_get_dggrs_provider),
                           collection: Dict[str, Collection] = Depends(_get_collection),
                           collection_provider: Dict[str, AbstractCollectionProvider] = Depends(_get_collection_provider)) -> ZonesDataDggsJsonResponse | FileResponse:
    returntype = _get_return_type(req, support_returntype, 'application/json')
    zoneId = zonedataReq.zoneId
    depth = zonedataQuery.zone_depth if (zonedataQuery.zone_depth is not None) else [dggrs_description.defaultDepth]
    returngeometry = zonedataQuery.geometry if (zonedataQuery.geometry is not None) else 'zone-region'
    filter = zonedataQuery.filter
    include_datetime = True if (zonedataQuery.datetime is not None) else False
    include_properties = zonedataQuery.properties
    exclude_properties = zonedataQuery.exclude_properties
    # prepare zone levels from zoneId + depth
    # The first element of zone_level will be the zoneId's level, follow by the required relative depth (zoneId's level + d)
    try:
        base_level = dggrs_provider.get_cells_zone_level([zoneId])[0]
    except Exception as e:
        logger.error(f'{__name__} query zone data {zonedataReq.dggrsId}, zone id {zoneId} get zone level error: {e}')
        raise HTTPException(status_code=500, detail=f'{__name__} query zone data {zonedataReq.dggrsId}, zone id {zoneId} get zone level error: {e}')
    relative_levels = [base_level + d for d in depth]
    skip_collection = []
    for k, v in collection.items():
        max_ = v.collection_provider.max_refinement_level
        # if the dggrsId is not the primary dggrs supported by the collection.
        if (zonedataReq.dggrsId != v.collection_provider.dggrsId
                and zonedataReq.dggrsId in dggrs_provider.dggrs_conversion):
            max_ = v.collection_provider.max_refinement_level + dggrs_provider.dggrs_conversion[v.collection_provider.dggrsId].zonelevel_offset
        for z in relative_levels:
            if (z > max_):
                skip_collection.append(k)
                logger.warning(f'{__name__} query zone data {zonedataReq.dggrsId}, zone id {zoneId} with relative depth: {z} not supported')
    [collection.pop(k) for k in skip_collection]
    if (len(collections) == 0):
        raise HTTPException(status_code=400,
                            detail=f"f'{__name__} zone id {zoneId} with relative depth: {depth} is over refinement for all collections")
    try:
        result = query_zone_data(zoneId, base_level, relative_levels, dggrs_description,
                                 dggrs_provider, collection, collection_providers, returntype,
                                 returngeometry, filter, include_datetime, include_properties, exclude_properties)
        if (result is None):
            return Response(status_code=204)
        return result
    except ValueError as e:
        logger.error(f'{__name__} data_retrieval failed: {e}')
        raise HTTPException(status_code=400, detail=f'{__name__} data_retrieval failed: {e}')
    except Exception as e:
        logger.error(f'{__name__} data_retrieval failed: {e}')
        raise HTTPException(status_code=500, detail=f'{__name__} data_retrieval failed: {e}')
