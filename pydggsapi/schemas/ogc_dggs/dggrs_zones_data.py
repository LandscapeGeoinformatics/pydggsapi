from __future__ import annotations
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import Feature
from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoRequest
from pydggsapi.schemas.ogc_dggs.dggrs_zones import zone_datetime_placeholder, datetime_cql_validation

from typing import List, Literal, Optional, Dict, Union, Any
from fastapi.exceptions import HTTPException
from fastapi import Query
from pydantic import AnyUrl, BaseModel, Field, model_validator

support_returntype = ['application/json', 'application/zarr+zip', 'application/geo+json']


class ZonesDataRequest(BaseModel):
    zone_depth: Optional[str] = Query(
        default=None,
        alias="zone-depth",
        pattern=r"(\d{1,2})|(\d{1,2}-\d{1,2})|(\d{1,2}[,\d{1,2}]+)",
        description=(
            "Relative depth(s) to the requested zone as single depth value, "
            "a range (int-int) of depths, or a comma-separated list of specific depth values or ranges."
        )
    )
    geometry: Optional[Literal['zone-centroid', 'zone-region']] = Query(default=None)
    filter: Optional[str] = Query(default=None)
    datetime: Optional[str] = Query(default=None)
    properties: Optional[str] = Query(
        default=None,
        pattern=r"[\w\.\-\_]+(,[\w\.\-\_]+)*",
        description=(
            "Comma-separated list of properties contained in the DGGS to be returned. "
            "If not specified, all available properties are returned by default."
        )
    )
    exclude_properties: Optional[str] = Query(
        default=None,
        alias="exclude-properties",
        pattern=r"[\w\.\-\_]+(,[\w\.\-\_]+)*",
        description=(
            "Comma-separated list of properties contained in the DGGS to be returned. "
            "If not specified, all available properties are returned by default."
        )
    )

    @model_validator(mode='after')
    def validator(self):
        if (self.zone_depth is not None):
            depths = self.zone_depth.split(",")
            depths = [zd.split("-") for zd in depths]
            try:
                resolved_depths = []
                for zone_depth in depths:
                    if (len(zone_depth) == 1):
                        resolved_depths.append(int(zone_depth[0]))
                    else:
                        range_depths = [int(zone_depth[0]), int(zone_depth[1])]
                        if (range_depths[0] > range_depths[1]):
                            raise HTTPException(status_code=400, detail=f"depth range {range_depths} is not in order")
                        resolved_depths.extend(list(range(range_depths[0], range_depths[1] + 1)))
                self.zone_depth = sorted(list(set(resolved_depths)))
            except ValueError:
                raise HTTPException(status_code=500, detail="depth must be integer >=0 ")
        self.datetime, self.filter = datetime_cql_validation(self.datetime, self.filter)
        if self.properties is not None:
            self.properties = self.properties.split(",")
        if self.exclude_properties is not None:
            self.exclude_properties = self.exclude_properties.split(",")
        return self


class Property(BaseModel):
    type: str
    title: Optional[str] = None


class Value(BaseModel):
    depth: int
    # FIXME: invalid 'shape' object
    #   (https://github.com/opengeospatial/ogcapi-discrete-global-grid-systems/blob/ea1a2ad/core/schemas/dggs-json/dggs-json.yaml#L104)
    shape: Dict[str, int]
    data: list[Any]


class DimensionGrid(BaseModel):
    type: str
    coordinates: List[List[float]]  # List of [lon, lat] pairs


class Dimension(BaseModel):
    name: str
    # FIXME: technically 'grid' is 'required' by API,
    #   but can be problematic (https://github.com/opengeospatial/ogcapi-discrete-global-grid-systems/issues/94)
    grid: Optional[str] = None
    interval: Optional[Union[List[Optional[float]], List[Optional[str]]]] = None
    definition: Optional[str] = None
    unit: Optional[str] = None
    unitLang: Optional[str] = None


class ZonesDataDggsJsonResponse(BaseModel):
    dggrs: AnyUrl
    zoneId: str
    depths: List[int]
    # schema_: Optional[Schema] = Field(None, alias='schema')
    properties: Dict[str, Property]
    values: Dict[str, List[Value]]
    dimensions: Optional[List[Dimension]] = None


class ZonesDataGeoJson(BaseModel):
    type: str
    features: List[Feature]
