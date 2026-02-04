# here should be all OGC DGGS API related routes
# they should all live under e.g. /dggs-api/v1-pre
# that means this module export a FastAPI router that gets mounted
# in the main api.py under /dggs-api/v1-pre

from typing import Annotated, Dict, List, Optional, Union, cast
from functools import cache
import logging
import copy
import importlib
import traceback

import pyproj
from fastapi import APIRouter, HTTPException, Depends, Request, Path, Query
from fastapi.params import Param
from fastapi.responses import JSONResponse, FileResponse, Response
from starlette.datastructures import URL
from shapely.geometry import box
from shapely.ops import transform

from pydggsapi.schemas.api.collections import Collection
from pydggsapi.schemas.api.collection_providers import CollectionProvider
from pydggsapi.schemas.ogc_dggs.dggrs_list import DggrsListResponse
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import (
    CollectionDggrsPathRequest,
    CollectionPathRequest,
    DggrsPathRequest,
    DggrsDescription,
)
from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import (
    CollectionZoneInfoPathRequest,
    ZoneInfoPathRequest,
    ZoneInfoResponse,
)
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
    zone_datetime_placeholder
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
from pydggsapi.dependencies.api.utils import getCQLAttributes

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


# WARNING: FastAPI dependencies limitation / workaround
#   only 1 nested-model 'Query' is supported, adding more than one 'Annotated[]'
#   makes all queries to fail OpenAPI rendering, as they are detected as distinct 'Body'
#   as described in https://fastapi.tiangolo.com/tutorial/body-multiple-params/
#
#   Planned support of multiple non-Body models:
#   - https://github.com/fastapi/fastapi/issues/11037#issuecomment-3637254759
#   - https://github.com/fastapi/fastapi/pull/12944
#   - https://github.com/fastapi/fastapi/pull/12481
#
#   When using 'Depends(<func>)' with a dependency function containing "flat-typed" arguments (int, str, etc.)
#   their parameters are automatically mapped to 'Path' parameters.
#   To avoid having them detected and clashing with 'Query' or 'Body' parameters,
#   they should only be provided when they actually apply for the corresponding route,
#   and should **explicitly** indicate when to include/exclude them with 'Path' otherwise.
#
#   However, one caveat to 'Path' is that is is **required** (no default '... = None' allowed).
#   Therefore, following "dependable" functions should use 'Annotated[..., Path(include_in_schema=False)]' and combine
#   with an appropriate 'BaseModel' that defines the actual Path parameters (while including more metadata).
#   If an error like 'assert not is_path_param, "Path parameters cannot have default values"' is raised, then
#   there is a great chance that the "dependable" function over-list irrelevant/unused path parameters for that route.
#

@cache
def _get_dggrs_provider(dggrsId: Annotated[str, Path()]) -> AbstractDGGRSProvider:
    global dggrs_providers
    try:
        return dggrs_providers[dggrsId]
    except KeyError:
        logger.error(f'{__name__} _get_dggrs_provider: {dggrsId} not found in dggrs providers')
        raise HTTPException(status_code=500, detail=f'{__name__} _get_dggrs_provider: {dggrsId} not found in dggrs providers')


@cache
def _get_collection_provider(
    # ensure this parameter is not reported in OpenAPI schema
    # use 'Path' (although it isn't such a parameter), to ensure it doesn't clash with Query/Body (see above warning)
    providerId: Annotated[Optional[str], Path(include_in_schema=False)] = None,
) -> dict[str, AbstractCollectionProvider]:
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
def _get_collection_info(
    # use parameters from 'DggrsDescriptionRequest' instead
    collectionId: Annotated[str, Path(include_in_schema=False)],
) -> dict[str, Collection]:
    global collections
    if (collectionId is None):
        return collections.copy()
    try:
        return {collectionId: copy.deepcopy(collections[collectionId])}
    except KeyError:
        logger.error(f'{__name__} : {collectionId} not found')
        raise HTTPException(status_code=404, detail=f'{__name__}  _get_collection failed: {collectionId} not found')


@cache
def _get_collection(
    # use parameters from 'DggrsDescriptionRequest' instead
    collectionId: Annotated[Optional[str], Path(include_in_schema=False)],
    dggrsId: Annotated[Optional[str], Path(include_in_schema=False)],  # duplicate from '_get_dggrs_description'
) -> dict[str, Collection]:
    global dggrs_providers
    c = _get_collection_info(collectionId)
    collection_dggrs = c[collectionId].collection_provider.dggrsId
    if (dggrsId is not None):
        _get_dggrs_description(dggrsId)
        if (collection_dggrs != dggrsId):
            if (collection_dggrs not in dggrs_providers[dggrsId].dggrs_conversion):
                raise HTTPException(status_code=400, detail=f"{__name__} _get_collection failed: collection doesn't support {dggrsId}.")
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

###############
# API routes
###############


# Landing page and conformance
@router.get(
    "/",
    summary="Landing Page",
    tags=['OGC DGGS API', 'Core'],
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
        Link(
            href=f"{collection_url}/schema",
            rel="[ogc-rel:schema]",
            type="application/schema+json",
            title="Schema of the properties in the collection.",
        ),
    ]
    dggrs_provider = _get_dggrs_provider(collection.collection_provider.dggrsId)
    min_rf, max_rf = collection.collection_provider.min_refinement_level, collection.collection_provider.max_refinement_level
    col = ogc_CollectionDesc(**collection.model_dump(exclude={'collection_provider'}))
    col.minScaleDenominator = int((dggrs_provider.get_cls_by_zone_level(max_rf)*1000) / 0.00028)
    col.maxScaleDenominator = int((dggrs_provider.get_cls_by_zone_level(min_rf)*1000) / 0.00028)
    col.links.extend(collection_links)
    return col


@router.get(
    "/collections",
    response_model=ogc_Collections,
    summary="Collections Listing",
    tags=['OGC DGGS API', 'Collection'],
)
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
        collections_info = _get_collection_info(None)
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


@router.get(
    "/collections/{collectionId}",
    response_model=ogc_CollectionDesc,
    summary="Collection Description",
    tags=['OGC DGGS API', 'Collection'],
)
async def list_collection_by_id(
    req: Request,
    resp: Response,
    col_req: Annotated[CollectionPathRequest, Depends()],
) -> Union[ogc_CollectionDesc, Response]:

    collections_info = _get_collection_info(None)
    # logger.info(f'{collections_info.keys()}')
    if col_req.collectionId in collections_info.keys():
        collection = collections_info[col_req.collectionId]
        col = describe_collection(collection, req.url)
        for link in col.links:
            resp.headers.append("Link", link.header())
        return col
    else:
        raise HTTPException(status_code=404, detail=f'{__name__} {col_req.collectionId} not found')


@router.get(
    "/collections/{collectionId}/schema",
    response_class=JsonSchemaResponse,  # override Content-Type response header
    response_model=CollectionQueryables,
    tags=['OGC DGGS API', 'Collection'],
    summary="Collection Schema Properties",
)
async def get_collection_schema_request(
    req: Request,
    col_req: Annotated[CollectionPathRequest, Depends()],  # noqa: OpenAPI path parameter documentation
    collections: Dict[str, Collection] = Depends(_get_collection_info),
) -> Union[CollectionQueryables, JsonSchemaResponse]:
    schema = await get_collection_queryables_request(req, collections)
    return schema


@router.get(
    "/collections/{collectionId}/queryables",
    summary="Collection Queryables Properties",
    tags=['OGC DGGS API', 'Collection'],
    response_class=JsonSchemaResponse,  # override Content-Type response header
    response_model=CollectionQueryables,
)
async def get_collection_queryables_request(
    req: Request,
    collections: Dict[str, Collection] = Depends(_get_collection_info),
) -> Union[CollectionQueryables, JsonSchemaResponse]:

    _, collection = collections.copy().popitem()
    if (collection is None):
        # Error, should not be None, it should be handled by _get_collection
        raise HTTPException(status_code=404, detail=f'{__name__} collection is None')

    collection_provider = _get_collection_provider(collection.collection_provider.providerId)
    _, collection_provider = collection_provider.copy().popitem()
    if (collection_provider is None):
        # Error, should not be None, it should be handled by _get_collection_provider
        raise HTTPException(status_code=404, detail=f'{__name__} {collection.collection_provider.providerId} not found')
    schema_id = str(req.url).split('?')[0].split('#')[0]  # remove query/fragments if any indicated
    queryables = get_queryables(collection, collection_provider)
    queryables.id_ = schema_id
    return queryables


@router.get("/conformance", summary="OGC API Conformance Listing", tags=['OGC DGGS API', 'Core'])
async def conformance(conformance_classes=Depends(get_conformance_classes)) -> JSONResponse:
    return JSONResponse(content={'conformsTo': conformance_classes})


# Core conformance class

# dggrs-list
@router.get(
    "/dggs",
    response_model=DggrsListResponse,
    summary="DGGS Listing",
    tags=['OGC DGGS API', 'DGGRS'],
)
async def support_dggs(
    req: Request,
) -> Union[DggrsListResponse, Response]:
    collections = _get_collection_info(None)
    return await collection_support_dggs(req, None, collections=collections)


@router.get(
    "/collections/{collectionId}/dggs",
    response_model=DggrsListResponse,
    summary="DGGS Listing available for a specific Collection",
    tags=['OGC DGGS API', 'DGGRS'],
)
async def collection_support_dggs(
    req: Request,
    col_req: Annotated[CollectionPathRequest, Depends()] = None,
    collections: Dict[str, Collection] = Depends(_get_collection_info),
) -> Union[DggrsListResponse, Response]:

    logger.info(f'{__name__} called.')
    global dggrs, dggrs_providers
    selected_dggrs = copy.deepcopy(dggrs)
    try:
        if (col_req and col_req.collectionId is not None):
            collection = collections[col_req.collectionId]
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
@router.get(
    "/dggs/{dggrsId}",
    response_model=DggrsDescription,
    summary="DGGS Description",
    tags=['OGC DGGS API', 'DGGRS'],
)
async def dggrs_description(
    req: Request,
    dggrs_req: Annotated[DggrsPathRequest, Depends()],
    dggrs: DggrsDescription = Depends(_get_dggrs_description),
    dggrs_provider=Depends(_get_dggrs_provider)
) -> Union[DggrsDescription, Response]:
    collections = _get_collection_info(None)
    return await collection_dggrs_description(req, dggrs_req, dggrs, collections, dggrs_provider)


@router.get(
    "/collections/{collectionId}/dggs/{dggrsId}",
    response_model=DggrsDescription,
    summary="DGGS Description available for a specific Collection",
    tags=['OGC DGGS API', 'DGGRS'],
)
async def collection_dggrs_description(
    req: Request,
    dggrs_req: Annotated[CollectionDggrsPathRequest, Depends()],
    dggrs: Annotated[DggrsDescription, Depends(_get_dggrs_description)],
    collections: Annotated[Dict[str, Collection], Depends(_get_collection)],
    dggrs_provider=Depends(_get_dggrs_provider)
) -> Union[DggrsDescription, Response]:
    dggrs_description = dggrs.model_copy(deep=True)
    current_url = str(req.url)
    col_id = getattr(dggrs_req, "collectionId", None)
    if (col_id is not None):
        collection = collections[col_id]
        dggrs_description.maxRefinementLevel = collection.collection_provider.max_refinement_level
        # update the maxRefinementLevel if it belongs to dggrs conversion
        if (dggrs_req.dggrsId != collection.collection_provider.dggrsId
                and dggrs_req.dggrsId in dggrs_provider.dggrs_conversion.keys()):
            dggrs_description.maxRefinementLevel += dggrs_provider.dggrs_conversion[collection.collection_provider.dggrsId].zonelevel_offset
    return query_dggrs_definition(current_url, dggrs_description)


# zone-info
@router.get(
    "/dggs/{dggrsId}/zones/{zoneId}",
    response_model=ZoneInfoResponse,
    summary="DGGS Zone Information Query across Collections",
    tags=['OGC DGGS API', 'Zone Query'],
)
async def dggrs_zone_info(
    req: Request,
    zoneinfoReq: Annotated[ZoneInfoPathRequest, Depends()],
    dggrs_description: DggrsDescription = Depends(_get_dggrs_description),
    dggrs_provider: AbstractDGGRSProvider = Depends(_get_dggrs_provider),
    collection_provider=Depends(_get_collection_provider),
) -> Union[ZoneInfoResponse, Response]:
    collections = _get_collection_info(None)
    return await collection_dggrs_zone_info(req, zoneinfoReq, dggrs_description, dggrs_provider, collections, collection_provider)


@router.get(
    "/collections/{collectionId}/dggs/{dggrsId}/zones/{zoneId}",
    response_model=ZoneInfoResponse,
    summary="DGGS Zone Information Query for a specific Collection",
    tags=['OGC DGGS API', 'Zone Query'],
)
async def collection_dggrs_zone_info(
    req: Request,
    zoneinfoReq: Annotated[CollectionZoneInfoPathRequest, Depends()],
    dggrs_description: DggrsDescription = Depends(_get_dggrs_description),
    dggrs_provider: AbstractDGGRSProvider = Depends(_get_dggrs_provider),
    collections: Dict[str, Collection] = Depends(_get_collection),
    collection_provider: Dict[str, AbstractCollectionProvider] = Depends(_get_collection_provider),
) -> Union[ZoneInfoResponse, Response]:
    try:
        info = query_zone_info(zoneinfoReq, req.url, dggrs_description, dggrs_provider, collections, collection_provider)
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
# Only using the existence of `datetime` query to determine if the query belongs to temporal or non-temporal.

@router.get(
    "/dggs/{dggrsId}/zones",
    response_model=Union[ZonesResponse, ZonesGeoJson],
    summary="DGGS Zones Listing across Collections",
    tags=['OGC DGGS API', 'Zone Query'],
)
async def list_dggrs_zones(
    req: Request,
    dggrs_req: Annotated[DggrsPathRequest, Depends()],  # noqa: OpenAPI parameters definition only
    zonesReq: Annotated[ZonesRequest, Query()],
    dggrs_description: DggrsDescription = Depends(_get_dggrs_description),
    dggrs_provider: AbstractDGGRSProvider = Depends(_get_dggrs_provider),
    collection_provider=Depends(_get_collection_provider),
) -> Union[ZonesResponse, ZonesGeoJson, Response]:
    collections = _get_collection_info(None)
    return await collection_list_dggrs_zones(req, dggrs_req, zonesReq, dggrs_description, dggrs_provider, collections, collection_provider)


@router.get(
    "/collections/{collectionId}/dggs/{dggrsId}/zones",
    response_model=Union[ZonesResponse, ZonesGeoJson],
    summary="DGGS Zones Listing for a specific Collection",
    tags=['OGC DGGS API', 'Zone Query'],
)
async def collection_list_dggrs_zones(
    req: Request,
    dggrs_req: Annotated[CollectionDggrsPathRequest, Depends()],  # noqa: OpenAPI parameters definition only
    zonesReq: Annotated[ZonesRequest, Query()],
    dggrs_description: Annotated[DggrsDescription, Depends(_get_dggrs_description)],
    dggrs_provider: Annotated[AbstractDGGRSProvider, Depends(_get_dggrs_provider)],
    collections: Annotated[Dict[str, Collection], Depends(_get_collection)],
    collection_provider: Annotated[Dict[str, AbstractCollectionProvider], Depends(_get_collection_provider)],
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
    cql_attributes = set() if (filter is None) else getCQLAttributes(filter)
    # Parameters checking
    if (parent_zone is not None):
        parent_level = dggrs_provider.get_cells_zone_level([parent_zone])[0]
        # If the zone-level is not specified, use the parent-zone refinement level + 1 as the zone level value.
        zone_level = zone_level if (zone_level is not None) else parent_level + 1
        if (parent_level >= zone_level):
            logger.error(f'{__name__} query zones list, parent zone refinement level ({parent_level}) is finer or equal to the requested zone-level({zone_level}).')
            raise HTTPException(status_code=400, detail=f"query zones list, parent zone refinement level ({parent_level}) is finer or equal to the requested zone-level({zone_level}).")
    skip_collection = []
    for k, v in collections.items():
        max_ = v.collection_provider.max_refinement_level
        min_ = v.collection_provider.min_refinement_level
        # if the dggrsId is not the native dggrs supported by the collection,
        # check if the native dggrs supports conversion
        if (dggrs_description.id != v.collection_provider.dggrsId
                and v.collection_provider.dggrsId not in dggrs_provider.dggrs_conversion):
            skip_collection.append(k)
            continue
        if (dggrs_description.id != v.collection_provider.dggrsId
                and v.collection_provider.dggrsId in dggrs_provider.dggrs_conversion):
            max_ = v.collection_provider.max_refinement_level + dggrs_provider.dggrs_conversion[v.collection_provider.dggrsId].zonelevel_offset
        if (zone_level < min_ or zone_level > max_):
            logger.warning(f'{__name__} query zones list, zone level {zone_level} is not within the {k} refinement level: {min_} {max_}')
            skip_collection.append(k)
            continue
        cp = collection_provider[v.collection_provider.providerId]
        # if the collection consists of datetime_col or timeStamp, then it is a temporal collection
        is_temporalcollection = (cp.datasources[v.collection_provider.datasource_id].datetime_col is not None or v.timestamp is not None)
        if (include_datetime and not is_temporalcollection):
            # skip non-temporal collections
            skip_collection.append(k)
        # For a non-temporal query, only filter out collections that have a native temporal dimension
        if (not include_datetime and cp.datasources[v.collection_provider.datasource_id].datetime_col is not None):
            # skip non-temporal collections
            skip_collection.append(k)
    if (len(collections) == len(skip_collection)):
        raise HTTPException(status_code=400, detail=f"f'{__name__} query zones list, zone level {zone_level} is over refinement for all collections")
    filtered_collections = {k: v for k, v in collections.items() if (k not in skip_collection)}
    if (bbox is not None):
        try:
            bbox = box(*bbox)
            bbox_crs = zonesReq.bbox_crs if (zonesReq.bbox_crs is not None) else "wgs84"
            if (bbox_crs != 'wgs84'):
                logger.info(f'{__name__} query zones list {dggrs_description.id}, original bbox: {bbox}')
                project = pyproj.Transformer.from_crs(bbox_crs, "wgs84", always_xy=True).transform
                bbox = transform(project, bbox)
                logger.info(f'{__name__} query zones list {dggrs_description.id}, transformed bbox: {bbox}')
        except Exception as e:
            logger.error(f'{__name__} query zones list, bbox conversion failed : {e}')
            raise HTTPException(status_code=400, detail=f"{__name__} query zones list, bbox conversion failed : {e}")
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
# Only using the existence of `datetime` query to determine if the query belongs to temporal or non-temporal.

@router.get(
    "/dggs/{dggrsId}/zones/{zoneId}/data",
    response_model=None,
    summary="DGGS Zones Data Retrieval across Collections",
    tags=['OGC DGGS API', 'Zone Data'],
)
async def dggrs_zones_data(
    req: Request,
    zonedataReq: Annotated[ZoneInfoPathRequest, Depends()],
    zonedataQuery: Annotated[ZonesDataRequest, Query()],
    dggrs_description: DggrsDescription = Depends(_get_dggrs_description),
    dggrs_provider: AbstractDGGRSProvider = Depends(_get_dggrs_provider),
) -> ZonesDataDggsJsonResponse | FileResponse | Response:
    collections = _get_collection_info(None)
    return await collection_dggrs_zones_data(req, zonedataReq, zonedataQuery, dggrs_description, dggrs_provider, collections)


@router.get(
    "/collections/{collectionId}/dggs/{dggrsId}/zones/{zoneId}/data",
    response_model=None,
    summary="DGGS Zones Data Retrieval for a specific Collection",
    tags=['OGC DGGS API', 'Zone Data'],
)
async def collection_dggrs_zones_data(
    req: Request,
    zonedataReq: Annotated[CollectionZoneInfoPathRequest, Depends()],
    zonedataQuery: Annotated[ZonesDataRequest, Query()],
    dggrs_description: DggrsDescription = Depends(_get_dggrs_description),
    dggrs_provider: AbstractDGGRSProvider = Depends(_get_dggrs_provider),
    collections: Dict[str, Collection] = Depends(_get_collection),
    collection_provider=Depends(_get_collection_provider),
) -> ZonesDataDggsJsonResponse | FileResponse | Response:
    returntype = _get_return_type(req, zone_data_support_returntype, zone_data_support_formats, 'application/json')
    zoneId = zonedataReq.zoneId
    depth = zonedataQuery.zone_depth if (zonedataQuery.zone_depth is not None) else [dggrs_description.defaultDepth]
    returngeometry = zonedataQuery.geometry if (zonedataQuery.geometry is not None) else 'zone-region'
    returngeometry = None if (returntype != 'application/geo+json') else returngeometry
    filter = zonedataQuery.filter
    include_datetime = True if (zonedataQuery.datetime is not None) else False
    include_properties = cast(Optional[list[str]], zonedataQuery.properties)
    exclude_properties = cast(Optional[list[str]], zonedataQuery.exclude_properties)
    # prepare zone levels from zoneId + depth
    # The first element of zone_level will be the zoneId's level, follow by the required relative depth (zoneId's level + d)
    try:
        base_level = dggrs_provider.get_cells_zone_level([zoneId])[0]
    except Exception as e:
        logger.error(f'{__name__} query zone data {zonedataReq.dggrsId}, zone id {zoneId} get zone level error: {e}')
        raise HTTPException(status_code=500, detail=f'{__name__} query zone data {zonedataReq.dggrsId}, zone id {zoneId} get zone level error: {e}')
    relative_levels = [base_level + d for d in depth]
    skip_collection = []
    for k, v in collections.items():
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
        is_over_refinement = any([z > max_ for z in relative_levels])
        if (is_over_refinement):
            skip_collection.append(k)
            logger.warning(f'{__name__} query zone data {zonedataReq.dggrsId}, zone id {zoneId} with zone depth: {relative_levels} not supported')
            continue
        cp = collection_provider[v.collection_provider.providerId]
        is_temporalcollection = (cp.datasources[v.collection_provider.datasource_id].datetime_col is not None or v.timestamp is not None)
        if (include_datetime and not is_temporalcollection):
            # skip non-temporal collections
            skip_collection.append(k)
        # For a non-temporal query, only filter out collections that have a native temporal dimension
        if (not include_datetime and cp.datasources[v.collection_provider.datasource_id].datetime_col):
            # skip non-temporal collections
            skip_collection.append(k)
    if (len(collections) == len(skip_collection)):
        raise HTTPException(status_code=400,
                            detail=f"f'{__name__} zone id {zoneId} with relative depth: {depth} is over refinement for all collections")
    filtered_collections = {k: v for k, v in collections.items() if (k not in skip_collection)}
    try:
        result = query_zone_data(req, zoneId, base_level, relative_levels, dggrs_description,
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
