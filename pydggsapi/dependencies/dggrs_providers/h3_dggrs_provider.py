# here should be DGGRID related functions and methods
# DGGRID ISEA7H resolutions
from pydggsapi.dependencies.dggrs_providers.abstract_dggrs_provider import AbstractDGGRSProvider, conversion_properties
from pydggsapi.dependencies.dggrs_providers.igeo7_dggrs_provider import IGEO7Provider

from pydggsapi.schemas.common_geojson import GeoJSONPolygon, GeoJSONPoint
from pydggsapi.schemas.api.dggrs_providers import DGGRSProviderZoneInfoReturn, DGGRSProviderZonesListReturn
from pydggsapi.schemas.api.dggrs_providers import DGGRSProviderConversionReturn, DGGRSProviderGetRelativeZoneLevelsReturn, DGGRSProviderZonesElement

import logging
from typing import Union, List, Any
import time
import shapely
import h3
import json
import numpy as np
import geopandas as gpd
import pandas as pd
from shapely.geometry import box

logger = logging.getLogger()


class H3Provider(AbstractDGGRSProvider):

    def __init__(self):
        igeo7_conversion_properties = conversion_properties(zonelevel_offset=-2)
        self.dggrs_conversion = {'igeo7': igeo7_conversion_properties}

    def convert(self, zoneIds: list, targetdggrs: str):
        if (targetdggrs in self.dggrs_conversion):
            if (targetdggrs == 'igeo7'):
                igeo7 = IGEO7Provider()
                res_list = [[h3.cell_area(id_), self._cell_to_shapely(id_, 'zone-region')] for id_ in zoneIds]
                for i, area in enumerate(res_list):
                    for k, v in igeo7.data.items():
                        if (area[0] > v['Area (km^2)']):
                            res_list[i][0] = k
                            break
                v_ids = []
                target_zoneIds = []
                target_res_list = []
                try:
                    # ~ 0.05s for one iter with using actualdggrs.zoneslist
                    # ~ 0.03s for one iter with using get centriod method. (1s reduced in total for 49 zones)
                    for i, res in enumerate(res_list):
                        r = igeo7.generate_hexcentroid(shapely.box(*res[1].bounds), res[0])
                        selection = [shapely.within(g, res[1]) for g in r['geometry']]
                        selection = [r.iloc[j]['name'] for j in range(len(selection)) if (selection[j] == True)]
                        target_zoneIds += selection
                        v_ids += [zoneIds[i]] * len(selection)
                        target_res_list += [res[0]] * len(selection)
                except Exception as e:
                    logger.error(f'{__name__} forward transform failed : {e}')
                    raise Exception(f'{__name__} forward transform failed : {e}')
                if (len(np.unique(target_zoneIds)) < len(np.unique(zoneIds))):
                    logger.warn(f'{__name__} forward transform: unique h3 zones id > unique igeo7 zones id ')
                return DGGRSProviderConversionReturn(zoneIds=v_ids, target_zoneIds=target_zoneIds, target_res=target_res_list)
        else:
            raise Exception(f"{__name__} conversion to {targetdggrs} not supported.")

    def get_zone_level_by_cls(self, cls_km) -> int:
        for i in range(0, 16):
            length = h3.average_hexagon_edge_length(i, unit='km')
            if (length < cls_km):
                return i

    def get_cells_zone_level(self, cellIds: list) -> List[int]:
        zoneslevel = []
        try:
            for c in cellIds:
                zoneslevel.append(h3.get_resolution(c))
            return zoneslevel
        except Exception as e:
            logger.error(f'{__name__} zone id {cellIds} failed: {e}')
            raise Exception(f'{__name__} zone id {cellIds} failed: {e}')

    def get_relative_zonelevels(self, cellId: Any, base_level: int, zone_levels: List[int],
                                geometry="zone-region") -> DGGRSProviderGetRelativeZoneLevelsReturn:
        children = {}
        geometry = geometry.lower()
        geojson = GeoJSONPolygon if (geometry == 'zone-region') else GeoJSONPoint
        try:
            for z in zone_levels:
                children_ids = h3.cell_to_children(cellId, z)
                children_geometry = [self._cell_to_shapely(id_, geometry) for id_ in children_ids]
                children_geometry = [geojson(**shapely.geometry.mapping(g)) for g in children_geometry]
                children[z] = DGGRSProviderZonesElement(**{'zoneIds': children_ids,
                                                           'geometry': children_geometry})
        except Exception as e:
            logger.error(f'{__name__} get_relative_zonelevels, get children failed {e}')
            raise Exception(f'{__name__} get_relative_zonelevels, get children failed {e}')

        return DGGRSProviderGetRelativeZoneLevelsReturn(relative_zonelevels=children)

    def zoneslist(self, bbox: Union[box, None], zone_level: int, parent_zone: Union[str, int, None],
                  returngeometry: str, compact=True) -> DGGRSProviderZonesListReturn:
        if (bbox is not None):
            try:
                zoneIds = h3.h3shape_to_cells_experimental(h3.geo_to_h3shape(bbox), zone_level, contain='overlap')
                geometry = [self._cell_to_shapely(z, returngeometry) for z in zoneIds]
                hex_gdf = gpd.GeoDataFrame({'zoneIds': zoneIds}, geometry=geometry, crs='wgs84').set_index('zoneIds')
            except Exception as e:
                logger.error(f'{__name__} query zones list, bbox: {bbox} failed :{e}')
                raise Exception(f"{__name__} query zones list, bbox: {bbox} failed {e}")
            logger.info(f'{__name__} query zones list, number of hexagons: {len(hex_gdf)}')
        if (parent_zone is not None):
            try:
                children_zoneIds = h3.cell_to_children(parent_zone, zone_level)
                children_geometry = [self._cell_to_shapely(z, returngeometry) for z in children_zoneIds]
                children_hex_gdf = gpd.GeoDataFrame({'zoneIds': children_zoneIds}, geometry=children_geometry, crs='wgs84').set_index('zoneIds')
                hex_gdf = hex_gdf.join(children_hex_gdf, how='inner', rsuffix='_p') if (bbox is not None) else children_hex_gdf
            except Exception as e:
                logger.error(f'{__name__} query zones list, parent_zone: {parent_zone} get children failed {e}')
                raise Exception(f'parent_zone: {parent_zone} get children failed {e}')
        if (len(hex_gdf) == 0):
            raise Exception(f"{__name__} Parent zone {parent_zone} is not with in bbox: {bbox} at zone level {zone_level}")
        if (compact):
            compactIds = h3.compact_cells(hex_gdf.index.values)
            geometry = [self._cell_to_shapely(z, returngeometry) for z in compactIds]
            hex_gdf = gpd.GeoDataFrame({'zoneIds': compactIds}, geometry=geometry, crs='wgs84').set_index('zoneIds')
            logger.info(f'{__name__} query zones list, compact : {len(hex_gdf)}')
        area = [h3.cell_area(z, 'm^2') for z in hex_gdf.index.values]
        geotype = GeoJSONPolygon if (returngeometry == 'zone-region') else GeoJSONPoint
        geometry = [geotype(**eval(shapely.to_geojson(g))) for g in hex_gdf['geometry'].values.tolist()]
        hex_gdf.reset_index(inplace=True)
        return DGGRSProviderZonesListReturn(**{'zones': hex_gdf['zoneIds'].values.astype(str).tolist(),
                                               'geometry': geometry,
                                               'returnedAreaMetersSquare': area})

    def zonesinfo(self, cellIds: list) -> DGGRSProviderZoneInfoReturn:
        centroid = []
        hex_geometry = []
        total_area = []
        try:
            zone_level = self.get_cells_zone_level([cellIds[0]])[0]
            for c in cellIds:
                centroid.append(self._cell_to_shapely(c, 'zone-centroid'))
                hex_geometry.append(self._cell_to_shapely(c, 'zone-region'))
                total_area.append(h3.cell_area(c))
        except Exception as e:
            logger.error(f'{__name__} zone id {cellIds} dggrid convert failed: {e}')
            raise Exception(f'{__name__} zone id {cellIds} dggrid convert failed: {e}')
        geometry, bbox, centroids = [], [], []
        for g in hex_geometry:
            geometry.append(GeoJSONPolygon(**eval(shapely.to_geojson(g))))
            bbox.append(list(g.bounds))
        for c in centroid:
            centroids.append(GeoJSONPoint(**eval(shapely.to_geojson(c))))
        return DGGRSProviderZoneInfoReturn(**{'zone_level': zone_level, 'shapeType': 'hexagon',
                                              'centroids': centroids, 'geometry': geometry, 'bbox': bbox,
                                              'areaMetersSquare': (sum(total_area) / len(cellIds)) * 1000000})

    # source : https://medium.com/@jesse.b.nestler/how-to-convert-h3-cell-boundaries-to-shapely-polygons-in-python-f7558add2f63
    def _cell_to_shapely(self, cellid, geometry):
        method = h3.cell_to_boundary if (geometry == 'zone-region') else h3.cell_to_latlng
        GEO = shapely.Polygon if (geometry == 'zone-region') else shapely.Point
        points = method(cellid)
        points = [points] if (geometry != 'zone-region') else points
        points = tuple(p[::-1] for p in points)
        return GEO(points)



