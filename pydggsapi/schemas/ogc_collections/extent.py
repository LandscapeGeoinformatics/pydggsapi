from __future__ import annotations
from typing import Annotated, List, Literal, Optional, Tuple, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator, conlist
import logging

from pydggsapi.schemas.common_basemodel import CommonBaseModel, OmitIfNone

logger = logging.getLogger()

Coord = Union[str, float, int]
Bbox2D = conlist(float, min_length=4, max_length=4)
Bbox3D = conlist(float, min_length=6, max_length=6)
Bbox = Union[Bbox2D, Bbox3D]


class GridBase(CommonBaseModel):
    cellsCount: int = Field(..., ge=1)


class RegularGrid(GridBase):
    """
    Regular grid with samples spaced at equal intervals.
    """
    resolution: Optional[Coord] = Field(
        None,  # can be 'null', but explicitly (don't omit)
        examples=[
            0.0006866455078,
            "PT1H"
        ],
    )
    firstCoordinate: Optional[Coord] = Field(
        None,  # can be 'null', but explicitly (don't omit)
        examples=[
            -180.0,
            "2020-01-01T00:00:00Z"
        ],
    )
    relativeBounds: Annotated[
        Optional[  # this 'Optional' to allow dropping the field
            conlist(Optional[Coord], min_length=2, max_length=2)  # this 'Optional' to allow actual 'null' values
        ],
        OmitIfNone
    ] = Field(
        None,
        description=(
            'Distance in units from coordinate to the lower and upper bounds of each cell for regular grids, '
            'describing the geometry of the cells.'
        ),
        examples=[
            [-0.5, 0.5],
        ]
    )


class IrregularGrid(GridBase):
    """
    Irregular grid with samples spaced at different intervals.
    """
    coordinates: List[Optional[Coord]] = Field(
        None,
        min_length=1,
        description=(
            'List of coordinates along the dimension for which data organized as '
            'an irregular grid in the collection is available.'
        ),
        examples=[
            [2, 10, 80, 100],
            ["2020-11-12T12:15:00Z", "2020-11-12T12:30:00Z", "2020-11-12T12:45:00Z"],
        ]
    )
    boundsCoordinates: Annotated[
        Optional[  # this 'Optional' to allow dropping the field
            conlist(
                conlist(Optional[Coord], min_length=2, max_length=2),  # this 'Optional' to allow actual 'null' values
                min_length=1,
            )
        ],
        OmitIfNone
    ] = Field(
        None,
        description=(
            'Coordinates of the lower and upper bounds of each cell in absolute units '
            'for irregular grids describing the geometry each cell.'
        ),
        examples=[
            [[-180, -179], [-179, -178]]
        ]
    )


Grid = Union[RegularGrid, IrregularGrid]


class SpatialExtent(CommonBaseModel):
    bbox: List[Bbox] = Field(
        ...,
        examples=[
            [[-180.0, -90.0, 180.0, 90.0]],
            [[-180, -90.0, 0, 0], [0, 0, 180, 90.0]],
        ],
    )
    crs: str = Field(
        'http://www.opengis.net/def/crs/OGC/1.3/CRS84',
        description='Coordinate reference system of the grid dimension.',
        examples=[
            'http://www.opengis.net/def/crs/OGC/1.3/CRS84',
            'http://www.opengis.net/def/crs/EPSG/0/4326',
            'http://www.opengis.net/def/uom/ISO-8601/0/Gregorian',
        ],
    )
    storageCrsBbox: Annotated[Optional[conlist(Bbox, min_length=1)], OmitIfNone] = Field(
        None,
        description='One or more bounding boxes that describe the spatial extent of the data in the native storage CRS.',
    )
    # NOTE: different grid structure because of nested 2D/3D bbox, therefore not reusing 'WithSingleGrid'
    grid: Annotated[Optional[conlist(Grid, min_length=2, max_length=3)], OmitIfNone] = Field(
        None,
        description=(
            'Provides information about the limited availability of data within the collection organized '
            'as a grid (regular or irregular) along the dimension.'
        ),
        examples=[
            [
                {"cellsCount": 10, "resolution": 0.5, "firstCoordinate": -180, "relativeBounds": [-0.5, 0.5]},
                {"cellsCount": 10, "resolution": 0.5, "firstCoordinate": 0.0, "relativeBounds": [-0.5, 0.5]},
            ],
            [
                {"cellsCount": 10, "resolution": 0.5, "firstCoordinate": 0.0},
                {"cellsCount": 10, "resolution": 0.5, "firstCoordinate": 0.0},
            ],
        ]
    )


class TemporalExtent(CommonBaseModel):
    interval: List[conlist(Optional[str], min_length=2, max_length=2)] = Field(
        ...,  # if the field is provided, it must be non-empty, otherwise entire temporal extent object must be omitted
        min_length=1,
    )
    trs: Optional[str] = Field(
        'http://www.opengis.net/def/uom/ISO-8601/0/Gregorian',
        description=(
            'Coordinate reference system of the coordinates in the temporal extent (property interval). '
            'The default reference system is the Gregorian calendar. '
            'For data for which the Gregorian calendar is not suitable, such as geological time scale, '
            'another temporal reference system may be used.'
        ),
        examples=[
            'http://www.opengis.net/def/uom/ISO-8601/0/Gregorian'
        ],
    )
    grid: Annotated[Optional[Grid], OmitIfNone] = Field(
        None,
        description=(
            'Provides information about the limited availability of data within the collection organized '
            'as a grid (regular or irregular) along the dimension.'
        ),
    )


class AdditionalExtent(CommonBaseModel):
    # NOTE:
    #   contrary to other extents, here we purposely use 'default=None' to remove the fields if omitted
    #   (trs, vrs, definition) are mutually exclusive, and therefore, should be provided explicitly if needed
    #   interval is always needed (either in combination of the others, or on its own)
    #   see:
    #       - https://github.com/opengeospatial/ogcapi-common/issues/368)
    #       - https://docs.ogc.org/DRAFTS/20-024.html#ats_umd-collection_extent-uad-definition
    interval: List[conlist(Optional[Coord], min_length=2, max_length=2)] = Field(..., min_length=1)
    trs: Annotated[Optional[str], OmitIfNone] = Field(None)
    vrs: Annotated[Optional[str], OmitIfNone] = Field(None)
    definition: Annotated[Optional[str], OmitIfNone] = Field(None)

    # extra properties that can be added without restriction
    grid: Annotated[Optional[Grid], OmitIfNone] = Field(None)
    unit: Annotated[Optional[str], OmitIfNone] = Field(None)
    unitLang: Annotated[Optional[str], OmitIfNone] = Field(None)
    variableType: Annotated[
        Optional[
            Literal[
                "continuous",
                "numericalOrdinal",
                "numericalNominal",
                "categoricalOrdinal",
                "categoricalNominal",
            ]
        ],
        OmitIfNone
    ] = Field(None)

    @model_validator(mode="after")
    def validate(self) -> AdditionalExtent:
        mutually_exclusive = ['trs', 'vrs', 'definition']
        mutex_props = [prop for prop in mutually_exclusive if getattr(self, prop) is not None]
        if len(mutex_props) > 1:
            raise ValueError(f"Only one of {mutually_exclusive} can be provided.")
        if getattr(self, "unit", None) is not None and getattr(self, "unitLang", None) is None:
            logger.warning("Using default 'unitLang=UCUM' undefined for 'unit' provided in AdditionalExtent")
            self.unitLang = "UCUM"
        return self

    # custom properties are allowed without explicit restriction as long as the above validate
    model_config = ConfigDict(extra='allow')


class Extent(CommonBaseModel):
    spatial: Annotated[Optional[SpatialExtent], OmitIfNone] = Field(
        None, description='The spatial extent of the data in the collection.'
    )
    temporal: Annotated[Optional[TemporalExtent], OmitIfNone] = Field(
        None, description='The temporal extent of the features in the collection.'
    )

    __pydantic_extra__: dict[str, AdditionalExtent] = {}
    model_config = ConfigDict(extra='allow')
