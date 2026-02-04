from __future__ import annotations
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import CrsModel, Feature, ReturnGeometryTypes

from fastapi import Depends, Query
from fastapi.exceptions import HTTPException
from pydantic import BaseModel, Field, conint, model_validator
from pygeofilter.parsers.cql_json import parse as cql_json_parser
from pygeofilter.parsers.ecql import parse as cql_text_parser
from pygeofilter.ast import AstType
from datetime import datetime as dt
from typing import Annotated, List, Optional, Union, Tuple, Literal, get_args
import json

zone_query_support_returntype = ['application/json', 'application/geo+json']
zone_query_support_formats = {
    'json': 'application/json',
    'geojson': 'application/geo+json',
    'geo+json': 'application/geo+json',
}
zone_query_support_formats.update({typ: typ for typ in zone_query_support_returntype})
zone_datetime_placeholder = '_pydggs_datetime'


def bbox_converter(bbox: Optional[str] = None) -> Optional[List[float]]:
    if not bbox:
        return None
    if isinstance(bbox, str):
        bbox = bbox.split(",")
    return [float(i) for i in bbox]


def datetime_cql_validation(datetime: str | None, cql_filter: str | None) -> Tuple[dt | None, AstType | None]:
    if (datetime is not None):
        datetime = datetime.split("/")
        try:
            datetime = [dt.fromisoformat(d) if (d != "..") else d for d in datetime]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f'datetime format error: {e}')
        if (len([d for d in datetime if (d == "..")]) == 2):
            raise HTTPException(status_code=400, detail='datetime format error ".." occurs twice in the datetime parameter')
        datetime_query = f"({zone_datetime_placeholder} = '{datetime[0]}')"
        if (len(datetime) > 1):
            try:
                idx = datetime.index("..")
                ops = "<=" if (idx == 0) else ">="
                datetime_query = f"({zone_datetime_placeholder} {ops} '{datetime[1-idx]}')"
            except ValueError:
                datetime_query = f"(({zone_datetime_placeholder} >= '{datetime[0]}') AND ({zone_datetime_placeholder} <= '{datetime[1]}'))"
        if (cql_filter is not None):
            cql_filter += f" AND {datetime_query}"
        else:
            cql_filter = datetime_query
    if (cql_filter is not None):
        parser = cql_text_parser
        try:
            cql_filter = json.loads(cql_filter)
            parser = cql_json_parser
        except ValueError:
            pass  # then it is a cql-text (or not)
        try:
            cql_filter = parser(cql_filter)
        except Exception as er:
            raise HTTPException(status_code=400, detail=f"{cql_filter} is not a valid CQL-text or CQL-json :{er}")
    return datetime, cql_filter


class ZonesRequest(BaseModel):
    zone_level: Optional[conint(ge=0)] = Field(
        default=None,
        alias="zone-level",
        description=(
            "The DGGS hierarchy level at which to return the list of zones. The precision of the calculation to return the results depends on this parameter."
            "Returned zones will have a level equal or smaller to this specified level. If `compact-zones` is set to true, all returned zones will be of this zone level. "
            "If not specified, this defaults to the most detailed zone that the system is able to return for the specific request."
        )
    )
    compact_zone: Optional[bool] = Field(
        default=True,
        alias="compact-zone",
        description=(
            "If set to true (default), when the list of DGGS zones to be returned at the requested resolution (zone-level) includes all children of a parent zone,"
            " the parent zone will be returned as a shorthand for that list of children zone.  If set to false, all zones returned will be of the requested zone level."
        )
    )
    parent_zone: Optional[Union[int, str]] = Field(
        default=None,
        alias="parent-zone",
        description=(
            "The optional parent zone parameter restricts a zone query to only return zones within that parent zone."
            "Used together with `zone-level`, it allows to explore the response for a large zone query in a hierarchical manner."
        )
    )
    limit: Optional[int] = Field(default=1000)
    bbox_crs: Optional[str] = Field(default=None, alias="bbox-crs")
    bbox: Optional[str] = Field(default=None)
    geometry: Optional[ReturnGeometryTypes] = Field(default=None)
    filter: Optional[str] = Field(default=None)
    datetime: Optional[str] = Field(default=None)

    @model_validator(mode="after")
    def validation(self):
        if (self.bbox is None and self.parent_zone is None):
            raise HTTPException(status_code=400, detail='Either bbox or parent-zone must be set')
        if (self.bbox is not None):
            self.bbox = bbox_converter(self.bbox)
            if (len(self.bbox) != 4):
                raise HTTPException(status_code=400, detail='bbox length is not equal to 4')
            if (self.zone_level is None):
                raise HTTPException(status_code=400, detail='zone-level must be specified')
        # If the request includes the datetime query, it will be concatenated to the CQL filter
        # using the attribute name from zone_datetime_placeholder.
        self.datetime, self.filter = datetime_cql_validation(self.datetime, self.filter)
        return self


class ZonesResponse(BaseModel):
    zones: List[str]
    returnedAreaMetersSquare: Optional[float]


class ZonesGeoJson(BaseModel):
    type: str
    features: List[Feature]
