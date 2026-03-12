from pydantic import ValidationError
from pydggsapi.schemas.tiles.tiles import TilesFeatures, TilesJSON, VectorLayer
import pyproj
from shapely.geometry import box
from shapely.ops import transform
from uuid import UUID
from datetime import datetime
import os
import logging


SRID_LNGLAT = 4326
SRID_SPHERICAL_MERCATOR = 3857
default_uuid = os.environ.get('DEFAULTUUID', '00000000-0000-0000-0000-000000000000')

transformer = pyproj.Transformer.from_crs(crs_from=SRID_LNGLAT, crs_to=SRID_SPHERICAL_MERCATOR, always_xy=True)


