from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import Link

from pydantic import AnyUrl, BaseModel, Field, conint


class DggrsItem(BaseModel):
    id: str = Field(
        ...,
        description='Local DGGRS identifier consistent with the `{dggrsId}` parameter of `/dggs/{dggrsId}` resources.',
    )
    title: str = Field(
        ...,
        description='Title of this Discrete Global Grid System, normally used for display to a human',
    )
    uri: Union[AnyUrl, str] = Field(
        ...,
        description='Identifier for this Discrete Global Grid Reference System registered with an authority.',
    )
    links: List[Link] = Field(
        ...,
        description='Links to related resources. A `self` link to the Discrete Global Grid Reference System description and an `[ogc-rel:dggrs-definition]` link to the DGGRS definition (using the schema defined by https://github.com/opengeospatial/ogcapi-discrete-global-grid-systems/blob/master/core/schemas/dggrs-definition/dggrs-definition-proposed.yaml) are required.',
    )


class DggrsListResponse(BaseModel):
    dggrs: List[DggrsItem]
    links: List[Link]
