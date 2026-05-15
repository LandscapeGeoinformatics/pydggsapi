from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import ZonesDataDggsJsonResponse, ZonesDataGeoJson
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
from dggrid4py import DGGRIDv8
import tempfile
import shapely
import json
import geopandas as gpd
import xarray as xr
import zarr

working = tempfile.mkdtemp()
dggrid = DGGRIDv8(os.environ['DGGRID_PATH'], working_dir=working, silent=True)

aoi = [[25.329803558251513, 58.634545591972696],
       [25.329803558251513, 57.99111013411327],
       [27.131561370751513, 57.99111013411327],
       [27.131561370751513, 58.634545591972696]]

aoi_3035 = [5204952.96287564, 3973761.18085118, 5324408.86305371, 4067507.93907037]
cellids = ['000102', '0001022011', '0001022012']
non_exists = ['05526613']
zone_level = [5, 6, 7, 8, 9]

aoi = shapely.Polygon(aoi)


def test_data_retrieval():
    os.environ['dggs_api_config'] = './dggs_api_config_testing.json'
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Fail test case with non existing dggrs id")
    response = client.get(f'/dggs-api/v1-pre/dggs/non_exist/zones/{cellids[0]}/data')
    assert "not supported" in response.text
    assert response.status_code == 400

    print(f"Fail test case withdata-retrieval query (igeo7, {cellids[0]}, relative_depth=6) over refinement")
    response = client.get(f'/dggs-api/v1-pre/dggs/igeo7/zones/{cellids[0]}/data', params={'zone-depth': 6})
    assert "over refinement" in response.text
    assert response.status_code == 400

    print(f"Success test case with data-retrieval query (igeo7, {cellids[0]})")
    response = client.get(f'/dggs-api/v1-pre/dggs/igeo7/zones/{cellids[0]}/data', params={'zone-depth': '0'})
    data = ZonesDataDggsJsonResponse(**response.json())
    p1 = list(data.values.keys())[0]
    assert len(data.values[p1]) > 0
    value = data.values[p1][0]
    assert len(value.data) > 0
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (igeo7, {cellids[0]}, depth=[0] ,return = geojson)")
    response = client.get(f'/dggs-api/v1-pre/dggs/igeo7/zones/{cellids[0]}/data', headers={'accept': 'application/geo+json'},
                          params={'zone-depth': '0'})
    data = ZonesDataGeoJson(**response.json())
    assert len(data.features) > 0
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (igeo7, {cellids[0]}, depth=[0],return = geojson, geometry='zone-centroid')")
    response = client.get(f'/dggs-api/v1-pre/dggs/igeo7/zones/{cellids[0]}/data', params={'geometry': 'zone-centroid', 'zone-depth': '0'},
                          headers={'accept': 'application/geo+json'})
    data = ZonesDataGeoJson(**response.json())
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (igeo7, {cellids[0]}, relative_depth=2)")
    response = client.get(f'/dggs-api/v1-pre/dggs/igeo7/zones/{cellids[0]}/data', params={'zone-depth': '2'})
    data = ZonesDataDggsJsonResponse(**response.json())
    p1 = list(data.values.keys())[0]
    assert len(data.values[p1]) > 0
    assert (2 in data.depths)
    value = data.values[p1][0]
    assert len(value.data) > 0
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (igeo7, {cellids[0]}, relative_depth=1-2)")
    response = client.get(f'/dggs-api/v1-pre/dggs/igeo7/zones/{cellids[0]}/data', params={'zone-depth': '1-2'})
    data = ZonesDataDggsJsonResponse(**response.json())
    p1 = list(data.values.keys())[0]
    assert len(data.values[p1]) > 0
    assert (1 in data.depths) and (2 in data.depths)
    value = data.values[p1][0]
    assert len(value.data) > 0
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (igeo7, {cellids[0]}, relative_depth=0-2)")
    response = client.get(f'/dggs-api/v1-pre/dggs/igeo7/zones/{cellids[0]}/data', params={'zone-depth': '0-2'})
    data = ZonesDataDggsJsonResponse(**response.json())
    p1 = list(data.values.keys())[0]
    assert len(data.values[p1]) > 0
    assert (1 in data.depths) and (2 in data.depths) and (0 in data.depths)
    value = data.values[p1][0]
    assert len(value.data) > 0
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (igeo7, {cellids[0]}, relative_depth=0-2, geometry='zone-centroid', return=geojson)")
    response = client.get(f'/dggs-api/v1-pre/dggs/igeo7/zones/{cellids[0]}/data', params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                          headers={'accept': 'application/geo+json'})
    data = ZonesDataGeoJson(**response.json())
    assert len(data.features) > 0
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (igeo7, {cellids[0]}, relative_depth=0-2, geometry='zone-centroid', return=zarr+zip)")
    response = client.get(f'/dggs-api/v1-pre/dggs/igeo7/zones/{cellids[0]}/data', params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                          headers={'accept': 'application/zarr+zip'})
    assert response.status_code == 200
    with open("data_zarr.zip", "wb") as f:
        f.write(response.content)
    z = zarr.open('data_zarr.zip')
    print(z.tree())

    print(f"Empty test case with data-retrieval query (igeo7, {non_exists[0]}, relative_depth=0-2, geometry='zone-centroid', return=geojson)")
    response = client.get(f'/dggs-api/v1-pre/dggs/igeo7/zones/{non_exists[0]}/data', params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                          headers={'accept': 'application/geo+json'})
    assert response.status_code == 204
