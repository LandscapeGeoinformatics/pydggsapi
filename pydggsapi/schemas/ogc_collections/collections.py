from __future__ import annotations
from pydggsapi.schemas.common_basemodel import _OmitIfNone, CommonBaseModel
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import Link
from pydggsapi.schemas.ogc_collections.extent import Spatial, Temporal


from datetime import datetime
from enum import Enum
from typing import List, Optional, Union, Annotated

from pydantic import AnyUrl, BaseModel, Field, conint, RootModel

OmitIfNone = _OmitIfNone()


class DataType1(Enum):
    map = 'map'
    vector = 'vector'
    coverage = 'coverage'


class DataType(RootModel):
    root: Union[str, DataType1]


class Extent(BaseModel):
    spatial: Optional[Spatial] = Field(
        None, description='The spatial extent of the data in the collection.'
    )
    temporal: Optional[Temporal] = Field(
        None, description='The temporal extent of the features in the collection.'
    )


class CollectionDesc(CommonBaseModel):
    id: str = Field(
        ...,
        description='identifier of the collection used, for example, in URIs',
        examples=['dem'],
    )
    title: Annotated[Optional[str], OmitIfNone] = Field(
        None,
        description='human readable title of the collection',
        examples=['Digital Elevation Model'],
    )
    description: Annotated[Optional[str], OmitIfNone] = Field(
        None,
        description='a description of the data in the collection',
        examples=['A Digital Elevation Model.'],
    )
    attribution: Annotated[Optional[str], OmitIfNone] = Field(None, title='attribution for the collection')
    links: List[Link] = Field(
        lambda: [],
        examples=[
            [
                {
                    'href': 'http://data.example.org/collections/dem?f=json',
                    'rel': 'self',
                    'type': 'application/json',
                    'title': 'Digital Elevation Model',
                },
                {
                    'href': 'http://data.example.org/collections/dem?f=html',
                    'rel': 'alternate',
                    'type': 'application/json',
                    'title': 'Digital Elevation Model',
                },
                {
                    'href': 'http://data.example.org/collections/dem/coverage',
                    'rel': 'coverage',
                    'type': 'image/tiff; application=geotiff',
                    'title': 'Digital Elevation Model',
                },
                {
                    'href': 'http://data.example.org/collections/dem/coverage/domainset',
                    'rel': 'domainset',
                    'type': 'application/json',
                    'title': 'Digital Elevation Model',
                },
                {
                    'href': 'http://data.example.org/collections/dem/coverage/rangetype',
                    'rel': 'rangetype',
                    'type': 'application/json',
                    'title': 'Digital Elevation Model',
                },
                {
                    'href': 'http://data.example.org/collections/dem/coverage/metadata',
                    'rel': 'metadata',
                    'type': 'application/json',
                    'title': 'Digital Elevation Model',
                },
            ],
        ]
    )
    extent: Annotated[Optional[Extent], OmitIfNone] = None
    itemType: Annotated[Optional[str], OmitIfNone] = Field(
        '',
        description='indicator about the type of the items in the collection if the collection has an accessible /collections/{collectionId}/items endpoint',
    )
    crs: Annotated[Optional[str], OmitIfNone] = Field(
        'http://www.opengis.net/def/crs/OGC/1.3/CRS84',
        description='the list of coordinate reference systems supported by the API; the first item is the default coordinate reference system',
        examples=[
            'http://www.opengis.net/def/crs/OGC/1.3/CRS84',
            'http://www.opengis.net/def/crs/EPSG/0/4326',
        ],
    )
    storageCrs: Annotated[Optional[str], OmitIfNone] = Field(
        'http://www.opengis.net/def/crs/OGC/1.3/CRS84',
        description='the native coordinate reference system (i.e., the most efficient CRS in which to request the data, possibly how the data is stored on the server); this is the default output coordinate reference system for Maps and Coverages',
        examples=['http://www.opengis.net/def/crs/OGC/1.3/CRS84'],
    )
    dataType: Annotated[Optional[DataType], OmitIfNone] = None
    geometryDimension: Annotated[Optional[conint(ge=0, le=3)], OmitIfNone] = Field(
        None,
        description='The geometry dimension of the features shown in this layer (0: points, 1: curves, 2: surfaces, 3: solids), unspecified: mixed or unknown',
    )
    minScaleDenominator: Annotated[Optional[float], OmitIfNone] = Field(
        None, description='Minimum scale denominator for usage of the collection'
    )
    maxScaleDenominator: Annotated[Optional[float], OmitIfNone] = Field(
        None, description='Maximum scale denominator for usage of the collection'
    )
    minCellSize: Annotated[Optional[float], OmitIfNone] = Field(
        None, description='Minimum cell size for usage of the collection'
    )
    maxCellSize: Annotated[Optional[float], OmitIfNone] = Field(
        None, description='Maximum cell size for usage of the collection'
    )

class Collections(BaseModel):
    links: List[Link]
    timeStamp: Optional[datetime] = None
    #numberMatched: Optional[NumberMatched] = None
    #numberReturned: Optional[NumberReturned] = None
    collections: List[CollectionDesc]
