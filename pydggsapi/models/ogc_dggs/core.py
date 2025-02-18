from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import Link, LinkTemplate, LandingPageResponse
from pydggsapi.schemas.ogc_dggs.dggrs_list import DggrsItem, DggrsListResponse
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoRequest, ZoneInfoResponse
from pydggsapi.schemas.common_geojson import GeoJSONPolygon, GeoJSONPoint


from typing import Dict
from pydggsapi.dependencies.dggrs_providers.abstract_dggrs_provider import AbstractDGGRSProvider
from pprint import pprint
import logging
logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s {%(module)s} [%(funcName)s] %(message)s',
                    datefmt='%Y-%m-%d,%H:%M:%S', level=logging.INFO)


def landingpage(current_url):
    root = '/'.join(str(current_url).split('/')[:-3])
    self_link = Link(**{'href': str(current_url), 'rel': 'self', 'type': 'application/json', 'title': 'Landing Page'})
    service_desc_link = Link(**{'href': root + '/docs', 'rel': 'service-desc', 'type': 'html', 'title': 'Open API swagger interface'})
    service_doc_link = Link(**{'href': 'https://docs.ogc.org/DRAFTS/21-038.html', 'rel': 'service-doc', 'type': 'html', 'title': 'API Documentation'})
    conformance_link = Link(**{'href': str(current_url) + 'conformance', 'rel': 'http://www.opengis.net/def/rel/ogc/1.0/conformance', 'type': 'application/json', 'title': 'Conformance classes implemented by this API.'})
    dggs_list_link =Link(**{'href': str(current_url) + 'dggs', 'rel': 'ogc-rel:dggrs-list', 'type': 'application/json', 'title': 'List of DGGS implemented by this API.'})
    return LandingPageResponse(**{'title': 'University of Tartu, OGC DGGS API v1-pre', 'description': 'ogc dggs api',
                                  'links': [self_link, service_desc_link, service_doc_link, conformance_link, dggs_list_link]})


def query_support_dggs(current_url, dggs_info: Dict[str, DggrsItem], filter_):
    # DGGRID_ISEA7H_seqnum
    logging.info(f'{__name__} support dggs')
    support_dggs = []
    for k, v in dggs_info.items():
        if (k in filter_):
            for i, link in enumerate(v.links):
                if link.rel == 'self':
                    v.links[i].href = str(current_url) + f'/{k}'
            support_dggs.append(v)
    logging.info(f'{__name__} support dggs ({len(support_dggs)})')
    landing_page = '/'.join(str(current_url).split('/')[:-1])
    dggs_landing_page = Link(**{'href': landing_page, 'rel': 'ogc-rel:dggrs-list', 'title': 'DGGS API landing page'})
    return DggrsListResponse(**{'links': [dggs_landing_page], 'dggrs': support_dggs})


def query_dggrs_definition(current_url, dggrs_description: DggrsDescription):
    logging.info(f'{__name__} query dggrs model {dggrs_description.id}')
    for i, link in enumerate(dggrs_description.links):
        if link.rel == 'self':
            dggrs_description.links[i].href = str(current_url)
    zone_query_link = Link(**{'href': str(current_url) + '/zones', 'rel': 'ogc-rel:dggrs-zone-query', 'title': 'Dggrs zone-query link'})
    zone_data_link = LinkTemplate(**{'uriTemplate': str(current_url) + '/zones/{zoneId}/data', 'rel': 'ogc-rel:dggrs-zone-data',
                                     'title': 'Dggrs zone-query link'})
    dggrs_description.links.append(zone_query_link)
    dggrs_description.linkTemplates = [zone_data_link]
    logging.debug(f'{__name__} query dggrs model: {pprint(dggrs_description)}')
    return dggrs_description


def query_zone_info(zoneinfoReq: ZoneInfoRequest, current_url, dggs_info: DggrsDescription, dggrid: AbstractDGGRSProvider):
    logging.info(f'{__name__} query zone info {zoneinfoReq.dggrsId}, zone id: {zoneinfoReq.zoneId}')
    zoneId = zoneinfoReq.zoneId
    zoneinfo = dggrid.zonesinfo([zoneId])
    dggs_link = '/'.join(str(current_url).split('/')[:-3])
    dggs_link = Link(**{'href': dggs_link, 'rel': 'ogc-rel:dggrs', 'title': 'Link back to /dggs (get list of supported dggs)'})
    data_link = Link(**{'href': str(current_url) + '/data', 'rel': 'ogc-rel:dggrs-zone-data', 'title': 'Link to data-retrieval for the zoneId)'})
    return_ = {'id': str(zoneId)}
    return_['level'] = zoneinfo.zone_level
    return_['links'] = [data_link, dggs_link]
    return_['shapeType'] = zoneinfo.shapeType
    return_['crs'] = dggs_info.crs
    return_['centroid'] = zoneinfo.centroids[0]
    return_['bbox'] = zoneinfo.bbox[0]
    return_['geometry'] = zoneinfo.geometry[0]
    return_['areaMetersSquare'] = zoneinfo.areaMetersSquare
    logging.debug(f'{__name__} query zone info {zoneinfoReq.dggrsId}, zone id: {zoneinfoReq.zoneId}, zoneinfo: {pprint(return_)}')
    return ZoneInfoResponse(**return_)

