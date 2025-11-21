from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import Link, LinkTemplate, LandingPageResponse
from pydggsapi.schemas.ogc_dggs.dggrs_list import DggrsItem, DggrsListResponse
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoRequest, ZoneInfoResponse
from pydggsapi.schemas.api.collections import Collection
from pydggsapi.schemas.ogc_collections.queryables import CollectionQueryables, Property
from pydggsapi.schemas.common_geojson import GeoJSONPolygon, GeoJSONPoint
from pydggsapi.dependencies.collections_providers.abstract_collection_provider import AbstractCollectionProvider
from pydggsapi.dependencies.dggrs_providers.abstract_dggrs_provider import AbstractDGGRSProvider

from fastapi import FastAPI
from starlette.requests import URL
from urllib.parse import urljoin

from typing import Dict, Optional, Union
from pprint import pprint
import datetime
import logging
import os

logger = logging.getLogger()


def landingpage(current_url: URL, app: FastAPI) -> LandingPageResponse:
    base_url = str(current_url)
    root_url = urljoin(base_url, "/")
    self_link = Link(href=base_url, rel='self', type='application/json', title='Landing Page')
    service_desc_link = Link(href=urljoin(root_url, app.openapi_url), rel='service-desc', type='application/vnd.oai.openapi+json; version=3.1', title='OpenAPI specification')
    service_doc_link = Link(href=urljoin(root_url, app.docs_url), rel='service-doc', type='text/html', title='OpenAPI swagger interface')
    described_by_link = Link(href='https://docs.ogc.org/DRAFTS/21-038.html', rel='describedby', type='text/html', title='API Documentation')
    conformance_link = Link(href=urljoin(base_url, './conformance'), rel='http://www.opengis.net/def/rel/ogc/1.0/conformance',
                            type='application/json', title='Conformance classes implemented by this API.')
    dggs_list_link = Link(href=urljoin(base_url, './dggs'), rel='[ogc-rel:dggrs-list]', type='application/json',
                          title='List of DGGS implemented by this API.')
    collections_link = Link(href=urljoin(base_url, './collections'), rel='[ogc-rel:data]', type='application/json',
                            title='List of available Collections')

    links = [self_link, service_desc_link, service_doc_link, described_by_link, conformance_link, collections_link, dggs_list_link]
    service_meta_url = os.environ.get('SERVICE_META_URL', None)
    if service_meta_url:
        service_meta_link = Link(href=service_meta_url, rel='service-meta', type='application/json', title='API metadata')
        links.append(service_meta_link)
    return LandingPageResponse(title=app.title, version=app.version, description=app.description, links=links)


def query_support_dggs(current_url, selected_dggrs: Dict[str, DggrsDescription]) -> DggrsListResponse:
    # DGGRID_ISEA7H_seqnum
    logger.debug(f'{__name__} support dggs')
    support_dggrs = []
    base_url = str(current_url)
    for k, v in selected_dggrs.items():
        for i, link in enumerate(v.links):
            if link.rel == 'self':
                v.links[i].href = f'{base_url}/{k}'
        support_dggrs.append(DggrsItem(id=k, title=v.title, links=v.links))
    logger.debug(f'{__name__} support dggs ({len(support_dggrs)})')
    dggs_url = urljoin(base_url, './dggs')
    links = [
        Link(href=base_url, rel='self', title='Current page'),
        Link(href=dggs_url, rel='[ogc-rel:dggrs-list]', title='DGGS API landing page'),
    ]
    if '/collections/' in base_url:
        col_url = base_url.rsplit('/', 1)[0]
        links.append(
            Link(href=col_url, rel='[ogc-rel:geodata]', title='DGGS Collection details')
        )
    return DggrsListResponse(links=links, dggrs=support_dggrs)


def query_dggrs_definition(current_url, dggrs_description: DggrsDescription):
    logger.debug(f'{__name__} query dggrs model {dggrs_description.id}')
    for i, link in enumerate(dggrs_description.links):
        if link.rel == 'self':
            dggrs_description.links[i].href = str(current_url)
    zone_query_link = Link(href=str(current_url) + '/zones', rel='[ogc-rel:dggrs-zone-query]', title='Dggrs zone-query link')
    zone_data_link = LinkTemplate(uriTemplate=str(current_url) + '/zones/{zoneId}/data', rel='[ogc-rel:dggrs-zone-data]',
                                     title='Dggrs zone-query link')
    dggrs_description.links.append(zone_query_link)
    dggrs_description.linkTemplates = [zone_data_link]
    logger.debug(f'{__name__} query dggrs model: {pprint(dggrs_description)}')
    return dggrs_description


def query_zone_info(
    zoneinfoReq: ZoneInfoRequest,
    current_url: URL,
    dggs_info: DggrsDescription,
    dggrs_provider: AbstractDGGRSProvider,
    collection: Dict[str, Collection],
    collection_provider: Dict[str, AbstractCollectionProvider],
) -> Optional[ZoneInfoResponse]:
    logger.debug(f'{__name__} query zone info {zoneinfoReq.dggrsId}, zone id: {zoneinfoReq.zoneId}')
    zoneId = [zoneinfoReq.zoneId]
    zonelevel = dggrs_provider.get_cells_zone_level(zoneId)[0]
    zoneinfo = dggrs_provider.zonesinfo(zoneId)
    filter_ = 0
    for k, v in collection.items():
        zoneId = [zoneinfoReq.zoneId]
        cp = collection_provider[v.collection_provider.providerId]
        datasource_id = v.collection_provider.datasource_id
        if (v.collection_provider.dggrsId != dggs_info.id and
                v.collection_provider.dggrsId not in dggrs_provider.dggrs_conversion):
            continue
        if (v.collection_provider.dggrsId != dggs_info.id and
                v.collection_provider.dggrsId in dggrs_provider.dggrs_conversion):
            converted_zones = dggrs_provider.convert([zoneinfoReq.zoneId], v.collection_provider.dggrsId,
                                                     v.collection_provider.dggrs_zoneid_repr)
            zoneId = converted_zones.target_zoneIds
            zonelevel = converted_zones.target_res[0]
        else:
            if (v.collection_provider.dggrs_zoneid_repr != 'textual'):
                zoneId = dggrs_provider.zone_id_from_textual(zoneId, v.collection_provider.dggrs_zoneid_repr)
        data = cp.get_data(zoneId, zonelevel, datasource_id)
        filter_ += len(data.zoneIds)
    zoneId = zoneinfoReq.zoneId  # reset the zoneId to original one as string
    if (filter_ > 0):
        dggs_link = '/'.join(str(current_url).split('/')[:-3])
        dggs_link = Link(
            href=dggs_link,
            rel='[ogc-rel:dggrs]',
            title='Link back to /dggs (get list of supported dggs)',
            type='application/json',
        )
        data_link = Link(
            href=f'{current_url}/data',
            rel='[ogc-rel:dggrs-zone-data]',
            title='Link to data-retrieval for the zoneId.',
            type='application/json',
        )
        return_ = {'id': zoneId}
        return_['level'] = zoneinfo.zone_level
        return_['links'] = [data_link, dggs_link]
        return_['shapeType'] = zoneinfo.shapeType
        return_['crs'] = dggs_info.crs
        return_['centroid'] = zoneinfo.centroids[0]
        return_['bbox'] = zoneinfo.bbox[0]
        return_['geometry'] = zoneinfo.geometry[0]
        return_['areaMetersSquare'] = zoneinfo.areaMetersSquare
        logger.debug(f'{__name__} query zone info {zoneinfoReq.dggrsId}, zone id: {zoneinfoReq.zoneId}, zoneinfo: {pprint(return_)}')
        return ZoneInfoResponse(**return_)
    return None


def get_json_schema_property(data_type: Union[str, datetime.datetime, datetime.date, datetime.time]) -> Property:
    if data_type in ["date", "date-time", "datetime", "time"]:
        fmt = data_type.replace("datetime", "date-time")
        return Property(type="string", format=fmt)
    elif isinstance(data_type, (datetime.datetime, datetime.date, datetime.time)):
        fmt = data_type.__name__.replace("datetime", "date-time")
        return Property(type="string", format=fmt)
    elif any(data_type.startswith(fmt) for fmt in ['int', 'float', 'double']):
        fmt = data_type if data_type != 'int' else None
        typ = 'number' if data_type != 'int' else 'integer'
        prop = {"type": typ, "format": fmt}
    else:
        prop = {"type": data_type}
    return Property(**prop)


def get_queryables(collection: Collection, collection_provider: AbstractCollectionProvider) -> CollectionQueryables:
    fields = collection_provider.get_datadictionary(collection.collection_provider.datasource_id).data
    col_id = collection.id
    queryables = {}
    for key, typ in fields.items():
        prop_id = f"{col_id}.{key}"
        prop = get_json_schema_property(typ)
        queryables[prop_id] = prop
    return CollectionQueryables(properties=queryables)
