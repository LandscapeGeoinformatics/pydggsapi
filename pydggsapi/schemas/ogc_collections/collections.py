from __future__ import annotations
from pydggsapi.schemas.common_basemodel import OmitIfNone, CommonBaseModel
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import Link
from pydggsapi.schemas.ogc_collections.extent import Extent


from datetime import datetime
from enum import Enum
from typing import List, Optional, Union, Annotated

from pydantic import AnyUrl, BaseModel, Field, conint, RootModel


class DataType1(Enum):
    map = 'map'
    vector = 'vector'
    coverage = 'coverage'


class DataType(RootModel):
    root: Union[str, DataType1]


class CollectionDesc(CommonBaseModel):
    id: str = Field(
        ...,
        description='Identifier of the collection used, for example, in URIs.',
        examples=['dem'],
    )
    title: Annotated[Optional[str], OmitIfNone] = Field(
        None,
        description='A human-readable title of the collection.',
        examples=['Digital Elevation Model'],
    )
    description: Annotated[Optional[str], OmitIfNone] = Field(
        None,
        description='A description of the data in the collection.',
        examples=['A Digital Elevation Model.'],
    )
    attribution: Annotated[Optional[str], OmitIfNone] = Field(None, title='attribution for the collection')
    links: List[Link] = Field(
        [],
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
        None,
        description='Indicator about the type of the items in the collection if the collection has an accessible /collections/{collectionId}/items endpoint.',
    )
    crs: Annotated[Optional[str], OmitIfNone] = Field(
        'http://www.opengis.net/def/crs/OGC/1.3/CRS84',
        description='The list of coordinate reference systems supported by the API; the first item is the default coordinate reference system.',
        examples=[
            'http://www.opengis.net/def/crs/OGC/1.3/CRS84',
            'http://www.opengis.net/def/crs/EPSG/0/4326',
        ],
    )
    storageCrs: Annotated[Optional[str], OmitIfNone] = Field(
        'http://www.opengis.net/def/crs/OGC/1.3/CRS84',
        description='The native coordinate reference system (i.e., the most efficient CRS in which to request the data, possibly how the data is stored on the server); this is the default output coordinate reference system for Maps and Coverages.',
        examples=['http://www.opengis.net/def/crs/OGC/1.3/CRS84'],
    )
    dataType: Annotated[Optional[DataType], OmitIfNone] = None
    geometryDimension: Annotated[Optional[conint(ge=0, le=3)], OmitIfNone] = Field(
        None,
        description='The geometry dimension of the features shown in this layer (0: points, 1: curves, 2: surfaces, 3: solids), unspecified: mixed or unknown.',
    )
    minScaleDenominator: Annotated[Optional[float], OmitIfNone] = Field(
        None, description='Minimum scale denominator for usage of the collection.'
    )
    maxScaleDenominator: Annotated[Optional[float], OmitIfNone] = Field(
        None, description='Maximum scale denominator for usage of the collection.'
    )
    minCellSize: Annotated[Optional[float], OmitIfNone] = Field(
        None, description='Minimum cell size for usage of the collection.'
    )
    maxCellSize: Annotated[Optional[float], OmitIfNone] = Field(
        None, description='Maximum cell size for usage of the collection.'
    )


class Collections(CommonBaseModel):
    collections: List[CollectionDesc]
    links: List[Link]
    timeStamp: Annotated[Optional[datetime], OmitIfNone] = None
    numberMatched: Annotated[Optional[int], OmitIfNone] = Field(
        None, ge=0, description='The number of collections that match the query (if a query was provided).'
    )
    numberReturned: Annotated[Optional[int], OmitIfNone] = Field(
        None, ge=0, description='The number of collections returned in the response.'
    )
