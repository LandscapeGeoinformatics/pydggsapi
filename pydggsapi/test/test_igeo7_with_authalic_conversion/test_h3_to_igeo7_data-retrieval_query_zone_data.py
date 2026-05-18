from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import ZonesDataDggsJsonResponse, ZonesDataGeoJson
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
from pprint import pprint
from dggrid4py import DGGRIDv8
import tempfile
import shapely
import json
import geopandas as gpd


aoi = [[25.329803558251513, 58.634545591972696],
       [25.329803558251513, 57.99111013411327],
       [27.131561370751513, 57.99111013411327],
       [27.131561370751513, 58.634545591972696]]

aoi_3035 = [5204952.96287564, 3973761.18085118, 5324408.86305371, 4067507.93907037]
# 841134dffffffff refinement level = 4
cellids = ['841134dffffffff', '841136bffffffff', '841f65bffffffff', '8411345ffffffff', '8411369ffffffff']
non_exists = ['84411c9ffffffff']
# cellids = ['00010220', '0001022011', '0001022012']
zone_level = [5, 6, 7, 8, 9]

aoi = shapely.Polygon(aoi)


def test_data_retrieval_h3():
    os.environ['dggs_api_config'] = './dggs_api_config_testing.json'
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    print("Fail test case with non existing dggrs id")
    response = client.get(f'/dggs-api/v1-pre/dggs/non_exist/zones/{cellids[0]}/data')
    assert "not supported" in response.text
    assert response.status_code == 400

    print(f"Fail test case withdata-retrieval query (h3, {cellids[0]}, relative_depth=9) over refinement")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{cellids[0]}/data', params={'zone-depth': 9})
    assert response.status_code == 400

    print(f"Success test case with data-retrieval query (h3, {cellids[0]})")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{cellids[0]}/data', params={"zone-depth": 0})
    data = ZonesDataDggsJsonResponse(**response.json())
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (h3, {cellids[0]}, return = geojson)")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{cellids[0]}/data', headers={'accept': 'application/geo+json'}, params={'zone-depth': 0})
    data = ZonesDataGeoJson(**response.json())
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (h3, {cellids[0]}, return = geojson, geometry='zone-centroid')")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{cellids[0]}/data', params={'geometry': 'zone-centroid', "zone-depth": 0},
                          headers={'accept': 'application/geo+json'})
    data = ZonesDataGeoJson(**response.json())
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (h3, {cellids[0]}, relative_depth=2)")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{cellids[0]}/data', params={'zone-depth': 2})
    data = ZonesDataDggsJsonResponse(**response.json())
    assert response.status_code == 200

    print(f"Empty test case with data-retrieval query (h3, {non_exists[0]}, relative_depth=2)")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{non_exists[0]}/data', params={'zone-depth': 2})
    assert response.status_code == 204
