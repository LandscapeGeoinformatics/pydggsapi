from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoResponse
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
from pprint import pprint
from dggrid4py import DGGRIDv8
import tempfile
import shapely
import json

# working = tempfile.mkdtemp()
# dggrid = DGGRIDv7(os.environ['DGGRID_PATH'], working_dir=working)
cellids = ['841134dffffffff', '841136bffffffff', '841f65bffffffff', '8411345ffffffff', '8411369ffffffff']
non_exists = ['86411cb77ffffff']
#validation_hexagons_gdf = dggrid.grid_cell_polygons_from_cellids(cellids, 'IGEO7', 8, input_address_type='Z7_STRING', output_address_type='Z7_STRING')
#validation_centroids_gdf = dggrid.grid_cell_centroids_from_cellids(cellids, 'IGEO7', 8, input_address_type='Z7_STRING', output_address_type='Z7_STRING')
#validation_hexagons_gdf.set_index('name', inplace=True)
#validation_centroids_gdf.set_index('name', inplace=True)


def test_core_dggs_zoneinfo_H3_2_IGEO7():
    os.environ['dggs_api_config'] = './dggs_api_config_testing.json'
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print(f"Success test case with dggs zone info (h3 {cellids[0]})")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{cellids[0]}')
    pprint(response.json())
    zoneinfo = ZoneInfoResponse(**response.json())
    centroid = shapely.from_geojson(json.dumps(zoneinfo.centroid.__dict__))
    hexagon = shapely.from_geojson(json.dumps(zoneinfo.geometry.__dict__))
    assert response.status_code == 200

    print(f"Empty return test case with dggs zone info (h3 {non_exists[0]})")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{non_exists[0]}')
    assert response.status_code == 204
