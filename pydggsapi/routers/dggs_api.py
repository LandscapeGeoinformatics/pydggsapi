# here should be all OGC DGGS API related routes
# they should all live under e.g. /dggs-api/v1-pre
# that means this module export a FastAPI router that gets mounted
# in the main api.py under /dggs-api/v1-pre

from typing import Annotated, Dict, List, Optional, Union
from functools import cache
import logging
import copy
import importlib
import traceback

import pyproj
from fastapi import APIRouter, HTTPException, Depends, Request, Path, Query
from fastapi.responses import JSONResponse, FileResponse, Response
from starlette.datastructures import URL
from shapely.geometry import box
from shapely.ops import transform

from pydggsapi.schemas.api.collections import Collection
from pydggsapi.schemas.api.collection_providers import CollectionProvider
from pydggsapi.schemas.ogc_dggs.dggrs_list import DggrsListResponse
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescriptionRequest, DggrsDescription
from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoRequest, ZoneInfoResponse
from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import (
    ZonesDataRequest,
    ZonesDataDggsJsonResponse,
    ZonesDataGeoJson,
    zone_data_support_formats,
    zone_data_support_returntype,
)
from pydggsapi.schemas.ogc_dggs.dggrs_zones import (
    ZonesRequest,
    ZonesResponse,
    ZonesGeoJson,
    zone_query_support_formats,
    zone_query_support_returntype,
)
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import LandingPageResponse, Link
from pydggsapi.schemas.ogc_collections.collections import CollectionDesc as ogc_CollectionDesc
from pydggsapi.schemas.ogc_collections.collections import Collections as ogc_Collections
from pydggsapi.schemas.ogc_collections.collections import CollectionDesc
from pydggsapi.schemas.ogc_collections.queryables import CollectionQueryables
from pydggsapi.schemas.ogc_collections.schema import JsonSchemaResponse

from pydggsapi.models.ogc_dggs.core import get_queryables, query_support_dggs, query_dggrs_definition, query_zone_info, landingpage
from pydggsapi.models.ogc_dggs.data_retrieval import query_zone_data
from pydggsapi.models.ogc_dggs.zone_query import query_zones_list

from pydggsapi.dependencies.api.collections import get_collections_info
from pydggsapi.dependencies.api.collection_providers import get_collection_providers
from pydggsapi.dependencies.api.dggrs import get_dggrs_descriptions, get_dggrs_class, get_conformance_classes

from pydggsapi.dependencies.dggrs_providers.abstract_dggrs_provider import AbstractDGGRSProvider
from pydggsapi.dependencies.collections_providers.abstract_collection_provider import AbstractCollectionProvider

logger = logging.getLogger()
router = APIRouter()

dggrs: dict[str, DggrsDescription] = {}
dggrs_providers: dict[str, AbstractDGGRSProvider] = {}
collections: dict[str, Collection] = {}
collection_providers: dict[str, AbstractCollectionProvider] = {}

browser_ignore_types = [
    'text/html',
    'text/xml',
    'application/xhtml+xml',
    'application/xml',
    '*/*',
]


def _import_dggrs_class(dggrsId: str, crs: Optional[str] = None) -> AbstractDGGRSProvider:
    try:
        classname, initial_params = get_dggrs_class(dggrsId)
        initial_params.update({"crs": crs})
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


def _import_collection_provider(providerConfig: CollectionProvider) -> AbstractCollectionProvider:
    try:
        classname = providerConfig.classname
        module, classname = classname.split('.') if (len(classname.split('.')) == 2) else (classname, classname)
        cls_ = getattr(importlib.import_module(f'pydggsapi.dependencies.collections_providers.{module}'), classname)
        return cls_(providerConfig.datasources)
    except Exception as e:
        logger.error(f'{__name__} {providerConfig.classname} import failed, {e}')
        raise Exception(f'{__name__} {providerConfig.classname} import failed, {e}')


@cache
def _get_dggrs_provider(dggrsId: str) -> AbstractDGGRSProvider:
    global dggrs_providers
    try:
        return dggrs_providers[dggrsId]
    except KeyError:
        logger.error(f'{__name__} _get_dggrs_provider: {dggrsId} not found in dggrs providers')
        raise HTTPException(status_code=500, detail=f'{__name__} _get_dggrs_provider: {dggrsId} not found in dggrs providers')


@cache
def _get_collection_provider(providerId: Optional[str] = None) -> dict[str, AbstractCollectionProvider]:
    global collection_providers
    if (providerId is None):
        return collection_providers
    try:
        return {providerId: collection_providers[providerId]}
    except KeyError:
        logger.error(f'{__name__} _get_collection_provider: {providerId} not found in collection providers')
        raise HTTPException(status_code=500, detail=f'{__name__} _get_collection_provider: {providerId} not found in collection providers')


@cache
def _get_dggrs_description(dggrsId: str = Path(...)) -> DggrsDescription:
    global dggrs
    try:
        return copy.deepcopy(dggrs[dggrsId])
    except KeyError as e:
        logger.error(f'{__name__} {dggrsId} not supported : {e}')
        raise HTTPException(status_code=400, detail=f'{__name__}  _get_dggrs_description failed:  {dggrsId} not supported: {e}')


@cache
def _get_collection(collectionId: Optional[str] = None, dggrsId: Optional[str] = None) -> dict[str, Collection]:
    global collections, dggrs_providers
    if (collectionId is None):
        return collections.copy()
    try:
        c = {collectionId: copy.deepcopy(collections[collectionId])}
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


def _get_return_type(
    req: Request,
    support_returntype: List[str],
    support_formats: Dict[str, str],
    default_return: str = 'application/json',
) -> str:
    returntypes = req.headers.get('accept').lower() if (req.headers.get('accept') is not None) else ''
    returntypes = [typ.strip() for typ in returntypes.split(',')]
    returntypes_raw = [typ.split(';')[0].strip() for typ in returntypes]
    # if using a browser auto-injecting visualization content-types, allow ignoring them if format is provided
    fmt = req.query_params.get('f')
    if fmt and (returntypes is None or all(typ in browser_ignore_types for typ in returntypes_raw)):
        fmt = str(fmt).lower()
        returntypes = support_formats.get(fmt)  # could still be none if unmapped
        if returntypes is None:
            raise HTTPException(406, detail=f"Requested format '{fmt}' is not supported.")
    if returntypes is None:
        returntypes = default_return
    if isinstance(returntypes, str):
        returntypes = [returntypes]
    returntypes = returntypes + returntypes_raw
    intersection = [i for i in returntypes if i in support_returntype]
    if not intersection:
        if '*/*' in returntypes:
            return default_return
        raise HTTPException(406, detail="Requested content-type is not supported.")
    returntype = intersection[0]
    return returntype


# API Initialization checking and setup.
try:
    dggrs = get_dggrs_descriptions()
    collections = get_collections_info()
    collection_provider_configs = get_collection_providers()
except Exception as e:
    logger.error(f'{__name__} {e}')
    raise Exception(f'{__name__} {e}')

# check if dggrs and collection providerID defined in collections are exists
c1 = set([v.collection_provider.dggrsId for k, v in collections.items()]) <= set(dggrs.keys())
c2 = set([v.collection_provider.providerId for k, v in collections.items()]) <= set(collection_provider_configs.keys())
if (c1 is False or c2 is False):
    logger.error(f'{__name__} collection_provider: either collection providerId or dggrsId not exists ')
    raise Exception(f'{__name__} collection_provider: either collection providerId or dggrsId not exists ')

for dggrsId in dggrs.keys():
    dggrs_providers[dggrsId] = _import_dggrs_class(dggrsId, dggrs[dggrsId].crs)

for providerId, providerConfig in collection_provider_configs.items():
    collection_providers[providerId] = _import_collection_provider(providerConfig)


# Landing page and conformance
@router.get(
    "/",
    tags=['ogc-dggs-api'],
    response_model=LandingPageResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def landing_page(req: Request) -> Union[LandingPageResponse, Response]:
    return landingpage(req.url, req.app)


def describe_collection(collection: Collection, collection_url: Union[str, URL]) -> ogc_CollectionDesc:
    collection_links = [
        Link(
            href=f"{collection_url}",
            rel="self",
            type="application/json",
            title="this document"
        ),
        Link(
            href=f"{collection_url}/dggs",
            rel="[ogc-rel:dggrs-list]",
            type="application/json",
            title="DGGS list"
        ),
        Link(
            href=f"{collection_url}/queryables",
            rel="[ogc-rel:queryables]",
            type="application/schema+json",
            title="Queryable properties from the collection.",
        ),
    ]
    dggrs_provider = _get_dggrs_provider(collection.collection_provider.dggrsId)
    min_rf, max_rf = collection.collection_provider.min_refinement_level, collection.collection_provider.max_refinement_level
    col = ogc_CollectionDesc(**collection.model_dump(exclude={'collection_provider'}))
    col.minScaleDenominator = int((dggrs_provider.get_cls_by_zone_level(max_rf)*1000) / 0.00028)
    col.maxScaleDenominator = int((dggrs_provider.get_cls_by_zone_level(min_rf)*1000) / 0.00028)
    col.links.extend(collection_links)
    return col


@router.get("/collections", tags=['ogc-dggs-api'], response_model=ogc_Collections)
async def list_collections(req: Request) -> Union[ogc_Collections, Response]:
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
            col = describe_collection(collection, f"{req.url}/{collectionId}")
            collectionsResponse.collections.append(col)
        collectionsResponse.numberMatched = len(collectionsResponse.collections)
        collectionsResponse.numberReturned = len(collectionsResponse.collections)
    except Exception as e:
        logger.error(f'{__name__} {e}')
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f'{__name__} {e}')

    return collectionsResponse


@router.get("/collections/{collectionId}", tags=['ogc-dggs-api'], response_model=ogc_CollectionDesc)
async def list_collection_by_id(collectionId: str, req: Request) -> Union[ogc_CollectionDesc, Response]:

    collections_info = _get_collection()
    # logger.info(f'{collections_info.keys()}')
    if collectionId in collections_info.keys():
        collection = collections_info[collectionId]
        col = describe_collection(collection, req.url)
        return col
    else:
        raise HTTPException(status_code=404, detail=f'{__name__} {collectionId} not found')


@router.get(
    "/collections/{collectionId}/queryables",
    tags=['ogc-dggs-api'],
    response_class=JsonSchemaResponse,  # override Content-Type response header
    response_model=None,
)
async def get_collection_queryables_request(
    req: Request,
    collection: Dict[str, Collection] = Depends(_get_collection),
) -> Union[CollectionQueryables, JsonSchemaResponse]:

    _, collection = collection.popitem()
    if (collection is None):
        # Error, should not be None, it should be handled by _get_collection
        raise HTTPException(status_code=404, detail=f'{__name__} collection is None')

    collection_provider = _get_collection_provider(collection.collection_provider.providerId)
    _, collection_provider = collection_provider.popitem()
    if (collection_provider is None):
        # Error, should not be None, it should be handled by _get_collection_provider
        raise HTTPException(status_code=404, detail=f'{__name__} {collection.collection_provider.providerId} not found')
    schema_id = str(req.url).split('?')[0].split('#')[0]  # remove query/fragments if any indicated
    queryables = get_queryables(collection, collection_provider)
    queryables.id_ = schema_id
    return queryables


@router.get("/conformance", tags=['ogc-dggs-api'])
async def conformance(conformance_classes=Depends(get_conformance_classes)) -> JSONResponse:
    return JSONResponse(content={'conformsTo': conformance_classes})


# Core conformance class

# dggrs-list
@router.get("/dggs", response_model=DggrsListResponse, tags=['ogc-dggs-api'])
@router.get("/collections/{collectionId}/dggs", response_model=DggrsListResponse, tags=['ogc-dggs-api'])
async def support_dggs(
    req: Request, collectionId: Optional[str] = None,
    collection: Dict[str, Collection] = Depends(_get_collection),
) -> Union[DggrsListResponse, Response]:

    logger.info(f'{__name__} called.')
    global dggrs, dggrs_providers
    selected_dggrs = copy.deepcopy(dggrs)
    try:
        if (collectionId is not None):
            collection = collection[collectionId]
            dggrsId = collection.collection_provider.dggrsId
            selected_dggrs = {dggrsId: selected_dggrs[dggrsId]}
            ref_max = selected_dggrs[dggrsId].maxRefinementLevel = collection.collection_provider.max_refinement_level
            # find other dggrs provider support for conversion
            for k, v in dggrs_providers.items():
                if (dggrsId in v.dggrs_conversion.keys()):
                    selected_dggrs[k] = dggrs[k]
                    selected_dggrs[k].maxRefinementLevel = ref_max - v.dggrs_conversion[dggrsId].zonelevel_offset
        result = query_support_dggs(req.url, selected_dggrs)
    except Exception as e:
        logger.error(f'{__name__} dggrs-list failed: {e}')
        raise HTTPException(status_code=500, detail=f'{__name__} dggrs-list failed: {e}')
    return result


# dggrs description
@router.get("/dggs/{dggrsId}", response_model=DggrsDescription, tags=['ogc-dggs-api'])
@router.get("/collections/{collectionId}/dggs/{dggrsId}", response_model=DggrsDescription, tags=['ogc-dggs-api'])
async def dggrs_description(
    req: Request, dggrs_req: DggrsDescriptionRequest = Depends(),
    dggrs_description: DggrsDescription = Depends(_get_dggrs_description),
    collection: Dict[str, Collection] = Depends(_get_collection),
    dggrs_provider=Depends(_get_dggrs_provider)
) -> Union[DggrsDescription, Response]:
    dggrs_description = dggrs_description.model_copy(deep=True)
    current_url = str(req.url)
    if (dggrs_req.collectionId is not None):
        collection = collection[dggrs_req.collectionId]
        dggrs_description.maxRefinementLevel = collection.collection_provider.max_refinement_level
        # update the maxRefinementLevel if it belongs to dggrs conversion
        if (dggrs_req.dggrsId != collection.collection_provider.dggrsId
                and dggrs_req.dggrsId in dggrs_provider.dggrs_conversion.keys()):
            dggrs_description.maxRefinementLevel += dggrs_provider.dggrs_conversion[collection.collection_provider.dggrsId].zonelevel_offset
    return query_dggrs_definition(current_url, dggrs_description)


# zone-info
@router.get("/dggs/{dggrsId}/zones/{zoneId}",  response_model=ZoneInfoResponse, tags=['ogc-dggs-api'])
@router.get("/collections/{collectionId}/dggs/{dggrsId}/zones/{zoneId}", response_model=ZoneInfoResponse, tags=['ogc-dggs-api'])
async def dggrs_zone_info(
    req: Request, zoneinfoReq: ZoneInfoRequest = Depends(),
    dggrs_description: DggrsDescription = Depends(_get_dggrs_description),
    dggrs_provider: AbstractDGGRSProvider = Depends(_get_dggrs_provider),
    collection: Dict[str, Collection] = Depends(_get_collection),
    collection_provider: Dict[str, AbstractCollectionProvider] = Depends(_get_collection_provider),
) -> Union[ZoneInfoResponse, Response]:
    try:
        info = query_zone_info(zoneinfoReq, req.url, dggrs_description, dggrs_provider, collection, collection_provider)
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
async def list_dggrs_zones(
    req: Request,
    dggrsDesc: Annotated[DggrsDescriptionRequest, Path()],
    zonesReq: Annotated[ZonesRequest, Query()],
    dggrs_description: DggrsDescription = Depends(_get_dggrs_description),
    dggrs_provider: AbstractDGGRSProvider = Depends(_get_dggrs_provider),
    collection: Dict[str, Collection] = Depends(_get_collection),
    collection_provider: Dict[str, AbstractCollectionProvider] = Depends(_get_collection_provider),
) -> Union[ZonesResponse, ZonesGeoJson, Response]:

    returntype = _get_return_type(req, zone_query_support_returntype, zone_query_support_formats, 'application/json')
    returngeometry = zonesReq.geometry if (zonesReq.geometry is not None) else 'zone-region'
    zone_level = zonesReq.zone_level
    compact_zone = zonesReq.compact_zone if (zonesReq.compact_zone is not None) else True
    limit = zonesReq.limit if (zonesReq.limit is not None) else 100000
    parent_zone = zonesReq.parent_zone
    bbox = zonesReq.bbox
    include_datetime = True if (zonesReq.datetime is not None) else False
    filter = zonesReq.filter
    # Parameters checking
    if (parent_zone is not None):
        parent_level = dggrs_provider.get_cells_zone_level([parent_zone])[0]
        # If the zone-level is not specified, use the parent-zone refinement level + 1 as the zone level value.
        zone_level = zone_level if (zone_level is not None) else parent_level + 1
        if (parent_level >= zone_level):
            logger.error(f'{__name__} query zones list, parent zone refinement level ({parent_level}) is finer or equal to the requested zone-level({zone_level}).')
            raise HTTPException(status_code=400, detail=f"query zones list, parent zone refinement level ({parent_level}) is finer or equal to the requested zone-level({zone_level}).")
    skip_collection = []
    for k, v in collection.items():
        max_ = v.collection_provider.max_refinement_level
        min_ = v.collection_provider.min_refinement_level
        # if the dggrsId is not the native dggrs supported by the collection,
        # check if the native dggrs supports conversion
        if (dggrsDesc.dggrsId != v.collection_provider.dggrsId
                and v.collection_provider.dggrsId not in dggrs_provider.dggrs_conversion):
            skip_collection.append(k)
            continue
        if (dggrsDesc.dggrsId != v.collection_provider.dggrsId
                and v.collection_provider.dggrsId in dggrs_provider.dggrs_conversion):
            max_ = v.collection_provider.max_refinement_level + dggrs_provider.dggrs_conversion[v.collection_provider.dggrsId].zonelevel_offset
        if (zone_level < min_ or zone_level > max_):
            logger.warning(f'{__name__} query zones list, zone level {zone_level} is not within the {k} refinement level: {min_} {max_}')
            skip_collection.append(k)

    if (len(collection) == len(skip_collection)):
        raise HTTPException(status_code=400, detail=f"f'{__name__} query zones list, zone level {zone_level} is over refinement for all collections")
    filtered_collections = {k: v for k, v in collection.items() if (k not in skip_collection)}
    if (bbox is not None):
        try:
            bbox = box(*bbox)
            bbox_crs = zonesReq.bbox_crs if (zonesReq.bbox_crs is not None) else "wgs84"
            if (bbox_crs != 'wgs84'):
                logger.info(f'{__name__} query zones list {dggrsDesc.dggrsId}, original bbox: {bbox}')
                project = pyproj.Transformer.from_crs(bbox_crs, "wgs84", always_xy=True).transform
                bbox = transform(project, bbox)
                logger.info(f'{__name__} query zones list {dggrsDesc.dggrsId}, transformed bbox: {bbox}')
        except Exception as e:
            logger.error(f'{__name__} query zones list, bbox converstion failed : {e}')
            raise HTTPException(status_code=400, detail=f"{__name__} query zones list, bbox converstion failed : {e}")
    try:
        result = query_zones_list(bbox, zone_level, limit, dggrs_description, dggrs_provider, filtered_collections, collection_provider,
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
async def dggrs_zones_data(
    req: Request,
    zonedataReq: Annotated[ZoneInfoRequest, Path()],
    zonedataQuery: Annotated[ZonesDataRequest, Query()],
    dggrs_description: DggrsDescription = Depends(_get_dggrs_description),
    dggrs_provider: AbstractDGGRSProvider = Depends(_get_dggrs_provider),
    collection: Dict[str, Collection] = Depends(_get_collection),
    collection_provider: Dict[str, AbstractCollectionProvider] = Depends(_get_collection_provider),
) -> ZonesDataDggsJsonResponse | FileResponse | Response:
    returntype = _get_return_type(req, zone_data_support_returntype, zone_data_support_formats, 'application/json')
    zoneId = zonedataReq.zoneId
    depth = zonedataQuery.zone_depth if (zonedataQuery.zone_depth is not None) else [dggrs_description.defaultDepth]
    returngeometry = zonedataQuery.geometry if (zonedataQuery.geometry is not None) else 'zone-region'
    returngeometry = None if (returntype != 'application/geo+json') else returngeometry
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
        # if the dggrsId is not the native dggrs supported by the collection,
        # check if the native dggrs supports conversion
        if (zonedataReq.dggrsId != v.collection_provider.dggrsId
                and v.collection_provider.dggrsId not in dggrs_provider.dggrs_conversion):
            skip_collection.append(k)
            continue
        # if the dggrsId is not the primary dggrs supported by the collection.
        if (zonedataReq.dggrsId != v.collection_provider.dggrsId
                and v.collection_provider.dggrsId in dggrs_provider.dggrs_conversion):
            max_ = v.collection_provider.max_refinement_level + dggrs_provider.dggrs_conversion[v.collection_provider.dggrsId].zonelevel_offset
        for z in relative_levels:
            if (z > max_):
                skip_collection.append(k)
                logger.warning(f'{__name__} query zone data {zonedataReq.dggrsId}, zone id {zoneId} with relative depth: {z} not supported')
    if (len(collection) == len(skip_collection)):
        raise HTTPException(status_code=400,
                            detail=f"f'{__name__} zone id {zoneId} with relative depth: {depth} is over refinement for all collections")
    filtered_collections = {k: v for k, v in collection.items() if (k not in skip_collection)}
    try:
        result = query_zone_data(zoneId, base_level, relative_levels, dggrs_description,
                                 dggrs_provider, filtered_collections, collection_providers, returntype,
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
