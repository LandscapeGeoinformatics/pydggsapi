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
from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import ZoneGeometryType

import shapely
import logging
from dggal import Application, pydggal_setup, CRS, ogc, epsg, GeoExtent, Array, GeoPoint
from dggal import IVEA7H, ISEA7H_Z7, rHEALPix, HEALPix
from typing import Any, List, Union

logger = logging.getLogger()
supported_grids = {'IVEA7H': IVEA7H,
                   'RHEALPIX': rHEALPix,
                   'ISEA7H_Z7': ISEA7H_Z7,
                   'HEALPIX': HEALPix}


# helper function to generate geometry geojson of a zoneId
def generateZoneGeometry(dggrs, zone, crs=None, centroids: bool = False) -> GeoJSONPoint | GeoJSONPolygon | None:
    if (crs is None) or crs == CRS(ogc, 84) or crs == CRS(epsg, 4326):
        if centroids:
            centroid = dggrs.getZoneWGS84Centroid(zone)
            return GeoJSONPoint(type="Point", coordinates=(centroid.lon.value, centroid.lat.value))
        else:
            vertices = dggrs.getZoneRefinedWGS84Vertices(zone, 0)
            coordinates = []
            if vertices:
                for i in range(vertices.count):
                    coordinates.append((vertices[i].lon, vertices[i].lat))
                # to make the polygon a closed linestring
                coordinates.append((vertices[0].lon, vertices[0].lat))
                return GeoJSONPolygon(type="Polygon", coordinates=[coordinates])
            return None

    else:
        if centroids:
            centroid = dggrs.getZoneCRSCentroid(zone, crs)
            return GeoJSONPoint(type="Point", coordinates=(centroid.lon.value, centroid.lat.value))
        else:
            vertices = dggrs.getZoneRefinedCRSVertices(zone, crs, 0)
            coordinates = []
            if vertices:
                for i in range(vertices.count):
                    coordinates.append((vertices[i].x.value, vertices[i].y.value))
                return GeoJSONPolygon(type="Polygon", coordinates=[coordinates])
            return None


def generateZoneExtent(dggrs, zoneId):
    geoextent = GeoExtent()
    dggrs.getZoneWGS84Extent(zoneId, geoextent)
    minx, miny, maxx, maxy = geoextent.ll.lon.value, geoextent.ll.lat.value, geoextent.ur.lon.value, geoextent.ur.lat.value
    extent = shapely.box(minx, miny, maxx, maxy)
    return extent


class DGGALProvider(AbstractDGGRSProvider):
    def __init__(self, **params):
        self.app = Application(appGlobals=globals())
        pydggal_setup(self.app)
        self.grid_name = params.get('grid', 'IVEA7H').upper()
        try:
            self.mygrid = supported_grids[self.grid_name]()
        except KeyError:
            logger.error(f'{__name__} grid: {self.grid_name} not supported')
            raise Exception(f'{__name__} grid: {self.grid_name} not supported')

    def convert(self, zoneIds: List[str], targedggrs: str,
                zone_id_repr: ZoneIdRepresentationType = 'textual') -> DGGRSProviderConversionReturn:
        raise NotImplementedError

    def zone_id_from_textual(self, cellIds: List[str], zone_id_repr: str) -> List[Any]:
        if (len(cellIds) == 0):
            return []
        if (zone_id_repr == "textual"):
            return cellIds
        if (zone_id_repr == "int"):
            return [self.mygrid.getZoneFromTextID(z) for z in cellIds]
        if (zone_id_repr == "hexstring"):
            raise ValueError("{__name__} dggal doesn't support hexstring zone id representation")

    def zone_id_to_textual(self, cellIds: List[Any], zone_id_repr: str) -> List[str]:
        if (len(cellIds) == 0):
            return []
        if (zone_id_repr == "textual"):
            return cellIds
        if (zone_id_repr == "int"):
            # get_data return zone id in string format
            if (isinstance(cellIds[0], str)):
                return [self.mygrid.getZoneTextID(int(z)) for z in cellIds]
            else:
                return [self.mygrid.getZoneTextID(z) for z in cellIds]
        if (zone_id_repr == "hexstring"):
            raise ValueError("{__name__} dggal doesn't support hexstring zone id representation")

    def get_cls_by_zone_level(self, zone_level: int) -> float:
        return self.mygrid.getMetersPerSubZoneFromLevel(zone_level, 0)

    def get_zone_level_by_cls(self, cls_km: float):
        return self.mygrid.getLevelFromMetersPerSubZone(cls_km * 1000, 0)

    def get_cells_zone_level(self, cellIds: List[str]) -> List[int]:
        cellId = self.mygrid.getZoneFromTextID(cellIds[0])
        return [self.mygrid.getZoneLevel(cellId)]

    def get_relative_zonelevels(self, cellId: str, base_level: int, zone_levels: List[int],
                                geometry: ZoneGeometryType = 'zone-region') -> DGGRSProviderGetRelativeZoneLevelsReturn:
        children = {}
        geometry = geometry.lower()
        #geojson = GeoJSONPolygon if (geometry == 'zone-region') else GeoJSONPoint
        cellId = self.mygrid.getZoneFromTextID(cellId)
        for z in zone_levels:
            subzoneIds = self.mygrid.getSubZones(cellId, (z - base_level))
            subzones_geometry = [generateZoneGeometry(self.mygrid, cellId, None, False if (geometry == 'zone-region') else True)
                               for cellId in subzoneIds]
            subzoneIds = [self.mygrid.getZoneTextID(id_) for id_ in subzoneIds]
            #subzones_geometry = [geojson(**shapely.geometry.mapping(g)) for g in subzones_geometry]
            children[z] = DGGRSProviderZonesElement(**{'zoneIds': subzoneIds,
                                                       'geometry': subzones_geometry})
        return DGGRSProviderGetRelativeZoneLevelsReturn(relative_zonelevels=children)

    def zonesinfo(self, cellIds: List[str]) -> DGGRSProviderZoneInfoReturn:
        zone_level = self.get_cells_zone_level(cellIds)[0]
        cellIds = [self.mygrid.getZoneFromTextID(cellId) for cellId in cellIds]
        try:
            centroids = [generateZoneGeometry(self.mygrid, cellId, None, True)
                         for cellId in cellIds]
            #centroids = [GeoJSONPoint(**eval(shapely.to_geojson(c))) for c in centroids]
            hex_vertices = [generateZoneGeometry(self.mygrid, cellId, None, False)
                            for cellId in cellIds]
            #hex_vertices = [GeoJSONPolygon(**eval(shapely.to_geojson(g))) for g in hex_vertices]
            extents = [generateZoneExtent(self.mygrid, cellId) for cellId in cellIds]
            extents = [b.bounds for b in extents]
        except Exception as e:
            logger.error(f'{__name__} zone id {cellIds} convert failed, {e}')
            raise Exception(f'{__name__} zone id {cellIds} convert failed, {e}')
        return DGGRSProviderZoneInfoReturn(**{'zone_level': zone_level, 'shapeType': 'hexagon',
                                              'centroids': centroids, 'geometry': hex_vertices, 'bbox': extents,
                                              'areaMetersSquare': self.mygrid.getRefZoneArea(zone_level)})

    def zoneslist(self, bbox: Union[shapely.box, None], zone_level: int, parent_zone: Union[str, int, None],
                  returngeometry: ZoneGeometryType, compact: bool = True) -> List[str]:
        if (bbox is not None):
            try:
                bbox = shapely.bounds(bbox)
                geoextent = GeoExtent(GeoPoint(bbox[1], bbox[0]), GeoPoint(bbox[3], bbox[2]))
                zones_list = self.mygrid.listZones(zone_level, geoextent)
                zones_list = set(int(z) for z in zones_list)
            except Exception as e:
                logger.error(f'{__name__} query zones list, bbox: {bbox} dggrid convert failed :{e}')
                raise Exception(f"{__name__} query zones list, bbox: {bbox} dggrid convert failed {e}")
            logger.info(f'{__name__} query zones list, number of hexagons: {len(zones_list)}')
        if (parent_zone is not None):
            try:
                parent_zone_level = self.get_cells_zone_level([parent_zone])[0]
                parent_zone = self.mygrid.getZoneFromTextID(parent_zone)
                subzones_list = self.mygrid.getSubZones(parent_zone, (zone_level - parent_zone_level))
                subzones_list = set(int(z) for z in subzones_list)
                zones_list = (zones_list & subzones_list) if (bbox is not None) else subzones_list
            except Exception as e:
                logger.error(f'{__name__} query zones list, parent_zone: {parent_zone} get children failed {e}')
                raise Exception(f'parent_zone: {parent_zone} get children failed {e}')
        if (len(zones_list) == 0):
            raise Exception(f"{__name__} Parent zone {parent_zone} is not with in bbox: {bbox} at zone level {zone_level}")
        if (compact):
            compact_list = Array("<DGGRSZone>")
            [compact_list.add(int(z)) for z in zones_list]
            self.mygrid.compactZones(compact_list)
            zones_list = [int(z) for z in compact_list]
            logger.info(f'{__name__} query zones list, compact : {len(zones_list)}')
        zones_geometry = [generateZoneGeometry(self.mygrid, z, None, False if (returngeometry == 'zone-region') else True) for z in zones_list]
        returnedAreaMetersSquare = [self.mygrid.getZoneArea(z) for z in zones_list]
        zones_list = [self.mygrid.getZoneTextID(z) for z in zones_list]
        return DGGRSProviderZonesListReturn(**{'zones': zones_list,
                                               'geometry': zones_geometry,
                                               'returnedAreaMetersSquare': returnedAreaMetersSquare})
