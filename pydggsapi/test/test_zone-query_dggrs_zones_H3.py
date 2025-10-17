from pydggsapi.schemas.ogc_dggs.dggrs_zones import ZonesResponse, ZonesGeoJson
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

working = tempfile.mkdtemp()
dggrid = DGGRIDv8(os.environ['DGGRID_PATH'], working_dir=working, silent=True)

aoi = [[25.329803558251513, 58.634545591972696],
       [25.329803558251513, 57.99111013411327],
       [27.131561370751513, 57.99111013411327],
       [27.131561370751513, 58.634545591972696]]

non_exist_aoi = [[113.81837742963569, 22.521237932154797],
          [113.81837742963569, 22.13760392858767],
          [114.41438573041694, 22.13760392858767],
          [114.41438573041694, 22.521237932154797]]

aoi_3035 = [5204952.96287564, 3973761.18085118, 5324408.86305371, 4067507.93907037]
cellids = ['841134dffffffff', '841136bffffffff', '841f65bffffffff', '8411345ffffffff', '8411369ffffffff']
non_exists = ['86411cb6fffffff']
zone_level = [5, 6, 7, 8, 9]

aoi = shapely.Polygon(aoi)
non_exist_aoi = shapely.Polygon(non_exist_aoi)


def test_zone_query_dggrs_zones_VH3_2_IGEO7():
    os.environ['dggs_api_config'] = './dggs_api_config_testing.json'
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    print(f"Success test case with dggs zones query (h3, bbox: {aoi.bounds}, compact=False)")
    bounds = list(map(str, aoi.bounds))
    response = client.get('/dggs-api/v1-pre/dggs/h3/zones', params={"bbox": ",".join(bounds), 'compact_zone': False})
    pprint(response.json())
    zones = ZonesResponse(**response.json())
    assert len(zones.zones) > 0
    assert response.status_code == 200

    print(f"Success test case with dggs zones query (h3, bbox: {aoi.bounds}, zone_level=2, compact=False)")
    response = client.get('/dggs-api/v1-pre/dggs/h3/zones', params={"bbox": ",".join(bounds), 'zone_level': 2, 'compact_zone': False})
    #pprint(response.json())
    #zones = ZonesResponse(**response.json())
    #assert len(zones.zones) > 0
    assert response.status_code == 204

    print(f"Success test case with dggs zones query (h3, bbox: {aoi.bounds}, zone_level=6, compact=False)")
    response = client.get('/dggs-api/v1-pre/dggs/h3/zones', params={"bbox": ",".join(bounds), 'zone_level': 6, 'compact_zone': False})
    pprint(response.json())
    zones = ZonesResponse(**response.json())
    assert len(zones.zones) > 0
    assert response.status_code == 200

    print(f"Success test case with dggs zones query (h3, bbox: {aoi.bounds}, zone_level=6, compact=True)")
    response = client.get('/dggs-api/v1-pre/dggs/h3/zones', params={"bbox": ",".join(bounds), 'zone_level': 6, 'compact_zone': True})
    pprint(response.json())
    zones = ZonesResponse(**response.json())
    assert len(zones.zones) > 0
    assert response.status_code == 200

    print(f"Success test case with dggs zones query (h3, bbox: {aoi.bounds}, zone_level=6, compact=False, geojson)")
    response = client.get('/dggs-api/v1-pre/dggs/h3/zones', headers={'Accept': 'Application/geo+json'},
                          params={"bbox": ",".join(bounds), 'zone_level': 6, 'compact_zone': False})
    pprint(response.json())
    zones_geojson = ZonesGeoJson(**response.json())
    assert len(zones.zones) > 0
    assert response.status_code == 200

    print(f"Success test case with dggs zones query (h3, parent zone: {cellids[0]}, zone_level=6, compact=False, geojson)")
    response = client.get('/dggs-api/v1-pre/dggs/h3/zones', headers={'Accept': 'Application/geo+json'},
                          params={"parent_zone": cellids[0], 'zone_level': 6, 'compact_zone': False})
    pprint(response.json())
    zones_geojson = ZonesGeoJson(**response.json())
    return_features_list = zones_geojson.features
    assert len(zones.zones) > 0
    assert response.status_code == 200

    print(f"Fail test case with dggs zones query (h3, parent zone: {cellids[0]}, zone_level=8, compact=False, geojson)")
    response = client.get('/dggs-api/v1-pre/dggs/h3/zones', headers={'Accept': 'Application/geo+json'},
                          params={"parent_zone": cellids[0], 'zone_level': 8, 'compact_zone': False})
    pprint(response.json())
    assert response.status_code == 400

    print(f"Empty test case with dggs zones query (h3, bbox: {non_exist_aoi.bounds}, zone_level=6, compact=False, geojson)")
    non_exist_bounds = list(map(str, non_exist_aoi.bounds))
    response = client.get('/dggs-api/v1-pre/dggs/h3/zones', headers={'Accept': 'Application/geo+json'},
                          params={"bbox": non_exist_bounds, 'zone_level': 6, 'compact_zone': False})
    assert response.status_code == 204

    print(f"Empty test case with dggs zones query (h3, parent zone: {non_exists[0]}, zone_level=6, compact=False, geojson)")
    response = client.get('/dggs-api/v1-pre/dggs/h3/zones', headers={'Accept': 'Application/geo+json'},
                          params={"parent_zone": non_exists[0], 'zone_level': 6, 'compact_zone': False})
    assert response.status_code == 204
