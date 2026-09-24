from pydggsapi.dependencies.dggrs_providers.abstract_dggrs_provider import AbstractDGGRSProvider, ZoneIdRepresentationType, conversion_properties
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
# - healpix-geo doesn't support textural zone id representation,
#   so I assume the input zone id is just the uint64 in str format
# - from the discussion in https://github.com/opengeospatial/ogcapi-discrete-global-grid-systems/issues/110
#   the textual ZIRS of the nested index should be in the form of "{refinement level}_{nested index}".


supported_indexing_schema = ["zuniq", "nested"]
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


class HealpixGeoNestedProvider(AbstractDGGRSProvider):
    def __init__(self, **params):
        self.indexing_schema = "nested"
        self.ellipsoid = params.get("ellipsoid", "wgs84").lower()
        if (self.ellipsoid not in supported_ellipsoid):
            raise ValueError(f"{__name__} {self.ellipsoid} not supported")
        self.ellipsoid = self.ellipsoid.upper()

    def convert(self, zoneIds: List[str], targedggrs: str,
                zone_id_repr: ZoneIdRepresentationType = 'textual') -> DGGRSProviderConversionReturn:
        raise NotImplementedError

    # the textual ZIRS of the nested index should be in the form of "{refinement level}_{nested index}".
    def zone_id_from_textual(self, cellIds: List[str], zone_id_repr: str) -> List[Any]:
        if (zone_id_repr not in get_args(ZoneIdRepresentationType)):
            raise ValueError("{__name__} {zone_id_repr} representation is not supported.")
        if (len(cellIds) == 0):
            return []
        if (zone_id_repr == "textual"):
            return cellIds
        if (zone_id_repr == "int"):
            cellIds = list(map(lambda x: x.split("_")[1], cellIds))
            cellIds = [int(cell_id) for cell_id in cellIds]
            return cellIds
        if (zone_id_repr == "hexstring"):
            raise ValueError("{__name__} doesn't support hexstring zone id representation")

    # the textual ZIRS of the nested index should be in the form of "{refinement level}_{nested index}".
    def zone_id_to_textual(self, cellIds: List[Any], zone_id_repr: str, refinement_level=None) -> List[str]:
        if (zone_id_repr not in get_args(ZoneIdRepresentationType)):
            raise ValueError("{__name__} {zone_id_repr} representation is not supported.")
        if (len(cellIds) == 0):
            return []
        if (zone_id_repr == "textual"):
            return cellIds
        if (zone_id_repr == "int"):
            # get_data return zone id in string format
            cellIds = list(map(lambda x: str(refinement_level).zfill(2) + "_" + str(x), cellIds))
            return cellIds
        if (zone_id_repr == "hexstring"):
            raise ValueError("{__name__} doesn't support hexstring zone id representation")

    def get_cls_by_zone_level(self, zone_level: int) -> float:
        return healpix_zone_statistics[zone_level]["cls"]

    def get_zone_level_by_cls(self, cls_km: float):
        for k, v in healpix_zone_statistics.items():
            if (v["cls"] < cls_km * 1000):
                return k

    # the textual ZIRS of the nested index should be in the form of "{refinement level}_{nested index}".
    def get_cells_zone_level(self, cellIds: List[str]) -> List[int]:
        refinement_level_str = list(map(lambda x: x.split("_")[0], cellIds))
        depth = [int(rf) for rf in refinement_level_str]
        return depth

    def get_relative_zonelevels(self, cellId: str, base_level: int, zone_levels: List[int],
                                geometry: Optional[ReturnGeometryTypes] = 'zone-region') -> DGGRSProviderGetRelativeZoneLevelsReturn:
        children = {}
        geometry = geometry.lower() if (geometry is not None) else geometry
        cellId = self.zone_id_from_textual([cellId], "int")
        for z in zone_levels:
            # it return an N x childen array where N is the number of parents
            # so we get the only element from the return as the get_relative_zonelevels is for a single cell.
            subzoneIds = healpix_geo.nested.zoom_to(cellId, base_level, z)[0]
            subzones_geometry = None
            if (geometry is not None):
                subzones_geometry = self._generateZoneGeometries(subzoneIds, z, False if (geometry == 'zone-region') else True)
            subzoneIds = self.zone_id_to_textual(subzoneIds.tolist(), "int", z)
            children[z] = DGGRSProviderZonesElement(**{'zoneIds': subzoneIds,
                                                       'geometry': subzones_geometry})
        return DGGRSProviderGetRelativeZoneLevelsReturn(relative_zonelevels=children)

    def zonesinfo(self, cellIds: List[str]) -> DGGRSProviderZoneInfoReturn:
        zone_level = self.get_cells_zone_level(cellIds)[0]
        cellIds = self.zone_id_from_textual(cellIds, "int")
        try:
            centroids = self._generateZoneGeometries([cellIds], zone_level, True)
            square_vertices = self._generateZoneGeometries([cellIds], zone_level, False)
            extents = [shapely.geometry.shape(geojson.__dict__) for geojson in square_vertices]
            extents = [b.bounds for b in extents]
        except Exception as e:
            logger.error(f'{__name__} zone id {cellIds} convert failed, {e}')
            raise Exception(f'{__name__} zone id {cellIds} convert failed, {e}')
        return DGGRSProviderZoneInfoReturn(**{'zone_level': zone_level, 'shapeType': 'rhombus',
                                              'centroids': centroids, 'geometry': square_vertices, 'bbox': extents,
                                              'areaMetersSquare': zone_level})

    def zoneslist(self, bbox: Union[shapely.box, None], zone_level: int, parent_zone: Union[str, int, None],
                  returngeometry: ReturnGeometryTypes, compact: bool = True) -> List[str]:
        if (bbox is not None):
            try:
                bbox = shapely.bounds(bbox)
                zones_list, _, _ = healpix_geo.nested.zone_coverage(tuple(bbox.tolist()), zone_level, ellipsoid=self.ellipsoid, flat=False)
                zones_list = set(zones_list)
            except Exception as e:
                logger.error(f'{__name__} query zones list, bbox: {bbox} convert failed :{e}')
                raise Exception(f"{__name__} query zones list, bbox: {bbox} convert failed {e}")
            logger.info(f'{__name__} query zones list, number of cells: {len(zones_list)}')
        if (parent_zone is not None):
            try:
                parent_zone_level = self.get_cells_zone_level([parent_zone])[0]
                parent_zone = self.zone_id_from_textual([parent_zone], "int")
                subzones_list = set(healpix_geo.nested.zoom_to(parent_zone, parent_zone_level, zone_level)[0])
                zones_list = (zones_list & subzones_list) if (bbox is not None) else subzones_list
            except Exception as e:
                logger.error(f'{__name__} query zones list, parent_zone: {parent_zone} get children failed {e}')
                raise Exception(f'parent_zone: {parent_zone} get children failed {e}')
        if (len(zones_list) == 0):
            raise Exception(f"{__name__} Parent zone {parent_zone} is not with in bbox: {bbox} at zone level {zone_level}")
        # TODO: compact zones
        zones_geometry = None
        if (returngeometry is not None):
            zones_geometry = self._generateZoneGeometries(list(zones_list), zone_level, False if (returngeometry == 'zone-region') else True)
        returnedAreaMetersSquare = [healpix_zone_statistics[zone_level]['area']] * len(zones_list)
        zones_list = self.zone_id_to_textual(zones_list, "int", zone_level)
        return DGGRSProviderZonesListReturn(**{'zones': zones_list,
                                               'geometry': zones_geometry,
                                               'returnedAreaMetersSquare': returnedAreaMetersSquare})

    def _generateZoneGeometries(self, zoneIds: List[int], refinement_level: int, centroids: bool = False) -> GeoJSONPoint | GeoJSONPolygon | None:
        if centroids:
            lon, lat = healpix_geo.nested.healpix_to_lonlat(zoneIds, refinement_level, self.ellipsoid)
            points = np.stack([lon, lat], axis=-1)
            # for list only consist of one zone, the shape of vertices is [1, 1, 2]
            if (len(zoneIds) == 1):
                points = np.squeeze(points, axis=1)
            points = list(map(lambda x: GeoJSONPoint(type="Point", coordinates=(x[0], x[1])), points))
            return points
        else:
            lon, lat = healpix_geo.nested.vertices(zoneIds, refinement_level, self.ellipsoid)
            vertices = np.stack([lon, lat], axis=-1)
            vertices = np.squeeze(vertices.view(dtype=np.dtype([('x', 'float64'), ('y', 'float64')])), axis=-1)
            # for list only consist of one zone, the shape of vertices is [1, 1, 4]
            if (len(zoneIds) == 1):
                vertices = np.squeeze(vertices, axis=1)
            polygon = list(map(lambda x: GeoJSONPolygon(type="Polygon", coordinates=[x.tolist()]), vertices))
            return polygon


class HealpixGeoZuniqProvider(AbstractDGGRSProvider):
    def __init__(self, **params):
        self.indexing_schema = "zuniq"
        self.ellipsoid = params.get("ellipsoid", "wgs84").lower()
        if (self.ellipsoid not in supported_ellipsoid):
            raise ValueError(f"{__name__} {self.ellipsoid} not supported")
        self.support_conversion = params.get("support_conversion", {})
        self.ellipsoid = self.ellipsoid.upper()
        self.dggrs_conversion = {dggrsid: conversion_properties(**conversion_param)
                                 for dggrsid, conversion_param in self.support_conversion.items()}

    def convert(self, zoneIds: List[str], targetdggrs: str,
                zone_id_repr: ZoneIdRepresentationType = 'textual') -> DGGRSProviderConversionReturn:
        if (targetdggrs not in self.dggrs_conversion.keys()):
            raise Exception(f"{__name__} conversion to {targetdggrs} not supported.")
        else:
            # in the case of healpix, conversion from zuniq index to nested is a 1-to-1 mapping.
            nestedIds, refinement_level = healpix_geo.zuniq.to_nested(zoneIds)
            nestedIds, refinement_level = nestedIds.tolist(), refinement_level.tolist()
            if (zone_id_repr == 'textual'):
                nestedIds = list(map(lambda x: f"{refinement_level[x]}_{nestedIds[x]}",
                                     range(len(nestedIds))))
            return DGGRSProviderConversionReturn(zoneIds=zoneIds, target_zoneIds=nestedIds,
                                                 target_res=refinement_level)

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
        nested_cellId, nested_rf = healpix_geo.zuniq.to_nested(cellId)
        nested_cellId, nested_rf = nested_cellId[0], nested_rf[0]
        for z in zone_levels:
            # it return an N x childen array where N is the number of parents
            # so we get the only element from the return as the get_relative_zonelevels is for a single cell.
            subzone_nestedIds = healpix_geo.nested.zoom_to(nested_cellId, nested_rf, z)[0]
            subzones_geometry = None
            # convert those subzone cell id from nested back to zuniq
            subzoneIds = healpix_geo.nested.to_zuniq(subzone_nestedIds, z)
            if (geometry is not None):
                subzones_geometry = self._generateZoneGeometries(subzoneIds, False if (geometry == 'zone-region') else True)
            subzoneIds = self.zone_id_to_textual(subzoneIds.tolist(), "int")
            children[z] = DGGRSProviderZonesElement(**{'zoneIds': subzoneIds,
                                                       'geometry': subzones_geometry})
        return DGGRSProviderGetRelativeZoneLevelsReturn(relative_zonelevels=children)

    def zonesinfo(self, cellIds: List[str]) -> DGGRSProviderZoneInfoReturn:
        zone_level = self.get_cells_zone_level(cellIds)[0]
        cellIds = self.zone_id_from_textual(cellIds, "int")
        try:
            centroids = self._generateZoneGeometries([cellIds], True)
            square_vertices = self._generateZoneGeometries([cellIds], False)
            extents = [shapely.geometry.shape(geojson.__dict__) for geojson in square_vertices]
            extents = [b.bounds for b in extents]
        except Exception as e:
            logger.error(f'{__name__} zone id {cellIds} convert failed, {e}')
            raise Exception(f'{__name__} zone id {cellIds} convert failed, {e}')
        return DGGRSProviderZoneInfoReturn(**{'zone_level': zone_level, 'shapeType': 'rhombus',
                                              'centroids': centroids, 'geometry': square_vertices, 'bbox': extents,
                                              'areaMetersSquare': zone_level})

    def zoneslist(self, bbox: Union[shapely.box, None], zone_level: int, parent_zone: Union[str, int, None],
                  returngeometry: ReturnGeometryTypes, compact: bool = True) -> List[str]:
        if (bbox is not None):
            try:
                bbox = shapely.bounds(bbox)
                zones_list, _ = healpix_geo.zuniq.zone_coverage(tuple(bbox.tolist()), zone_level, ellipsoid=self.ellipsoid, flat=False)
                zones_list = set(zones_list)
            except Exception as e:
                logger.error(f'{__name__} query zones list, bbox: {bbox} convert failed :{e}')
                raise Exception(f"{__name__} query zones list, bbox: {bbox} convert failed {e}")
            logger.info(f'{__name__} query zones list, number of cells: {len(zones_list)}')
        if (parent_zone is not None):
            try:
                parent_zone_nested, parent_zone_level = healpix_geo.zuniq.to_nested(parent_zone)
                subzones_list = healpix_geo.nested.zoom_to(parent_zone_nested,
                                                           parent_zone_level[0], zone_level)[0]
                subzones_list = set(healpix_geo.nested.to_zuniq(subzones_list, zone_level))
                zones_list = (zones_list & subzones_list) if (bbox is not None) else subzones_list
            except Exception as e:
                logger.error(f'{__name__} query zones list, parent_zone: {parent_zone} get children failed {e}')
                raise Exception(f'parent_zone: {parent_zone} get children failed {e}')
        if (len(zones_list) == 0):
            raise Exception(f"{__name__} Parent zone {parent_zone} is not with in bbox: {bbox} at zone level {zone_level}")
        # TODO: compact zones
        zones_geometry = None
        if (returngeometry is not None):
            zones_geometry = self._generateZoneGeometries(list(zones_list), False if (returngeometry == 'zone-region') else True)
        returnedAreaMetersSquare = [healpix_zone_statistics[zone_level]['area']] * len(zones_list)
        zones_list = self.zone_id_to_textual(zones_list, "int", zone_level)
        return DGGRSProviderZonesListReturn(**{'zones': zones_list,
                                               'geometry': zones_geometry,
                                               'returnedAreaMetersSquare': returnedAreaMetersSquare})

    def _generateZoneGeometries(self, zoneIds: List[int], centroids: bool = False) -> GeoJSONPoint | GeoJSONPolygon | None:
        if centroids:
            lon, lat = healpix_geo.zuniq.healpix_to_lonlat(zoneIds, self.ellipsoid)
            points = np.stack([lon, lat], axis=-1)
            # for list only consist of one zone, the shape of vertices is [1, 1, 2]
            if (len(zoneIds) == 1):
                points = np.squeeze(points, axis=1)
            points = list(map(lambda x: GeoJSONPoint(type="Point", coordinates=(x[0], x[1])), points))
            return points
        else:
            lon, lat = healpix_geo.zuniq.vertices(zoneIds, self.ellipsoid)
            vertices = np.stack([lon, lat], axis=-1)
            vertices = np.squeeze(vertices.view(dtype=np.dtype([('x', 'float64'), ('y', 'float64')])), axis=-1)
            # for list only consist of one zone, the shape of vertices is [1, 1, 4]
            if (len(zoneIds) == 1):
                vertices = np.squeeze(vertices, axis=1)
            polygon = list(map(lambda x: GeoJSONPolygon(type="Polygon", coordinates=[x.tolist()]), vertices))
            return polygon

