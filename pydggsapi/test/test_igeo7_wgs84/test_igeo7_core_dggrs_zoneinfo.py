from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoResponse
from pydggsapi.schemas.api.collections import Collection
from fastapi.testclient import TestClient
import pytest
from importlib import reload
from geopandas import GeoSeries
from tinydb import TinyDB
from dggrid4py import DGGRIDv8
from dggrid4py.auxlat import geoseries_to_authalic, geoseries_to_geodetic
import os
import numpy as np
import tempfile
import shapely
import json

extra_conf = {
    "input_address_type": 'HIERNDX',
    "input_hier_ndx_system": 'Z7',
    "input_hier_ndx_form": 'DIGIT_STRING',
    "output_address_type": 'HIERNDX',
    "output_cell_label_type": 'OUTPUT_ADDRESS_TYPE',
    "output_hier_ndx_system": 'Z7',
    "output_hier_ndx_form": 'DIGIT_STRING',
    # initial vertex lon setting
}

non_exists = ['055266135']

db = TinyDB(os.environ.get('dggs_api_config'))
collections = db.table('collections').all()
collections_dict = {}

for collection in collections:
    cid, collection_config = collection.popitem()
    collection_config['id'] = cid
    collections_dict[cid] = Collection(**collection_config)

working = tempfile.mkdtemp()
dggrid = DGGRIDv8(os.environ['DGGRID_PATH'], working_dir=working, silent=True)

validation_hexagons_gdf = {}
validation_centroids_gdf = {}
for collection_name, collection in collections_dict.items():
    bbox = shapely.box(*collection.extent.spatial.bbox[0])
    bbox = geoseries_to_authalic(GeoSeries(bbox))[0]
    rf = collection.collection_provider.max_refinement_level - 2
    hex_df = dggrid.grid_cell_polygons_for_extent('IGEO7', rf, clip_geom=bbox, **extra_conf)
    centroid_df = dggrid.grid_cell_centroids_from_cellids(hex_df['name'], 'IGEO7', rf, **extra_conf)
    hex_df['geometry'] = geoseries_to_geodetic(hex_df['geometry'])
    centroid_df['geometry'] = geoseries_to_geodetic(centroid_df['geometry'])

def test_core_dggs_zoneinfo():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Fail test case with not exist dggrs id")
    response = client.get('/dggs-api/v1-pre/dggs/not_exist/zones/00000000')
    assert "not supported" in response.text
    assert response.status_code == 400

    print("Fail test case with not exist collection dggs zone info (collection not found)")
    response = client.get('/dggs-api/v1-pre/collections/not_exist/dggs/igeo7/zones/00000000')
    assert "not found" in response.text
    assert response.status_code == 404

    for collection_name, hex_df in validation_hexagons_gdf.items():
        iloc_pos = np.random.randint(0, hex_df.size, 1)
        zoneid = hex_df.iloc[iloc_pos]['name'].values[0]
        zone_hex_geometry = hex_df.iloc[iloc_pos]['geometry'].values[0]
        zone_centroid_geometry = validation_centroids_gdf[collection_name].iloc[iloc_pos]['geometry'].values[0]
        print(f"Success test case with dggs zone info (igeo7 {zoneid})")
        response = client.get(f'/dggs-api/v1-pre/dggs/igeo7/zones/{zoneid}')
        zoneinfo = ZoneInfoResponse(**response.json())
        centroid = shapely.from_geojson(json.dumps(zoneinfo.centroid.__dict__))
        hexagon = shapely.from_geojson(json.dumps(zoneinfo.geometry.__dict__))
        assert shapely.equals(hexagon, zone_hex_geometry)
        assert shapely.equals(centroid, zone_centroid_geometry)
        assert response.status_code == 200

        print("Fail test case with collections (non-existing dggrs id)")
        response = client.get(f'/dggs-api/v1-pre/collections/{collection_name}/dggs/not_exit/zones/00000000')
        assert "not supported" in response.text
        assert response.status_code == 400

        print(f"Success test case with collections on zones info ({collection_name}, igeo7, {zoneid})")
        response = client.get(f'/dggs-api/v1-pre/collections/{collection_name}/dggs/igeo7/zones/{zoneid}')
        zoneinfo = ZoneInfoResponse(**response.json())
        centroid = shapely.from_geojson(json.dumps(zoneinfo.centroid.__dict__))
        hexagon = shapely.from_geojson(json.dumps(zoneinfo.geometry.__dict__))
        assert shapely.equals(hexagon, zone_hex_geometry)
        assert shapely.equals(centroid, zone_centroid_geometry)
        assert response.status_code == 200

        print(f"Fail test case with collections on non-exist zones info ({collection_name}, igeo7, {non_exists[0]})")
        response = client.get(f'/dggs-api/v1-pre/collections/{collection_name}/dggs/igeo7/zones/{non_exists[0]}')
        assert response.status_code == 204
