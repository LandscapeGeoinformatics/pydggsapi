from __future__ import annotations
from typing import Annotated, Any, Dict, Optional, Union, List
from pydantic import AnyUrl, BaseModel, Field, RootModel

from pydggsapi.schemas.common_basemodel import CommonBaseModel, OmitIfNone
from pydggsapi.schemas.common_geojson import GeoJSONPoint, GeoJSONPolygon
from fastapi import Query


class Link(CommonBaseModel):
    href: str = Field(
        ...,
        description='Supplies the URI to a remote resource (or resource fragment).',
        example='http://data.example.com/buildings/123',
    )
    rel: str = Field(
        ...,
        description='The type or semantics of the relation.',
        example='alternate',
    )
    type: Optional[str] = Field(
        None,
        description='A hint indicating what the media type of the result of dereferencing the link should be.',
        example='application/geo+json',
    )
    hreflang: Annotated[Optional[str], OmitIfNone] = Field(
        None,
        description='A hint indicating what the language of the result of dereferencing the link should be.',
        example='en',
    )
    title: Annotated[Optional[str], OmitIfNone] = Field(
        None,
        description='Used to label the destination of a link such that it can be used as a human-readable identifier.',
        example='Trierer Strasse 70, 53115 Bonn',
    )
    length: Annotated[Optional[str], OmitIfNone] = None


class Crs2(BaseModel):
    uri: AnyUrl = Field(
        ..., description='Reference to one coordinate reference system (CRS)'
    )


class Wkt(BaseModel):
    pass


class Crs3(BaseModel):
    wkt: Wkt


class Crs4(BaseModel):
    referenceSystem: Dict[str, Any] = Field(
        ...,
        description='A reference system data structure as defined in the MD_ReferenceSystem of the ISO 19115',
    )


class CrsModel(RootModel):
    root: Union[str, Union[Crs2, Crs3, Crs4]] = Field(..., title='CRS')
    # crs: str


class LinkTemplate(BaseModel):
    uriTemplate: str = Field(
        ...,
        description='Supplies the URL template to a remote resource (or resource fragment), with template variables surrounded by curly brackets (`{` `}`).',
        example='http://data.example.com/buildings/{featureId}',
    )
    rel: str = Field(
        ..., description='The type or semantics of the relation.', example='alternate'
    )
    type: Optional[str] = Field(
        None,
        description='A hint indicating what the media type of the result of dereferencing the link templates should be.',
        example='application/geo+json',
    )
    varBase: Optional[str] = Field(
        None,
        description='A base path to retrieve semantic information about the variables used in URL template.',
        example='/ogcapi/vars/',
    )
    hreflang: Optional[str] = Field(
        None,
        description='A hint indicating what the language of the result of dereferencing the link should be.',
        example='en',
    )
    title: Optional[str] = Field(
        None,
        description='Used to label the destination of a link template such that it can be used as a human-readable identifier.',
        example='Trierer Strasse 70, 53115 Bonn',
    )
    length: Optional[int] = None


class LandingPageResponse(BaseModel):
    title: str
    version: str
    description: str
    links: List[Link]


class Feature(BaseModel):
    type: str
    id: int
    geometry: Union[GeoJSONPoint, GeoJSONPolygon]
    properties: Dict[str, Any]


class Extent(BaseModel):
    spatial: Optional[dict] = Field(None, description="Spatial extent of the data in the collection")
    temporal: Optional[dict] = Field(None, description="Temporal extent of the data in the collection")
