from __future__ import annotations
from pydggsapi.schemas.common_basemodel import CommonBaseModel
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import Link, LinkTemplate, CrsModel
from typing import Annotated, List, Optional, Union
from pydantic import AnyUrl, BaseModel, Field, conint, model_validator
from fastapi import HTTPException, Path


class CollectionPathRequest(CommonBaseModel):
    collectionId: str = Field(
        ...,
        description='Identifier of the collection to be requested.',
    )


class DggrsPathRequest(CommonBaseModel):
    dggrsId: str = Field(
        ...,
        description='Identifier of the Discrete Global Grid Reference System (DGGRS) to be requested.',
    )


class CollectionDggrsPathRequest(CollectionPathRequest, DggrsPathRequest):
    pass


class DggrsDescription(BaseModel):
    id: str = Field(
        ...,
        description='Local DGGRS identifier consistent with the `{dggrsId}` parameter of `/dggs/{dggrsId}` resources.',
    )
    title: str = Field(
        ...,
        description='Title of this Discrete Global Grid Reference System, intended for displaying to a human',
    )
    description: str = Field(
        ...,
        description='Brief narrative description of this Discrete Global Grid System, normally available for display to a human',
    )
    keywords: Optional[List[str]] = Field(
        None,
        description='Unordered list of one or more commonly used or formalized word(s) or phrase(s) used to describe this Discrete Global Grid Reference System',
    )
    uri: Union[AnyUrl, str] = Field(  # can be a URI or a compact URI (CURIE)
        ...,
        description='Identifier for this Discrete Global Grid Reference System registered with an authority.',
    )
    crs: Optional[CrsModel] = None
    defaultDepth: Union[conint(ge=0), str] = Field(
        ...,
        description='The default zone depth returned for zone data retrieval when the `zone-depth` parameter is not used. This is the DGGS resolution levels beyond the requested DGGS zone’s hierarchy level included in the response, when retrieving data for a particular zone. This can be either: • A single positive integer value — representing a specific zone depth to return e.g., `5`; • A range of positive integer values in the form “{low}-{high}” — representing a\n  continuous range of zone depths to return e.g., `1-8`; or,\n• A comma separated list of at least two (2) positive integer values — representing a\n  set of specific zone depths to return e.g., `1,3,7`.\n  A particular data encoding imply a particular zone depth and not support the default zone depth specified here,\n  in which case the default zone depth (or the only possible depth) for that encoding will be used.',
    )
    maxRefinementLevel: Optional[conint(ge=0)] = Field(
        None,
        description='The maximum refinement level at which the full resolution of the data can be retrieved for this DGGRS and origin (using a `zone-depth` relative depth of 0) and/or used for performing the most accurate zone queries (using that value for `zone-level`)',
    )
    maxRelativeDepth: Optional[conint(ge=0)] = Field(
        None,
        description='The maximum relative depth at which the full resolution of the data can be retrieved for this DGGRS and origin',
    )
    links: List[Link] = Field(
        ...,
        description='Links to related resources. A `self` link to the Discrete Global Grid Reference System description and an `[ogc-rel:dggrs-definition]` link to the DGGRS definition (using the schema defined by https://github.com/opengeospatial/ogcapi-discrete-global-grid-systems/blob/master/core/schemas/dggrs-definition/dggrs-definition-proposed.yaml) are required. An `[ogc-rel:dggrs-zone-query]` link to query DGGS zones should also be included if _DGGS Zone Query_ is supported.',
    )
    linkTemplates: Optional[List[LinkTemplate]] = Field(
        None,
        description='Templated Links to related resources. A templated `[ogc-rel:dggrs-zone-data]` link to retrieve data should be included if _DGGS Zone Data_ is supported.',
    )
