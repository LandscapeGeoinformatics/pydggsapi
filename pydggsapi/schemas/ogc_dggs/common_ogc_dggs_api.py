from __future__ import annotations
from typing import Annotated, Any, Dict, Optional, Union, List, Literal
from pydantic import AnyUrl, BaseModel, Field, RootModel

from pydggsapi.schemas.common_basemodel import CommonBaseModel, OmitIfNone
from pydggsapi.schemas.common_geojson import GeoJSONPoint, GeoJSONPolygon
from fastapi import Query

ReturnGeometryTypes = Literal['zone-centroid', 'zone-region']


class LinkBase(CommonBaseModel):
    rel: str = Field(
        ...,
        description='The type or semantics of the relation.',
        examples=['alternate'],
    )
    type: Annotated[Optional[str], OmitIfNone] = Field(
        None,
        description='A hint indicating what the media type of the result of dereferencing the link should be.',
        examples=['application/geo+json'],
    )
    hreflang: Annotated[Optional[str], OmitIfNone] = Field(
        None,
        description='A hint indicating what the language of the result of dereferencing the link should be.',
        examples=['en'],
    )
    title: Annotated[Optional[str], OmitIfNone] = Field(
        None,
        description='Used to label the destination of a link such that it can be used as a human-readable identifier.',
        examples=['Trierer Strasse 70, 53115 Bonn'],
    )
    length: Annotated[Optional[str], OmitIfNone] = None

    def header(self) -> str:
        """
        Generate the HTTP Link header representation of the Link object.
        """
        uri = getattr(self, 'href', None) or getattr(self, 'uriTemplate', None)
        parts = [f'<{uri}>', f'rel="{self.rel}"']
        if self.type:
            parts.append(f'type="{self.type}"')
        if self.hreflang:
            parts.append(f'hreflang="{self.hreflang}"')
        if self.title:
            parts.append(f'title="{self.title}"')
        return '; '.join(parts)


class Link(LinkBase):
    href: str = Field(
        ...,
        description='Supplies the URI to a remote resource (or resource fragment).',
        examples=['http://data.example.com/buildings/123'],
    )


class LinkTemplate(LinkBase):
    uriTemplate: str = Field(
        ...,
        description=(
            'Supplies the URL template to a remote resource (or resource fragment), '
            'with template variables surrounded by curly brackets (`{` `}`).'
        ),
        examples=['http://data.example.com/buildings/{featureId}'],
    )
    varBase: Annotated[Optional[str], OmitIfNone] = Field(
        None,
        description='A base path to retrieve semantic information about the variables used in URL template.',
        examples=['/ogcapi/vars/'],
    )


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
