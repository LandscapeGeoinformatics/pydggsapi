# here should be DGGRID related functions and methods
# DGGRID ISEA7H resolutions
from pydggsapi.dependencies.dggrs_providers.AbstractDGGRS import AbstractDGGRS
from pydggsapi.schemas.common_geojson import GeoJSONPolygon, GeoJSONPoint
from pydggsapi.dependencies.dggrs_providers.dggrid import IGEO7
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

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s {%(module)s} [%(funcName)s] %(message)s',
                    datefmt='%Y-%m-%d,%H:%M:%S', level=logging.INFO)


class H3(AbstractDGGRS):

    def convert(self, virtual_zoneIds: list, targedggrs: type[AbstractDGGRS]):
        res_list = [[self.virtualdggrs.cell_area(id_), self._cell_to_shapely(id_, 'zone-region')] for id_ in virtual_zoneIds]
        for i, area in enumerate(res_list):
            for k, v in self.actualdggrs.data.items():
                if (area[0] > v['Area (km^2)']):
                    res_list[i][0] = k
                    break
        v_ids = []
        actual_zoneIds = []
        actual_res_list = []
        try:
            # ~ 0.05s for one iter with using actualdggrs.zoneslist
            # ~ 0.03s for one iter with using get centriod method. (1s reduced in total for 49 zones)
            for i, res in enumerate(res_list):
                r = self.actualdggrs.generate_hexcentroid(shapely.box(*res[1].bounds), res[0])
                selection = [shapely.within(g, res[1]) for g in r['geometry']]
                selection = [r.iloc[j]['name'] for j in range(len(selection)) if (selection[j] == True)]
                actual_zoneIds += selection
                v_ids += [virtual_zoneIds[i]] * len(selection)
                actual_res_list += [res[0]] * len(selection)
        except Exception as e:
            logging.error(f'{__name__} forward transform failed : {e}')
            raise Exception(f'{__name__} forward transform failed : {e}')
        if (len(np.unique(actual_zoneIds)) < len(np.unique(virtual_zoneIds))):
            logging.warn(f'{__name__} forward transform: unique virtual zones id > unique actual zones id ')
        return DGGRSProviderConversionReturn(virtual_zoneIds=v_ids, actual_zoneIds=actual_zoneIds, actual_res=actual_res_list)

    def get_cells_zone_level(self, cellIds: list) -> List[int]:
        zoneslevel = []
        try:
            for c in cellIds:
                zoneslevel.append(self.virtualdggrs.get_resolution(c))
            return zoneslevel
        except Exception as e:
            logging.error(f'{__name__} zone id {cellIds} dggrid get zone level failed: {e}')
            raise Exception(f'{__name__} zone id {cellIds} dggrid get zone level failed: {e}')

    def get_relative_zonelevels(self, cellId: Any, base_level: int, zone_levels: List[int],
                                geometry: str) -> DGGRSProviderGetRelativeZoneLevelsReturn:
        children = {}
        geometry = geometry.lower()
        geojson = GeoJSONPolygon if (geometry == 'zone-region') else GeoJSONPoint
        try:
            for z in zone_levels:
                children_ids = self.virtualdggrs.cell_to_children(cellId, z)
                children_geometry = [self._cell_to_shapely(id_, geometry) for id_ in children_ids]
                children_geometry = [geojson(**shapely.geometry.mapping(g)) for g in children_geometry]
                children[z] = DGGRSProviderZonesElement(**{'zoneIds': children_ids,
                                                           'geometry': children_geometry})
        except Exception as e:
            logging.error(f'{__name__} get_relative_zonelevels, get children failed {e}')
            raise Exception(f'{__name__} get_relative_zonelevels, get children failed {e}')

        return DGGRSProviderGetRelativeZoneLevelsReturn(relative_zonelevels=children)

    def zoneslist(self, bbox: Union[box, None], zone_level: int, parent_zone: Union[str, int, None],
                  returngeometry: str, compact=True) -> DGGRSProviderZonesListReturn:
        if (bbox is not None):
            try:
                zoneIds = self.virtualdggrs.h3shape_to_cells(self.virtualdggrs.geo_to_h3shape(bbox), zone_level)
                geometry = [self._cell_to_shapely(z, returngeometry) for z in zoneIds]
                hex_gdf = gpd.GeoDataFrame({'zoneIds': zoneIds}, geometry=geometry, crs='wgs84').set_index('zoneIds')
            except Exception as e:
                logging.error(f'{__name__} query zones list, bbox: {bbox} dggrid convert failed :{e}')
                raise Exception(f"{__name__} query zones list, bbox: {bbox} dggrid convert failed {e}")
            logging.info(f'{__name__} query zones list, number of hexagons: {len(hex_gdf)}')
        if (parent_zone is not None):
            try:
                children_zoneIds = self.virtualdggrs.cell_to_children(parent_zone, zone_level)
                children_geometry = [self._cell_to_shapely(z, returngeometry) for z in children_zoneIds]
                children_hex_gdf = gpd.GeoDataFrame({'zoneIds': children_zoneIds}, geometry=children_geometry, crs='wgs84').set_index('zoneIds')
                hex_gdf = hex_gdf.join(children_hex_gdf, how='inner', rsuffix='_p') if (bbox is not None) else children_hex_gdf
            except Exception as e:
                logging.error(f'{__name__} query zones list, parent_zone: {parent_zone} get children failed {e}')
                raise Exception(f'parent_zone: {parent_zone} get children failed {e}')
        if (len(hex_gdf) == 0):
            raise Exception(f"{__name__} Parent zone {parent_zone} is not with in bbox: {bbox} at zone level {zone_level}")
        if (compact):
            compactIds = self.virtualdggrs.compact_cells(hex_gdf.index.values)
            geometry = [self._cell_to_shapely(z, returngeometry) for z in compactIds]
            hex_gdf = gpd.GeoDataFrame({'zoneIds': compactIds}, geometry=geometry, crs='wgs84').set_index('zoneIds')
            logging.info(f'{__name__} query zones list, compact : {len(hex_gdf)}')
        returnedAreaMetersSquare = sum([self.virtualdggrs.cell_area(z, 'm^2') for z in hex_gdf.index.values])
        geotype = GeoJSONPolygon if (returngeometry == 'zone-region') else GeoJSONPoint
        geometry = [geotype(**eval(shapely.to_geojson(g))) for g in hex_gdf['geometry'].values.tolist()]
        hex_gdf.reset_index(inplace=True)
        return DGGRSProviderZonesListReturn(**{'zones': hex_gdf['zoneIds'].values.astype(str).tolist(),
                                               'geometry': geometry,
                                               'returnedAreaMetersSquare': returnedAreaMetersSquare})

    def zonesinfo(self, cellIds: list) -> DGGRSProviderZoneInfoReturn:
        centroid = []
        hex_geometry = []
        total_area = []
        try:
            zone_level = self.get_cells_zone_level([cellIds[0]])[0]
            for c in cellIds:
                centroid.append(self._cell_to_shapely(c, 'zone-centroid'))
                hex_geometry.append(self._cell_to_shapely(c, 'zone-region'))
                total_area.append(self.virtualdggrs.cell_area(c))
        except Exception as e:
            logging.error(f'{__name__} zone id {cellIds} dggrid convert failed: {e}')
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
        method = self.virtualdggrs.cell_to_boundary if (geometry == 'zone-region') else self.virtualdggrs.cell_to_latlng
        GEO = shapely.Polygon if (geometry == 'zone-region') else shapely.Point
        points = method(cellid)
        points = [points] if (geometry != 'zone-region') else points
        points = tuple(p[::-1] for p in points)
        return GEO(points)



