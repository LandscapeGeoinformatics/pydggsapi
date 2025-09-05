from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoResponse
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
from pprint import pprint
from dggrid4py import DGGRIDv7
import tempfile
import shapely
import json

working = tempfile.mkdtemp()
dggrid = DGGRIDv7(os.environ['DGGRID_PATH'], working_dir=working, silent=True)
cellids = ['0001022010', '0001022011', '0001022012']
non_exists = ['055266135']
validation_hexagons_gdf = dggrid.grid_cell_polygons_from_cellids(cellids, 'IGEO7', 8, input_address_type='Z7_STRING', output_address_type='Z7_STRING')
validation_centroids_gdf = dggrid.grid_cell_centroids_from_cellids(cellids, 'IGEO7', 8, input_address_type='Z7_STRING', output_address_type='Z7_STRING')
validation_hexagons_gdf.set_index('name', inplace=True)
validation_centroids_gdf.set_index('name', inplace=True)


def test_core_dggs_zoneinfo_empty_config():
    os.environ['dggs_api_config'] = './empty.json'
    try:
        import pydggsapi.api
        app = reload(pydggsapi.api).app
        client = TestClient(app)
    except Exception as e:
        print(f"Testing with dggrs zoneinfo (no dggrs defined) {e}")


def test_core_dggs_zoneinfo():
    os.environ['dggs_api_config'] = './dggs_api_config_testing.json'
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Fail test case with non existing dggrs id")
    response = client.get('/dggs-api/v1-pre/dggs/non_exist/zones/00000000')
    pprint(response.json())
    assert "not supported" in response.text
    assert response.status_code == 400

    os.environ['dggs_api_config'] = './dggs_api_config.json'
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print(f"Success test case with dggs zone info (igeo7 {cellids[0]})")
    response = client.get(f'/dggs-api/v1-pre/dggs/igeo7/zones/{cellids[0]}')
    pprint(response.json())
    zoneinfo = ZoneInfoResponse(**response.json())
    centroid = shapely.from_geojson(json.dumps(zoneinfo.centroid.__dict__))
    hexagon = shapely.from_geojson(json.dumps(zoneinfo.geometry.__dict__))
    assert shapely.equals(hexagon, validation_hexagons_gdf.loc[cellids[0]]['geometry'])
    assert shapely.equals(centroid, validation_centroids_gdf.loc[cellids[0]]['geometry'])
    assert response.status_code == 200

    print("Fail test case with not exist collection dggs zone info (collection not found)")
    response = client.get(f'/dggs-api/v1-pre/collections/hytruck/dggs/igeo7/zones/{cellids[0]}')
    pprint(response.text)
    assert "hytruck not found" in response.text
    assert response.status_code == 400

    print("Fail test case with collections (non-existing dggrs id)")
    response = client.get(f'/dggs-api/v1-pre/collections/suitability_hytruck/dggs/Non_existing/zones/{cellids[0]}')
    pprint(response.text)
    assert "not supported" in response.text
    assert response.status_code == 400

    print(f"Success test case with collections on zones info (suitability_hytruck, igeo7, {cellids[2]})")
    response = client.get(f'/dggs-api/v1-pre/collections/suitability_hytruck/dggs/igeo7/zones/{cellids[2]}')
    pprint(response.json())
    zoneinfo = ZoneInfoResponse(**response.json())
    centroid = shapely.from_geojson(json.dumps(zoneinfo.centroid.__dict__))
    hexagon = shapely.from_geojson(json.dumps(zoneinfo.geometry.__dict__))
    assert shapely.equals(hexagon, validation_hexagons_gdf.loc[cellids[2]]['geometry'])
    assert shapely.equals(centroid, validation_centroids_gdf.loc[cellids[2]]['geometry'])
    assert response.status_code == 200

    print(f"Fail test case with collections on non-exist zones info (suitability_hytruck, igeo7, {non_exists[0]})")
    response = client.get(f'/dggs-api/v1-pre/collections/suitability_hytruck/dggs/igeo7/zones/{non_exists[0]}')
    assert response.status_code == 204
