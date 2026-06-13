# here should be DGGRID related functions and methods
# DGGRID ISEA7H resolutions

from pydggsapi.dependencies.dggrs_providers.abstract_dggrs_provider import AbstractDGGRSProvider, ZoneIdRepresentationType
from pydggsapi.schemas.common_geojson import GeoJSONPolygon, GeoJSONPoint
from pydggsapi.schemas.api.dggrs_providers import (
    DGGRSProviderZoneInfoReturn,
    DGGRSProviderZonesListReturn,
    DGGRSProviderGetRelativeZoneLevelsReturn,
    DGGRSProviderConversionReturn,
    DGGRSProviderZonesElement,
)
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import ReturnGeometryTypes
import healpix_geo
import numpy as np
import shapely
import json
import logging
from typing import Any, List, Union, Optional, get_args

logger = logging.getLogger()

# Implementation assumption:
# - For nested index, there are no functions to return the refinement level of a zone id,
#   so the only way to do that is using zuniq index. In resultthe implementation only support zuniq index.
# - healpix-geo doesn't support textural zone id representation,
#   so I assume the input zone id is just the uint64 in str format


supported_indexing_schema = ["zuniq"]
supported_ellipsoid = ["sphere", "wgs84"]

# healpix_geo doesn't support zone statistics function yet
# unit : square meter and meter
healpix_zone_statistics = {
    0 : {"area" : 42506000000000.0000 ,  "cls":    6519662.5680 },
    1 : { "area" : 10626500000000.0000 ,  "cls":    3259831.2840 },
    2 : { "area" :  2656625000000.0000 ,  "cls":    1629915.6420 },
    3 : { "area" :   664156250000.0000 ,  "cls":     814957.8210 },
    4 : { "area" :   166039062500.0000 ,  "cls":     407478.9105 },
    5 : { "area" :    41509765625.0000 ,  "cls":     203739.4552 },
    6 : { "area" :    10377441406.2500 ,  "cls":     101869.7276 },
    7 : { "area" :     2594360351.5625 ,  "cls":     50934.8638 },
    8 : { "area" :      648590087.8906 ,  "cls":      25467.4319 },
    9 : { "area" :      162147521.9727 ,  "cls":      12733.7160 },
    10 : { "area" :       40536880.4932 , "cls":       6366.8580 },
    11 : { "area" :       10134220.1233 , "cls":        3183.4290 },
    12 : { "area" :        2533555.0308 , "cls":        1591.7145 },
    13 : { "area" :         633388.7577 , "cls":         795.8572 },
    14 : { "area" :         158347.1894 , "cls":         397.9286 },
    15 : { "area" :          39586.7974 , "cls":         198.9643 },
    16 : { "area" :           9896.6993 , "cls":          99.4822 },
    17 : { "area" :           2474.1748 , "cls":          49.7411 },
    18 : { "area" :            618.5437 , "cls":          24.8705 },
    19 : { "area" :            154.6359 , "cls":          12.4353 },
    20 : { "area" :             38.6590 , "cls":           6.2176 },
    21 : { "area" :              9.6647 , "cls":           3.1088 },
    22 : { "area" :              2.4162 , "cls":           1.5544 },
    23 : { "area" :              0.6040 , "cls":           0.7772 },
    24 : { "area" :              0.1510 , "cls":           0.3886 },
    25 : { "area" :              0.0377 , "cls":           0.1943 },
    26 : { "area" :              0.0094 , "cls":           0.0972 },
    27 : { "area" :               0.0024, "cls":            0.0486 },
    28 : { "area" :              0.0006 , "cls":           0.0243 },
    29 : { "area" :              0.0001 , "cls":           0.0121 }}


class HEALPixZuniqProvider(AbstractDGGRSProvider):
    def __init__(self, **params):
        self.indexing_schema = params.get("indexing_schema", "zuniq").lower()
        self.ellipsoid = params.get("ellipsoid", "wgs84").lower()
        if (self.indexing_schema not in supported_indexing_schema):
            raise ValueError(f"{__name__} {self.indexing_schema} not supported")
        if (self.ellipsoid not in supported_ellipsoid):
            raise ValueError(f"{__name__} {self.indexing_schema} not supported")
        self.ellipsoid = self.ellipsoid.upper()

    def convert(self, zoneIds: List[str], targedggrs: str,
                zone_id_repr: ZoneIdRepresentationType = 'textual') -> DGGRSProviderConversionReturn:
        raise NotImplementedError

    # at the time of implementation, healpix_geo doesn't support textural repr of zone id
    # so assume the input is just uint64 in str
    def zone_id_from_textual(self, cellIds: List[str], zone_id_repr: str) -> List[Any]:
        if (zone_id_repr not in get_args(ZoneIdRepresentationType)):
            raise ValueError("{__name__} {zone_id_repr} representation is not supported.")
        if (len(cellIds) == 0):
            return []
        if (zone_id_repr == "textual"):
            return cellIds
        if (zone_id_repr == "int"):
            return [int(z) for z in cellIds]
        if (zone_id_repr == "hexstring"):
            raise ValueError("{__name__} doesn't support hexstring zone id representation")

    # at the time of implementation, healpix_geo doesn't support textural repr of zone id
    # so assume the output is just uint64 in str
    def zone_id_to_textual(self, cellIds: List[Any], zone_id_repr: str, refinement_level=None) -> List[str]:
        if (zone_id_repr not in get_args(ZoneIdRepresentationType)):
            raise ValueError("{__name__} {zone_id_repr} representation is not supported.")
        if (len(cellIds) == 0):
            return []
        if (zone_id_repr == "textual"):
            return cellIds
        if (zone_id_repr == "int"):
            # get_data return zone id in string format
            return [str(z) for z in cellIds]
        if (zone_id_repr == "hexstring"):
            raise ValueError("{__name__} doesn't support hexstring zone id representation")

    def get_cls_by_zone_level(self, zone_level: int) -> float:
        return healpix_zone_statistics[zone_level]["cls"]

    def get_zone_level_by_cls(self, cls_km: float):
        for k, v in healpix_zone_statistics.items():
            if (v["cls"] < cls_km * 1000):
                return k

    def get_cells_zone_level(self, cellIds: List[str]) -> List[int]:
        _, depth = healpix_geo.zuniq.to_nested(cellIds)
        if (isinstance(depth, int)):
            depth = [depth]
        else:
            depth = depth.tolist()
        return depth

    def get_relative_zonelevels(self, cellId: str, base_level: int, zone_levels: List[int],
                                geometry: Optional[ReturnGeometryTypes] = 'zone-region') -> DGGRSProviderGetRelativeZoneLevelsReturn:
        children = {}
        geometry = geometry.lower() if (geometry is not None) else geometry
        cellId = self.zone_id_from_textual([cellId], "int")
        # utilising the zoom_to function of nested index
        nested_cellId, nested_rf = healpix_geo.zuniq.to_nested(np.array(cellId))
        for z in zone_levels:
            subzone_nestedIds = healpix_geo.nested.zoom_to(nested_cellId, nested_rf, z)
            subzones_geometry = None
            if (geometry is not None):
                subzones_geometry = [self._nestedindex_generateZoneGeometry(cellId, z, False if (geometry == 'zone-region') else True)
                                     for cellId in subzone_nestedIds]
            subzoneIds = self.zone_id_to_textual(subzone_nestedIds.tolist(), "int")
            children[z] = DGGRSProviderZonesElement(**{'zoneIds': subzoneIds,
                                                       'geometry': subzones_geometry})
        return DGGRSProviderGetRelativeZoneLevelsReturn(relative_zonelevels=children)

    def zonesinfo(self, cellIds: List[str]) -> DGGRSProviderZoneInfoReturn:
        zone_level = self.get_cells_zone_level(cellIds)[0]
        cellIds = self.zone_id_from_textual(cellIds, "int")
        try:
            centroids = [self._generateZoneGeometry(cellId, True)
                         for cellId in cellIds]
            square_vertices = [self._generateZoneGeometry(cellId, False)
                               for cellId in cellIds]
            extents = [shapely.from_geojson(json.dumps(geojson)) for geojson in square_vertices]
            extents = [b.bounds for b in extents]
        except Exception as e:
            logger.error(f'{__name__} zone id {cellIds} convert failed, {e}')
            raise Exception(f'{__name__} zone id {cellIds} convert failed, {e}')
        return DGGRSProviderZoneInfoReturn(**{'zone_level': zone_level, 'shapeType': 'hexagon',
                                              'centroids': centroids, 'geometry': square_vertices, 'bbox': extents,
                                              'areaMetersSquare': self.mygrid.getRefZoneArea(zone_level)})

    def zoneslist(self, bbox: Union[shapely.box, None], zone_level: int, parent_zone: Union[str, int, None],
                  returngeometry: ReturnGeometryTypes, compact: bool = True) -> List[str]:
        if (bbox is not None):
            try:
                bbox = shapely.bounds(bbox)
                zones_list, _ = healpix_geo.zuniq.zone_coverage(tuple(bbox.tolist()), zone_level, ellipsoid=self.ellipsoid, flat=False)
                zones_list = set(zones_list)
            except Exception as e:
                logger.error(f'{__name__} query zones list, bbox: {bbox} dggrid convert failed :{e}')
                raise Exception(f"{__name__} query zones list, bbox: {bbox} dggrid convert failed {e}")
            logger.info(f'{__name__} query zones list, number of hexagons: {len(zones_list)}')
        if (parent_zone is not None):
            try:
                parent_zone_level = self.get_cells_zone_level([parent_zone])[0]
                parent_zone = self.zone_id_from_textual([parent_zone], "int")
                parent_zone_nestedId, _ = healpix_geo.zuniq(parent_zone)
                subzones_list = healpix_geo.nested.zoome_to(parent_zone_nestedId, parent_zone_level, zone_level)
                subzones_list = healpix_geo.zuniq.from_nested(subzones_list, zone_level)
                zones_list = (zones_list & subzones_list) if (bbox is not None) else subzones_list
            except Exception as e:
                logger.error(f'{__name__} query zones list, parent_zone: {parent_zone} get children failed {e}')
                raise Exception(f'parent_zone: {parent_zone} get children failed {e}')
        if (len(zones_list) == 0):
            raise Exception(f"{__name__} Parent zone {parent_zone} is not with in bbox: {bbox} at zone level {zone_level}")
        # TODO: compact zones
        zones_geometry = [self._generateZoneGeometry(z, False if (returngeometry == 'zone-region') else True) for z in zones_list]
        returnedAreaMetersSquare = [healpix_zone_statistics[zone_level]['area']] * len(zones_list)
        zones_list = self.zone_id_to_textual(zones_list, "int")
        return DGGRSProviderZonesListReturn(**{'zones': zones_list,
                                               'geometry': zones_geometry,
                                               'returnedAreaMetersSquare': returnedAreaMetersSquare})

    def _nestedindex_generateZoneGeometry(self, zoneId: int, refinement_level: int, centroids: bool = False) -> GeoJSONPoint | GeoJSONPolygon | None:
        if centroids:
            lon, lat = healpix_geo.nested.healpix_to_lonlat(np.array([zoneId]), refinement_level, self.ellipsoid)

            return GeoJSONPoint(type="Point", coordinates=(lon[0][0], lat[0][1]))
        else:
            lon, lat = healpix_geo.nested.vertices([zoneId], refinement_level, self.ellipsoid)
            vertices = np.squeeze(np.stack([lon, lat], axis=-1))
            coordinates = []
            for i in range(vertices.shape[0]):
                coordinates.append((vertices[i][0], vertices[i][1]))
            # to make the polygon a closed linestring
            coordinates.append((vertices[0][0], vertices[0][1]))
            return GeoJSONPolygon(type="Polygon", coordinates=[coordinates])

    def _generateZoneGeometry(self, zoneId: int, centroids: bool = False) -> GeoJSONPoint | GeoJSONPolygon | None:
        if centroids:
            lon, lat = healpix_geo.zuniq.healpix_to_lonlat(np.array([zoneId]), self.ellipsoid)
            return GeoJSONPoint(type="Point", coordinates=(lon[0][0], lat[0][1]))
        else:
            lon, lat = healpix_geo.zuniq.vertices([zoneId], self.ellipsoid)
            vertices = np.squeeze(np.stack([lon, lat], axis=-1))
            coordinates = []
            for i in range(vertices.shape[0]):
                coordinates.append((vertices[i][0], vertices[i][1]))
            # to make the polygon a closed linestring
            coordinates.append((vertices[0][0], vertices[0][1]))
            return GeoJSONPolygon(type="Polygon", coordinates=[coordinates])

