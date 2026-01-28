from pydggsapi.schemas.ogc_collections.collections import CollectionDesc
from pydggsapi.schemas.api.dggrs_providers import ZoneIdRepresentationType
from pydggsapi.schemas.common_basemodel import OmitIfNone
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Annotated

collection_timestamp_placeholder = "collection_timestamp"

class Provider(BaseModel):
    providerId: str
    dggrsId: str
    dggrs_zoneid_repr: ZoneIdRepresentationType = "textual"
    max_refinement_level: int
    min_refinement_level: int
    datasource_id: str


class Collection(CollectionDesc):
    timestamp: Annotated[Optional[datetime], OmitIfNone] = None
    collection_provider: Provider
