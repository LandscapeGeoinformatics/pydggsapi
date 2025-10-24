from pygeofilter.ast import Attribute as pygeofilter_attrs
from pydggsapi.schemas.ogc_dggs.dggrs_zones import zone_datetime_placeholder

def getCQLAttributes(cql_filter):
    cql_attributes = set()
    if (isinstance(cql_filter, pygeofilter_attrs)):
        if (cql_filter.name == zone_datetime_placeholder):
            return []
        return [cql_filter.name]
    else:
        [cql_attributes.update(getCQLAttributes(c)) for c in cql_filter.get_sub_nodes() if (hasattr(c, "get_sub_nodes"))]
        return cql_attributes
