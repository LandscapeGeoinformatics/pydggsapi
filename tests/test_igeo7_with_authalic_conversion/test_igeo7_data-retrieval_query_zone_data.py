from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import ZonesDataDggsJsonResponse, ZonesDataGeoJson
from pydggsapi.schemas.api.collections import Collection
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
from dggrid4py import DGGRIDv8
from dggrid4py.auxlat import geoseries_to_authalic, geoseries_to_geodetic
import tempfile
import shapely
import numpy as np
from geopandas import GeoSeries
from tinydb import TinyDB
import zarr


extra_conf = {
    "input_address_type": 'HIERNDX',
    "input_hier_ndx_system": 'Z7',
    "input_hier_ndx_form": 'DIGIT_STRING',
    "output_address_type": 'HIERNDX',
    "output_cell_label_type": 'OUTPUT_ADDRESS_TYPE',
    "output_hier_ndx_system": 'Z7',
    "output_hier_ndx_form": 'DIGIT_STRING',
    "dggs_vert0_lon": 11.20
    # initial vertex lon setting
}

non_exists = ['055266135']

db = TinyDB(os.environ.get('DGGS_API_CONFIG'))
collections = db.table('collections').all()
collections_dict = {}

for collection in collections:
    cid, collection_config = collection.popitem()
    if (collection_config['collection_provider']['dggrsId'] == 'igeo7'):
        collection_config['id'] = cid
        collections_dict[cid] = Collection(**collection_config)

working = tempfile.mkdtemp()
dggrid = DGGRIDv8(os.environ['DGGRID_PATH'], working_dir=working, silent=True)

validation_df = {}

for collection_name, collection in collections_dict.items():
    minx, miny, maxx, maxy = collection.extent.spatial.bbox[0]
    # create a smaller bbox
    minx, miny = round(minx + 0.1, 3), round(miny + 0.05, 3)
    maxx, maxy = round(maxx - 0.1, 3), round(maxy - 0.05, 3)
    aoi = shapely.box(minx, miny, maxx, maxy)
    authalic_aoi = geoseries_to_authalic(GeoSeries(aoi))[0]
    max_rf = collection.collection_provider.max_refinement_level
    hex_df = dggrid.grid_cell_polygons_for_extent('IGEO7', max_rf-3, clip_geom=authalic_aoi, **extra_conf)
    centroid_df = dggrid.grid_cell_centroids_from_cellids(hex_df['name'], 'IGEO7', max_rf-3, **extra_conf)

    validation_df[collection_name] = {'hex': hex_df, 'centroid': centroid_df.set_index('name'),
                                      'aoi': aoi, 'max_rf': max_rf, 'zone_rf': max_rf-3}



def test_data_retrieval():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    print("Fail test case with non existing dggrs id")
    response = client.get('/dggs-api/dggs/non_exist/zones/0013415612/data')
    assert "not supported" in response.text
    assert response.status_code == 400

    _, df_dict = validation_df.popitem()
    iloc_pos = np.random.randint(0, df_dict['hex'].shape[0], 1)
    zone = df_dict['hex'].iloc[iloc_pos[0]]
    max_rf = df_dict['max_rf']
    zone_rf = df_dict['zone_rf']
    over_rf_depth = max_rf - zone_rf + 1
    print(f"Fail test case withdata-retrieval query (igeo7, {zone['name']}, zone-depth={over_rf_depth}) over refinement")
    response = client.get(f"/dggs-api/dggs/igeo7/zones/{zone['name']}/data", params={"zone-depth": over_rf_depth})
    assert "over refinement" in response.text
    assert response.status_code == 400

    print(f"Success test case with data-retrieval query (igeo7, {zone['name']}, default zone-depth = 1)")
    response = client.get(f'/dggs-api/dggs/igeo7/zones/{zone["name"]}/data')
    assert response.status_code == 200
    data = ZonesDataDggsJsonResponse(**response.json())
    for k, v in data.values.items():
        assert len(v) == 1
        assert v[0].depth == 1
        assert len(v[0].data) == 13

    print(f"Success test case with data-retrieval query (igeo7, {zone['name']}, zone-depth=0 ,return = geojson)")
    response = client.get(f'/dggs-api/dggs/igeo7/zones/{zone["name"]}/data', headers={'accept': 'application/geo+json'},
                          params={'zone-depth': '0'})
    assert response.status_code == 200
    data = ZonesDataGeoJson(**response.json())
    assert len(data.features) > 0

    print(f"Success test case with data-retrieval query (igeo7, {zone['name']}, zone-depth=0,return = geojson, geometry='zone-centroid')")
    response = client.get(f'/dggs-api/dggs/igeo7/zones/{zone["name"]}/data', params={'geometry': 'zone-centroid', 'zone-depth': '0'},
                          headers={'accept': 'application/geo+json'})
    assert response.status_code == 200
    data = ZonesDataGeoJson(**response.json())
    assert len(data.features) > 0

    print(f"Success test case with data-retrieval query (igeo7, {zone['name']}, zone-depth=2)")
    response = client.get(f'/dggs-api/dggs/igeo7/zones/{zone["name"]}/data', params={'zone-depth': '2'})
    data = ZonesDataDggsJsonResponse(**response.json())
    assert response.status_code == 200
    for k, v in data.values.items():
        assert len(v) == 1
        assert v[0].depth == 2
        assert len(v[0].data) > 0
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (igeo7, {zone['name']}, zone-depth=1-2)")
    response = client.get(f'/dggs-api/dggs/igeo7/zones/{zone["name"]}/data', params={'zone-depth': '1-2'})
    data = ZonesDataDggsJsonResponse(**response.json())
    assert response.status_code == 200
    zone_depth_counts = [1, 2]
    for k, v in data.values.items():
        assert len(v) == 2
        for data in v:
            assert data.depth in zone_depth_counts
            assert len(data.data) > 0

    print(f"Success test case with data-retrieval query (igeo7, {zone['name']}, zone-depth=0-2)")
    response = client.get(f'/dggs-api/dggs/igeo7/zones/{zone["name"]}/data', params={'zone-depth': '0-2'})
    data = ZonesDataDggsJsonResponse(**response.json())
    assert response.status_code == 200
    zone_depth_counts = [0, 1, 2]
    for k, v in data.values.items():
        assert len(v) == 3
        for data in v:
            assert data.depth in zone_depth_counts
            assert len(data.data) > 0

    print(f"Success test case with data-retrieval query (igeo7, {zone['name']}, zone-depth=0-2, geometry='zone-centroid', return=geojson)")
    response = client.get(f'/dggs-api/dggs/igeo7/zones/{zone["name"]}/data', params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                          headers={'accept': 'application/geo+json'})
    data = ZonesDataGeoJson(**response.json())
    assert len(data.features) > 0
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (igeo7, {zone['name']}, zone-depth=0-2, geometry='zone-centroid', return=zarr+zip)")
    response = client.get(f'/dggs-api/dggs/igeo7/zones/{zone["name"]}/data', params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                          headers={'accept': 'application/zarr+zip'})
    assert response.status_code == 200
    with open("data_zarr.zip", "wb") as f:
        f.write(response.content)
    store = zarr.storage.ZipStore("data_zarr.zip", read_only=True)
    z = zarr.open(store=store, mode="r")
    print(z.tree())

    print(f"Empty test case with data-retrieval query (igeo7, 00000000, zone-depth=0-2, geometry='zone-centroid', return=geojson)")
    response = client.get(f'/dggs-api/dggs/igeo7/zones/00000000/data', params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                          headers={'accept': 'application/geo+json'})
    assert response.status_code == 204
