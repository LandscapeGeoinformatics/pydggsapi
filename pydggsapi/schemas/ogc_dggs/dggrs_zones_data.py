from __future__ import annotations
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import CrsModel, Feature
from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoRequest
from pydggsapi.schemas.common_geojson import GeoJSONPoint, GeoJSONPolygon
from typing import List, Optional, Dict, Union, Any
from fastapi import Query
from fastapi.exceptions import HTTPException
import re
from pydantic import AnyUrl, BaseModel, Field, model_validator, ValidationError

support_returntype = ['application/json', 'application/zarr+zip', 'application/geo+json']
support_geometry = ['zone-centroid', 'zone-region']


class ZonesDataRequest(ZoneInfoRequest):
    depth: Optional[str] = None  # Field(pattern=r'', default=None)
    geometry: Optional[str] = None

    @model_validator(mode='after')
    def validator(self):
        if (self.depth is not None):
            if (not re.match("(\d{1,2})|(\d{1,2}-\d{1,2})", self.depth)):
                raise HTTPException(status_code=500, detail="depth must be either a integer or in range (int-int) format")
            depth = self.depth.split("-")
            try:
                if (len(depth) == 1):
                    self.depth = [int(depth[0])]
                else:
                    if (int(depth[0]) > int(depth[1])):
                        raise HTTPException(status_code=500, detail="depth range is not in order")
                    self.depth = [int(depth[0]), int(depth[1])]
            except ValueError:
                raise HTTPException(status_code=500, detail="depth must be integer >=0 ")
        if (self.geometry is not None):
            if (self.geometry not in support_geometry):
                raise HTTPException(status_code=500, detail=f"{self.geometry} is not supported")
        return self


class Property(BaseModel):
    type: str
    title: Optional[str] = None


class Value(BaseModel):
    depth: int
    shape: Dict[str, int]
    data: list[float]


class ZonesDataDggsJsonResponse(BaseModel):
    dggrs: AnyUrl
    zoneId: str
    depths: List[int]
    # schema_: Optional[Schema] = Field(None, alias='schema')
    properties: Dict[str, Property]
    values: Dict[str, List[Value]]


class ZonesDataGeoJson(BaseModel):
    type: str
    features: List[Feature]
