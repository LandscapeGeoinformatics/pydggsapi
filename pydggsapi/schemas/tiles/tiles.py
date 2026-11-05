from pydantic import BaseModel, model_validator, AnyUrl, Field
from fastapi import Path
from typing import List, Optional, Dict, Any
import os

tiles_relative_depth = int(os.environ.get("TILES_API_RELATIVE_DEPTH", 2))
min_tiles_relative_depth = tiles_relative_depth * -1


class TilesRequest(BaseModel):
    collectionId: str = Path(...)
    dggrsId: Optional[str] = None
    z: int = Path(..., ge=0, le=25)
    x: int = Path(...)
    y: int = Path(...)
    dggrsId: str = ""
    relative_depth: int = Field(0, ge=min_tiles_relative_depth, le=tiles_relative_depth)


class TilesFeatures(BaseModel):
    features: List[Dict[str,Any]]

class VectorLayer(BaseModel):
    id: str
    fields: Dict[str,str]

class TilesJSON(BaseModel):
    tilejson: str
    tiles: List[str]
    vector_layers: List[VectorLayer]
    bounds: List[float]
    description: str
    name: str
