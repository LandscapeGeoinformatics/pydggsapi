from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import ZonesDataDggsJsonResponse, ZonesDataGeoJson
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
import xarray as xr
import zarr

working = tempfile.mkdtemp()
dggrid = DGGRIDv7(os.environ['DGGRID_PATH'], working_dir=working, silent=True)

aoi = [[25.329803558251513, 58.634545591972696],
       [25.329803558251513, 57.99111013411327],
       [27.131561370751513, 57.99111013411327],
       [27.131561370751513, 58.634545591972696]]

aoi_3035 = [5204952.96287564, 3973761.18085118, 5324408.86305371, 4067507.93907037]
cellids = ['00010220', '0001022011', '0001022012']
non_exists = ['05526613']
zone_level = [5, 6, 7, 8, 9]

aoi = shapely.Polygon(aoi)

cql_ok = ['modelled_residential_areas <= 6']
cql_204= ['modelled_residential_areas_band_1 > 12']
cql_fail = ['non_exist > 4', 'non_exist $<< 12']

grid = {'igeo7': ['00010220', '0001022011', '0001022012'] , 'h3': ['841134dffffffff', '841136bffffffff', '841f65bffffffff', '8411345ffffffff', '8411369ffffffff']}


def test_data_retrieval():
    os.environ['dggs_api_config'] = './dggs_api_config_testing.json'
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    for g in list(grid.keys()):

        print(f"Success test case with data-retrieval query ({g}, {grid[g][0]})")
        response = client.get(f'/dggs-api/v1-pre/dggs/{g}/zones/{grid[g][0]}/data', params={'zone_depth': '0', 'filter': cql_ok[0]})
        pprint(response.json())
        data = ZonesDataDggsJsonResponse(**response.json())
        p1 = list(data.properties.keys())[0]
        assert len(data.values[p1]) > 0
        value = data.values[p1][0]
        assert len(value.data) > 0
        assert response.status_code == 200

        print(f"Success test case with data-retrieval query ({g}, {grid[g][0]}, zone_depth=[0] ,return = geojson)")
        response = client.get(f'/dggs-api/v1-pre/dggs/{g}/zones/{grid[g][0]}/data', headers={'accept': 'application/geo+json'},
                              params={'zone_depth': '0', 'filter': cql_ok[0]})
        pprint(response.json())
        data = ZonesDataGeoJson(**response.json())
        assert len(data.features) > 0
        assert response.status_code == 200

        print(f"Success test case with data-retrieval query ({g}, {grid[g][0]}, relative_zone_depth=2)")
        response = client.get(f'/dggs-api/v1-pre/dggs/{g}/zones/{grid[g][0]}/data', params={'zone_depth': '2', 'filter': cql_ok[0]})
        pprint(response.json())
        data = ZonesDataDggsJsonResponse(**response.json())
        p1 = list(data.properties.keys())[0]
        assert len(data.values[p1]) > 0
        assert (2 in data.depths)
        value = data.values[p1][0]
        assert len(value.data) > 0
        assert response.status_code == 200

        print(f"Success test case with data-retrieval query ({g}, {grid[g][0]}, relative_zone_depth=1-2)")
        response = client.get(f'/dggs-api/v1-pre/dggs/{g}/zones/{grid[g][0]}/data', params={'zone_depth': '1-2'})
        pprint(response.json())
        data = ZonesDataDggsJsonResponse(**response.json())
        p1 = list(data.properties.keys())[0]
        assert len(data.values[p1]) > 0
        assert (1 in data.depths) and (2 in data.depths)
        value = data.values[p1][0]
        assert len(value.data) > 0
        assert response.status_code == 200
