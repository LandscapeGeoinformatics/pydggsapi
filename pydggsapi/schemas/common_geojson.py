from pydantic import BaseModel
from typing import List, Tuple


class GeoJSONPoint(BaseModel):
    type: str
    coordinates: Tuple[float, float]

    class Config:
        json_schema_extra = {
            "example": {
                "type": "Point",
                "coordinates": [1.0, 1.0]
            }
        }


class GeoJSONPolygon(BaseModel):
    type: str
    coordinates: List[List[Tuple[float, float]]]

    class Config:
        json_schema_extra = {
            "example": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [0, 0],
                        [0, 1],
                        [1, 1],
                        [1, 0],
                        [0, 0]
                    ]
                ]
            }
        }
