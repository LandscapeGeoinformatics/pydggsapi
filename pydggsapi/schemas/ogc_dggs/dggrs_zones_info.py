from __future__ import annotations
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import CrsModel, Link
from pydggsapi.schemas.common_basemodel import CommonBaseModel, OmitIfNone
from pydggsapi.schemas.common_geojson import GeoJSONPolygon, GeoJSONPoint
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import CollectionDggrsPathRequest, DggrsPathRequest
from typing import Annotated, List, Optional
from pydantic import BaseModel, Field, conint
from fastapi import Path


class ZoneInfoPathRequest(DggrsPathRequest):
    zoneId: str = Field(title="zoneId", description="Identifier of the zone to request within the DGGRS.")


class CollectionZoneInfoPathRequest(CollectionDggrsPathRequest, ZoneInfoPathRequest):
    pass


class ZoneInfoResponse(CommonBaseModel):
    id: str
    links: List[Link]
    shapeType: Optional[str]
    level: Optional[conint(ge=0)] = None
    crs: Optional[CrsModel] = None
    centroid: Optional[GeoJSONPoint] = None
    bbox: Optional[List[float]] = None
    geometry: Optional[GeoJSONPolygon] = None
    areaMetersSquare: Annotated[Optional[float], OmitIfNone] = None
    volumeMetersCube: Annotated[Optional[float], OmitIfNone] = None
    temporalDurationSeconds: Annotated[Optional[float], OmitIfNone] = None
    temporalInterval: Annotated[Optional[List[str]], OmitIfNone] = None
    # statistics: Optional[Dict[str, Statistics]]
