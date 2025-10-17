# here should be DGGRID related functions and methods
# DGGRID ISEA7H resolutions

from pydggsapi.dependencies.dggrs_providers.abstract_dggrs_provider import AbstractDGGRSProvider
from pydggsapi.schemas.common_geojson import GeoJSONPolygon, GeoJSONPoint
from pydggsapi.schemas.api.dggrs_providers import DGGRSProviderZoneInfoReturn, DGGRSProviderZonesListReturn
from pydggsapi.schemas.api.dggrs_providers import DGGRSProviderGetRelativeZoneLevelsReturn, DGGRSProviderZonesElement

import os
import tempfile
import logging
from typing import Union, List
from dggrid4py import DGGRIDv8
import dggrid4py
import shapely
from dotenv import load_dotenv
from shapely.geometry import box
import numpy as np

logger = logging.getLogger()

load_dotenv()


class IGEO7Provider(AbstractDGGRSProvider):

    def __init__(self):
        executable = os.environ['DGGRID_PATH']
        working_dir = tempfile.mkdtemp()
        self.dggrid_instance = DGGRIDv8(executable=executable, working_dir=working_dir, silent=True)
        self.data = {
            0: {"Cells": 12, "Area (km^2)": 51006562.1724089, "CLS (km)": 8199.5003701},
            1: {"Cells": 72, "Area (km^2)": 7286651.7389156, "CLS (km)": 3053.2232428},
            2: {"Cells": 492, "Area (km^2)": 1040950.2484165, "CLS (km)": 1151.6430095},
            3: {"Cells": 3432, "Area (km^2)": 148707.1783452, "CLS (km)": 435.1531492},
            4: {"Cells": 24012, "Area (km^2)": 21243.8826207, "CLS (km)": 164.4655799},
            5: {"Cells": 168072, "Area (km^2)": 3034.8403744, "CLS (km)": 62.1617764},
            6: {"Cells": 1176492, "Area (km^2)": 433.5486249, "CLS (km)": 23.4949231},
            7: {"Cells": 8235432, "Area (km^2)": 61.9355178, "CLS (km)": 8.8802451},
            8: {"Cells": 57648012, "Area (km^2)": 8.8479311, "CLS (km)": 3.3564171},
            9: {"Cells": 403536072, "Area (km^2)": 1.2639902, "CLS (km)": 1.2686064},
            10: {"Cells": 2824752492, "Area (km^2)": 0.18057, "CLS (km)": 0.4794882},
            11: {"Cells": 19773267432, "Area (km^2)": 0.0257957, "CLS (km)": 0.1812295},
            12: {"Cells": 138412872012, "Area (km^2)": 0.0036851, "CLS (km)": 0.0684983},
            13: {"Cells": 968890104072, "Area (km^2)": 0.0005264, "CLS (km)": 0.0258899},
            14: {"Cells": 6782230728492, "Area (km^2)": 0.0000752, "CLS (km)": 0.0097855},
            15: {"Cells": 47475615099432, "Area (km^2)": 0.0000107, "CLS (km)": 0.0036986},
        }
        self.dggrs = 'IGEO7'
        self.address_params = {
            'input_address_type': 'HIERNDX',
            'input_hier_ndx_system': 'Z7',
            'input_hier_ndx_form': 'DIGIT_STRING',
            'output_address_type': 'HIERNDX',
            'output_cell_label_type': 'OUTPUT_ADDRESS_TYPE',
            'output_hier_ndx_system': 'Z7',
            'output_hier_ndx_form': 'DIGIT_STRING',
        }

    def convert(self, zoneIds: list, targedggrs: type[AbstractDGGRSProvider]):
        pass

    def get(self, zoom):
        # zoom must be integer and between 0 and 15 inclusive
        if not isinstance(zoom, int):
            raise TypeError("zoom must be integer")
        if zoom < 0 or zoom > 15:
            raise ValueError("zoom must be between 0 and 15 inclusive")

        return self.data[zoom]

    def generate_hexgrid(self, bbox, resolution):
        # ISEA7H grid at resolution, for extent of provided WGS84 rectangle into GeoDataFrame
        gdf = self.dggrid_instance.grid_cell_polygons_for_extent(self.dggrs, resolution, clip_geom=bbox, **self.address_params)
        return gdf

    def generate_hexcentroid(self, bbox, resolution):
        # ISEA7H grid at resolution, for extent of provided WGS84 rectangle into GeoDataFrame
        gdf = self.dggrid_instance.grid_cell_centroids_for_extent(self.dggrs, resolution, clip_geom=bbox, **self.address_params)
        return gdf

    def centroid_from_cellid(self, cellid: list, zone_level):
        gdf = self.dggrid_instance.grid_cell_centroids_from_cellids(cellid, self.dggrs, zone_level, **self.address_params)
        return gdf

    def hexagon_from_cellid(self, cellid: list, zone_level):
        gdf = self.dggrid_instance.grid_cell_polygons_from_cellids(cellid, self.dggrs, zone_level, **self.address_params)
        return gdf

    def cellid_from_centroid(self, geodf_points_wgs84, zoomlevel):
        gdf = self.dggrid_instance.cells_for_geo_points(geodf_points_wgs84, True, self.dggrs, zoomlevel, **self.address_params)
        return gdf

    def cellids_from_extent(self, clip_geom, zoomlevel):
        gdf = self.dggrid_instance.grid_cellids_for_extent(self.dggrs, zoomlevel, clip_geom=clip_geom, **self.address_params)
        return gdf

    def get_zone_level_by_cls(self, cls_km: float):
        for k, v in self.data.items():
            if v["CLS (km)"] < cls_km:
                return k

    def get_cells_zone_level(self, cellIds: List[str]):
        try:
            zones_level = dggrid4py.igeo7.get_z7string_resolution(cellIds[0])
            return [zones_level]
        except Exception as e:
            logger.error(f'{__name__} zone id {cellIds} dggrid get zone level failed : {e}')
            raise Exception(f'{__name__} zone id {cellIds} dggrid get zone level failed')

    def get_relative_zonelevels(self, cellId: str, base_level: int, zone_levels: List[int], geometry='zone-region'):
        children = {}
        geometry = geometry.lower()
        method = self.dggrid_instance.grid_cell_polygons_from_cellids if (geometry == 'zone-region') else self.dggrid_instance.grid_cell_centroids_from_cellids
        geojson = GeoJSONPolygon if (geometry == 'zone-region') else GeoJSONPoint
        try:
            for z in zone_levels:
                gdf = method([cellId], self.dggrs, z, clip_subset_type='COARSE_CELLS', clip_cell_res=base_level,
                             **self.address_params)
                g = [geojson(**shapely.geometry.mapping(g)) for g in gdf['geometry'].values.tolist()]
                children[z] = DGGRSProviderZonesElement(**{'zoneIds': gdf['name'].astype(str).values.tolist(),
                                                           'geometry': g})

        except Exception as e:
            logger.error(f'{__name__} get_relative_zonelevels, get children failed {e}')
            raise Exception(f'{__name__} get_relative_zonelevels, get children failed {e}')

        return DGGRSProviderGetRelativeZoneLevelsReturn(relative_zonelevels=children)

    def zonesinfo(self, cellIds: List[str]):
        zone_level = dggrid4py.igeo7.get_z7string_resolution(cellIds[0])
        try:
            centroid = self.centroid_from_cellid(cellIds, zone_level).geometry
            hex_geometry = self.hexagon_from_cellid(cellIds, zone_level).geometry
        except Exception:
            logger.error(f'{__name__} zone id {cellIds} dggrid convert failed')
            raise Exception(f'{__name__} zone id {cellIds} dggrid convert failed')
        geometry, bbox, centroids = [], [], []
        for g in hex_geometry:
            geometry.append(GeoJSONPolygon(**eval(shapely.to_geojson(g))))
            bbox.append(list(g.bounds))
        for c in centroid:
            centroids.append(GeoJSONPoint(**eval(shapely.to_geojson(c))))
        return DGGRSProviderZoneInfoReturn(**{'zone_level': zone_level, 'shapeType': 'hexagon',
                                              'centroids': centroids, 'geometry': geometry, 'bbox': bbox,
                                              'areaMetersSquare': self.data[zone_level]["Area (km^2)"] * 1000000})

    def zoneslist(self, bbox: Union[box, None], zone_level: int, parent_zone: Union[str, int, None], returngeometry: str, compact=True):
        if (bbox is not None):
            try:
                hex_gdf = self.generate_hexgrid(bbox, zone_level)
            except Exception as e:
                logger.error(f'{__name__} query zones list, bbox: {bbox} dggrid convert failed :{e}')
                raise Exception(f"{__name__} query zones list, bbox: {bbox} dggrid convert failed {e}")
            logger.info(f'{__name__} query zones list, number of hexagons: {len(hex_gdf)}')
        if (parent_zone is not None):
            try:
                parent_zone_level = self.get_cells_zone_level([parent_zone])[0]
                childern_hex_gdf = self.dggrid_instance.grid_cell_polygons_from_cellids([parent_zone], self.dggrs, zone_level,
                                                                                        clip_subset_type='COARSE_CELLS',
                                                                                        clip_cell_res=parent_zone_level,
                                                                                        **self.address_params)
                childern_hex_gdf.set_index('name', inplace=True)
                hex_gdf = hex_gdf.join(childern_hex_gdf, how='inner', rsuffix='_p') if (bbox is not None) else childern_hex_gdf
            except Exception as e:
                logger.error(f'{__name__} query zones list, parent_zone: {parent_zone} get children failed {e}')
                raise Exception(f'parent_zone: {parent_zone} get children failed {e}')
        if (len(hex_gdf) == 0):
            raise Exception(f"{__name__} Parent zone {parent_zone} is not with in bbox: {bbox} at zone level {zone_level}")
        if (compact):
            i = 0
            hex_gdf.reset_index(inplace=True)
            while (i >= 0):
                hex_gdf['compact'] = hex_gdf['name'].apply(lambda x: x[:-1] if (len(x) == (zone_level - i + 2)) else x)
                counts = hex_gdf.groupby("compact")['name'].count()
                i += 1
                counts_idx = np.where(counts == pow(7, i))[0]
                replace = counts.iloc[counts_idx].index
                if (len(replace) > 0):
                    new_geometry = self.hexagon_from_cellid(replace, (zone_level - i))
                    new_geometry.set_index('name', inplace=True)
                    replace_idx = np.isin(hex_gdf['compact'].values, replace.values).nonzero()[0]
                    hex_gdf.iloc[replace_idx, 0] = hex_gdf.iloc[replace_idx]['compact']
                    hex_gdf.set_index('name', inplace=True)
                    hex_gdf.update(new_geometry)
                    hex_gdf.reset_index(inplace=True)
                else:
                    i = -1
            hex_gdf = hex_gdf.drop_duplicates(subset=['name'])
            logger.info(f'{__name__} query zones list, compact : {len(hex_gdf)}')
        if (returngeometry != 'zone-region'):
            hex_gdf = self.centroid_from_cellid(hex_gdf['name'].values, zone_level)
        returnedAreaMetersSquare = [self.data[zone_level]['Area (km^2)'] * 1000000] * len(hex_gdf)
        geotype = GeoJSONPolygon if (returngeometry == 'zone-region') else GeoJSONPoint
        geometry = [geotype(**eval(shapely.to_geojson(g))) for g in hex_gdf['geometry'].values.tolist()]
        hex_gdf.reset_index(inplace=True)
        return DGGRSProviderZonesListReturn(**{'zones': hex_gdf['name'].values.astype(str).tolist(),
                                               'geometry': geometry,
                                               'returnedAreaMetersSquare': returnedAreaMetersSquare})
