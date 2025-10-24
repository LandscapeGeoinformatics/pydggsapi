from __future__ import annotations
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import CrsModel, Feature
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescriptionRequest
from typing import Annotated, List, Optional, Union, Tuple
from fastapi import Depends
from fastapi.exceptions import HTTPException

from pygeofilter.parsers.cql_json import parse as cql_json_parser
from pygeofilter.parsers.ecql import parse as cql_text_parser
from pygeofilter.ast import AstType
from datetime import datetime as dt
import json
from pydantic import BaseModel, conint, model_validator

zone_query_support_returntype = ['application/json', 'application/geo+json']
zone_query_support_geometry = ['zone-centroid', 'zone-region']
zone_datetime_placeholder = '_pydggs_datetime'


def bbox_converter(bbox: Optional[str] = None) -> Optional[List[float]]:
    if not bbox:
        return None
    if isinstance(bbox, str):
        bbox = bbox.split(",")
    return [float(i) for i in bbox]


def datetime_cql_validation(datetime: str | None, cql_filter: str | None) -> AstType | None:
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


class ZonesRequest(DggrsDescriptionRequest):
    zone_level: Optional[conint(ge=0)] = None
    compact_zone: Optional[bool] = None
    parent_zone: Optional[Union[int, str]] = None
    limit: Optional[int] = None
    bbox_crs: Optional[str] = None
    bbox: Annotated[
        Optional[Union[List[float], Tuple[float, float, float, float]]],
        Depends(bbox_converter)
    ] = None
    geometry: Optional[str] = None
    filter: Optional[str] = None
    datetime: Optional[str] = None

    @model_validator(mode="after")
    def validation(self):
        if (self.bbox is None and self.parent_zone is None):
            raise HTTPException(status_code=400, detail='Either bbox or parent-zone must be set')
        if (self.bbox is not None):
            if (len(self.bbox) != 4):
                raise HTTPException(status_code=400, detail='bbox length is not equal to 4')
        if (self.geometry is not None):
            if (self.geometry not in zone_query_support_geometry):
                raise HTTPException(status_code=400, detail=f"{self.geometry} is not supported")
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
