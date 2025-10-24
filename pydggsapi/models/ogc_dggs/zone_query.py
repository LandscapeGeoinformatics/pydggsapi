from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import Feature
from pydggsapi.schemas.ogc_dggs.dggrs_zones import ZonesResponse, ZonesGeoJson, zone_datetime_placeholder
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from pydggsapi.schemas.api.collections import Collection


from pydggsapi.dependencies.dggrs_providers.abstract_dggrs_provider import AbstractDGGRSProvider
from pydggsapi.dependencies.collections_providers.abstract_collection_provider import AbstractCollectionProvider, DatetimeNotDefinedError
from pydggsapi.dependencies.api.utils import getCQLAttributes

import numpy as np
from pygeofilter.ast import AstType
from typing import Dict
import numpy as np
import itertools
import logging

logger = logging.getLogger()


def query_zones_list(bbox, zone_level, limit, dggrs_info: DggrsDescription, dggrs_provider: AbstractDGGRSProvider,
                     collection: Dict[str, Collection], collection_provider: Dict[str, AbstractCollectionProvider],
                     compact=True, parent_zone=None, returntype='application/json', returngeometry='zone-region',
                     cql_filter: AstType = None, include_datetime: bool = False):
    logger.debug(f'{__name__} query zones list: {bbox}, {zone_level}, {limit}, {parent_zone}, {compact}')
    # generate zones for the bbox at the required zone_level
    result = dggrs_provider.zoneslist(bbox, zone_level, parent_zone, returngeometry, compact)
    filter_ = []
    cql_attributes = set() if (cql_filter is None) else getCQLAttributes(cql_filter)
    skipped = 0
    for k, v in collection.items():
        converted = None
        converted_zones = result.zones
        converted_level = zone_level
        datasource_id = v.collection_provider.datasource_id
        cp_id = v.collection_provider.providerId
        datasource_vars = list(collection_provider[cp_id].get_datadictionary(datasource_id).data.keys())

        intersection = (set(datasource_vars) & cql_attributes)
        # check if the cql attributes contain inside the datasource
        # The datasource of the collection must consist all columns that match with the attributes of the cql filter
        if ((len(cql_attributes) > 0)):
            if ((len(intersection) == 0) or (len(intersection) != len(cql_attributes))):
                skipped += 1
                continue
        if (v.collection_provider.dggrsId != dggrs_info.id and
                v.collection_provider.dggrsId in dggrs_provider.dggrs_conversion):
            # perform conversion
            converted = dggrs_provider.convert(result.zones, v.collection_provider.dggrsId)
            converted_zones = converted.target_zoneIds
            converted_level = converted.target_res[0]
        try:
            filtered_zoneIds = collection_provider[cp_id].get_data(converted_zones, converted_level,
                                                                   datasource_id, cql_filter, include_datetime).zoneIds
        except DatetimeNotDefinedError:
            filtered_zoneIds = []
            pass
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
