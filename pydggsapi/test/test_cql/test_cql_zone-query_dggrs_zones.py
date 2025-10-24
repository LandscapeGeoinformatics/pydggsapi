from pydggsapi.schemas.ogc_dggs.dggrs_zones import ZonesResponse, ZonesGeoJson
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
from pprint import pprint
from dggrid4py import DGGRIDv7
import tempfile
import shapely
import json
import geopandas as gpd

working = tempfile.mkdtemp()
dggrid = DGGRIDv7(os.environ['DGGRID_PATH'], working_dir=working, silent=True)

aoi = [[25.329803558251513, 58.634545591972696],
       [25.329803558251513, 57.99111013411327],
       [27.131561370751513, 57.99111013411327],
       [27.131561370751513, 58.634545591972696]]

non_exist_aoi = [[113.81837742963569, 22.521237932154797],
          [113.81837742963569, 22.13760392858767],
          [114.41438573041694, 22.13760392858767],
          [114.41438573041694, 22.521237932154797]]

aoi_3035 = [5204952.96287564, 3973761.18085118, 5324408.86305371, 4067507.93907037]
zone_level = [5, 6, 7, 8, 9]

aoi = shapely.Polygon(aoi)
non_exist_aoi = shapely.Polygon(non_exist_aoi)
validation_zone_level_5_hexagons_gdf = dggrid.grid_cell_polygons_for_extent('IGEO7', 5, clip_geom=aoi, output_address_type='Z7_STRING')
validation_hexagons_gdf = dggrid.grid_cell_polygons_for_extent('IGEO7', 8, clip_geom=aoi, output_address_type='Z7_STRING')
validation_centroids_gdf = dggrid.grid_cell_centroids_for_extent('IGEO7', 8, clip_geom=aoi, output_address_type='Z7_STRING')
validation_zone_level_5_hexagons_gdf.set_index('name', inplace=True)
validation_hexagons_gdf.set_index('name', inplace=True)
validation_centroids_gdf.set_index('name', inplace=True)

cql_ok = ['modelled_residential_areas <= 6']
cql_204= ['modelled_residential_areas_band_1 > 12']
cql_fail = ['non_exist > 4', 'non_exist $<< 12']

grid = {'igeo7': ['00010220', '0001022011', '0001022012'] , 'h3': ['841134dffffffff', '841136bffffffff', '841f65bffffffff', '8411345ffffffff', '8411369ffffffff']}

def test_zone_query_dggrs_zones():
    os.environ['dggs_api_config'] = './dggs_api_config_testing.json'
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    bounds = list(map(str, aoi.bounds))
    for g in list(grid.keys()):
        print(f"Test grid: {g}")
        for c in cql_ok:
            print(f"Test cql: {c}")
            print(f"Success test case with dggs zones query ({g}, bbox: {aoi.bounds}, compact=False)")
            response = client.get(f'/dggs-api/v1-pre/dggs/{g}/zones', params={"bbox": ",".join(bounds), 'compact_zone': False,
                                                                               "filter": c})
            pprint(response.json())
            zones = ZonesResponse(**response.json())
            assert len(zones.zones) > 0
            assert response.status_code == 200

            print(f"Success test case with dggs zones query ({g}, bbox: {aoi.bounds}, zone_level=8, compact=False)")
            response = client.get(f'/dggs-api/v1-pre/dggs/{g}/zones', params={"bbox": ",".join(bounds), 'zone_level': 8, 'compact_zone': False,
                                                                               "filter": c})
            pprint(response.json())
            zones = ZonesResponse(**response.json())
            assert len(zones.zones) > 0
            assert response.status_code == 200

            print(f"Success test case with dggs zones query ({g}, bbox: {aoi.bounds}, zone_level=8, compact=False, geojson)")
            response = client.get(f'/dggs-api/v1-pre/dggs/{g}/zones', headers={'Accept': 'Application/geo+json'},
                                  params={"bbox": ",".join(bounds), 'zone_level': 7, 'compact_zone': False, 'filter': c})
            pprint(response.json())
            assert len(zones.zones) > 0
            assert response.status_code == 200

            print(f"Success test case with dggs zones query ({g}, parent zone: {grid[g][0]}, zone_level=8, compact=False, geojson)")
            response = client.get(f'/dggs-api/v1-pre/dggs/{g}/zones', headers={'Accept': 'Application/geo+json'},
                                  params={"parent_zone": grid[g][0], 'zone_level': 7, 'compact_zone': False, 'filter': c})

            pprint(response.json())
            assert len(zones.zones) > 0
            assert response.status_code == 200

