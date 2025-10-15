from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import Feature
from pydggsapi.schemas.ogc_dggs.dggrs_zones import ZonesResponse, ZonesGeoJson
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from pydggsapi.schemas.api.collections import Collection


from pydggsapi.dependencies.dggrs_providers.abstract_dggrs_provider import AbstractDGGRSProvider
from pydggsapi.dependencies.collections_providers.abstract_collection_provider import AbstractCollectionProvider

import numpy as np
from pygeofilter.ast import Attribute as pygeofilter_ats
from typing import Dict
import numpy as np
import itertools
import logging

logger = logging.getLogger()


def query_zones_list(bbox, zone_level, limit, dggrs_info: DggrsDescription, dggrs_provider: AbstractDGGRSProvider,
                     collection: Dict[str, Collection], collection_provider: Dict[str, AbstractCollectionProvider],
                     compact=True, parent_zone=None, returntype='application/json', returngeometry='zone-region', cql_filter=None):
    logger.debug(f'{__name__} query zones list: {bbox}, {zone_level}, {limit}, {parent_zone}, {compact}')
    # generate zones for the bbox at the required zone_level
    result = dggrs_provider.zoneslist(bbox, zone_level, parent_zone, returngeometry, compact)
    filter_ = []
    # we need to import the dict here to avoid import loop.
    # from pydggsapi.routers.dggs_api import dggrs_providers as dggrs_pool
    cql_attributes = set([])
    if (cql_filter is not None):
        cql_attributes = set([a.name for a in cql_filter.get_sub_nodes() if (isinstance(a, pygeofilter_ats))])
    skipped = 0
    for k, v in collection.items():
        converted = None
        converted_zones = result.zones
        converted_level = zone_level
        datasource_vars = list(collection_provider[v.collection_provider.providerId].get_datadictionary(v.collection_provider.datasource_id).data.keys())
        intersection = (set(datasource_vars) & cql_attributes)
        # check if the cql attributes contain inside the datasource
        if ((len(cql_attributes) > 0) and (len(intersection) == 0)):
            skipped += 1
            continue
        if (v.collection_provider.dggrsId != dggrs_info.id and
                v.collection_provider.dggrsId in dggrs_provider.dggrs_conversion):
            # perform conversion
            converted = dggrs_provider.convert(result.zones, v.collection_provider.dggrsId)
            converted_zones = converted.target_zoneIds
            converted_level = converted.target_res[0]
        # if the requried zone_level is coarser than the datasource, use relative_zonelevels
        # to get the zones at the coarsest refinement level of the datasource.
        # child_parent_mapping = {z: z for z in converted_zones}
        # if (converted_level < v.collection_provider.min_refinement_level):
            # a mapping that helps to filter out which child zones are not inside the dataset
        #    child_parent_mapping = {}
        #    for z in converted_zones:
                # we need to change the calling dggrs_provider to the collection's dggrs for conversion case
        #        children = dggrs_pool[v.collection_provider.dggrsId].get_relative_zonelevels(z, converted_level,
        #                                                                                     [v.collection_provider.min_refinement_level], "zone-centroid")
        #        [child_parent_mapping.update({zid: z})for zid in
        #         children.relative_zonelevels[v.collection_provider.min_refinement_level].zoneIds]
        #    converted_zones = list(child_parent_mapping.keys())
        #    converted_level = v.collection_provider.min_refinement_level
        if (converted_level >= v.collection_provider.min_refinement_level):
            filtered_zoneIds = collection_provider[v.collection_provider.providerId].get_data(converted_zones, converted_level,
                                                                                              v.collection_provider.datasource_id, cql_filter).zoneIds
        else:
            filtered_zoneIds = []
        # filtered_zoneIds = [child_parent_mapping[child] for child in set(child_parent_mapping.keys()) & set(filtered_zoneIds)]
        if (converted is not None):
            # If conversion take place, it is a 3 level mapping, from child to parent, from parnet to the original dggrs
            filter_ += np.array(converted.zoneIds)[np.isin(converted.target_zoneIds, filtered_zoneIds)].tolist()
        else:
            filter_ += filtered_zoneIds
    if (skipped == len(collection)):
        raise ValueError(f"{__name__} query zones list cql attributes({cql_attributes}) not found in all collections.")
    if (len(filter_) == 0):
        return None
    logger.debug(f'{__name__} query zones list result: {len(filter_)}')
    if (returntype == 'application/geo+json'):
        features = [Feature(**{'type': 'Feature', 'id': i, 'geometry': result.geometry[i], 'properties': {'zoneId': zid}})
                    for i, zid in enumerate(result.zones[:limit]) if (zid in filter_)]
        return ZonesGeoJson(**{'type': 'FeatureCollection', 'features': features})
    total_area = sum(np.array(result.returnedAreaMetersSquare)[np.isin(result.zones, filter_)].tolist())
    return ZonesResponse(**{'zones': np.unique(filter_[:limit]), 'returnedAreaMetersSquare': total_area})
