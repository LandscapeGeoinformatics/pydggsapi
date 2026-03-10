from __future__ import annotations
from pydggsapi.schemas.common_basemodel import CommonBaseModel, OmitIfNone
from pydggsapi.schemas.ogc_collections.schema import Property
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import Feature, ReturnGeometryTypes
from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoPathRequest
from pydggsapi.schemas.ogc_dggs.dggrs_zones import zone_datetime_placeholder, datetime_cql_validation

from typing import Annotated, List, Literal, Optional, Dict, Union, Any, cast
from fastapi.exceptions import HTTPException
from fastapi import Query
from pydantic import AnyUrl, Field, ConfigDict, model_validator

zone_data_support_returntype = [
    'application/json',     # DGGS-JSON
    'application/ubjson',   # DGGS-UBJSON
    'application/zarr+zip',
    'application/geo+json',
]
zone_data_support_formats = {
    'json': 'application/json',
    'dggs-json': 'application/json',
    'dggs+json': 'application/json',
    'ubjson': 'application/ubjson',
    'dggs+ubjson': 'application/ubjson',
    'zarr': 'application/zarr+zip',
    'geojson': 'application/geo+json',
    'geo+json': 'application/geo+json',
}
zone_data_support_formats.update({typ: typ for typ in zone_data_support_returntype})


class ZonesDataRequest(CommonBaseModel):
    """
    DGGS Zones Data Request Query Parameters Model.
    """
    # NOTE:
    #   Queries are all optional by default, so adding 'Optional[str]'
    #   creates duplicates 'string | (string | null)' typings in OpenAPI schema.
    #   Simply list the 'str' type to avoid this, although the actual omission value will allow 'default=None'.

    zone_depth: str = Field(
        default=None,
        alias="zone-depth",
        pattern=r"(\d{1,2})|(\d{1,2}-\d{1,2})|(\d{1,2}[,\d{1,2}]+)",
        description=(
            "Relative depth(s) to the requested zone as single depth value, "
            "a range (int-int) of depths, or a comma-separated list of specific depth values or ranges."
        )
    )
    geometry: ReturnGeometryTypes = Field(default=None)
    filter: str = Field(default=None)
    datetime: str = Field(default=None)

    # although we transform them to 'list[str]', use 'str' here report the patterns correctly in OpenAPI schema
    properties: str = Field(
        default=None,
        pattern=r"[\w\.\-\_]+(,[\w\.\-\_]+)*",
        description=(
            "Comma-separated list of properties contained in the DGGS to be returned. "
            "If not specified, all available properties are returned by default."
        )
    )
    exclude_properties: str = Field(
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
            self.properties = self.properties.split(",")  # type: ignore
        if self.exclude_properties is not None:
            self.exclude_properties = self.exclude_properties.split(",")  # type: ignore
        return self


class Shape(CommonBaseModel):
    count: int
    subZones: Annotated[Optional[int], OmitIfNone] = None
    dimensions: Annotated[Optional[Dict[str, int]], OmitIfNone] = None


class Value(CommonBaseModel):
    depth: int
    shape: Shape
    data: list[Any]


class DimensionGrid(CommonBaseModel):
    cellsCount: int
    # required: coordinates OR firstCoordinate + resolution
    coordinates: Annotated[Union[List[Optional[float]], List[Optional[str]]], OmitIfNone] = None
    firstCoordinate: Annotated[Optional[Union[float, str]], OmitIfNone] = None
    resolution: Annotated[str, OmitIfNone] = None


class Dimension(CommonBaseModel):
    name: str
    grid: DimensionGrid
    interval: Union[List[Optional[float]], List[Optional[str]]]
    definition: Annotated[Optional[str], OmitIfNone] = None
    unit: Annotated[Optional[str], OmitIfNone] = None
    unitLang: Annotated[Optional[str], OmitIfNone] = None


class Schema(CommonBaseModel):
    schema_: str = Field("https://json-schema.org/draft/2020-12/schema", alias="$schema")
    id_: Optional[str] = Field(None, alias="$id")
    title: str = "DGGS Zones Data Schema"
    type: str = "object"
    properties: Dict[str, Property]

    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)


class ZonesDataDggsJsonResponse(CommonBaseModel):
    schema_: str = Field("https://schemas.opengis.net/ogcapi/dggs/1.0/core/schemas/dggs-json/dggs-json.json", alias='$schema')
    dggrs: AnyUrl
    zoneId: str
    depths: List[int]
    schema: Schema
    dimensions: Annotated[Optional[List[Dimension]], OmitIfNone] = None
    values: Dict[str, List[Value]]

    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)


class ZonesDataGeoJson(CommonBaseModel):
    type: str
    features: List[Feature]
