from __future__ import annotations
from pydantic import BaseModel
from typing import List, Any, Dict
from typing_extensions import Self

from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import Dimension


class CollectionProvider(BaseModel):
    classname: str
    datasources: Dict[str, Dict]


class CollectionProviderGetDataReturn(BaseModel):
    # amounts of zoneIds, datetimes (if any) and data must align
    # zoneIds should respect the order as established by the DGGS definition (ie: how the DGGS provider returns them)
    # if multiple datetimes per zoneId apply, zoneId is repeated N times [Zone1, Zone1, Zone2, Zone2, ...]
    # the zoneIds must follow this order to resolve into the correct 1D data array in DGGS-JSON response
    zoneIds: List[str] | List[int]
    cols_meta: Dict[str, str]
    # each inner list if data represents the distinct properties for a zoneId x datetime (as applicable)
    # values MUST be NaN-padded where data is missing for a zoneId/datetime/property combination
    data: List[List[Any]]
    # datetime and dimensions can be omitted if not applicable
    # (no other dimensions than 'datetime' is currently supported, though they can be reported as 'properties' instead)
    datetimes: List[str] | None = None
    dimensions: List[Dimension] | None = None


# the key represents the column name and the value represents the data type of the column
class CollectionProviderGetDataDictReturn(BaseModel):
    data: Dict[str, str]
