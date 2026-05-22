from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import ZonesDataDggsJsonResponse, ZonesDataGeoJson
from pydggsapi.schemas.api.collections import Collection
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
import h3
import shapely
import numpy as np
import geopandas as gpd
import zarr
from tinydb import TinyDB


def _cell_to_shapely(cellid, geometry):
    method = h3.cell_to_boundary if (geometry == 'zone-region') else h3.cell_to_latlng
    GEO = shapely.Polygon if (geometry == 'zone-region') else shapely.Point
    points = method(cellid)
    points = [points] if (geometry != 'zone-region') else points
    points = tuple(p[::-1] for p in points)
    return GEO(points)


non_exists = ['84411c9ffffffff']

db = TinyDB(os.environ.get('dggs_api_config'))
collections = db.table('collections').all()
collections_dict = {}

for collection in collections:
    cid, collection_config = collection.popitem()
    if (collection_config['collection_provider']['dggrsId'] == 'igeo7'):
        collection_config['id'] = cid
        collections_dict[cid] = Collection(**collection_config)

validation_df = {}

for collection_name, collection in collections_dict.items():
    minx, miny, maxx, maxy = collection.extent.spatial.bbox[0]
    # create a smaller bbox
    minx, miny = minx + 0.15, miny + 0.05
    maxx, maxy = maxx - 0.15, maxy - 0.05
    aoi = shapely.box(minx, miny, maxx, maxy)
    # h3 is approximately coarser than h3 with 2 refinement level
    max_rf = collection.collection_provider.max_refinement_level - 2
    zoneIds = h3.h3shape_to_cells_experimental(h3.geo_to_h3shape(aoi), max_rf - 3, contain='overlap')
    geometry = [_cell_to_shapely(z, 'zone-region') for z in zoneIds]
    hex_df = gpd.GeoDataFrame({'zoneid': zoneIds}, geometry=geometry, crs='wgs84')
    geometry = [_cell_to_shapely(z, 'zone-centorid') for z in zoneIds]
    centroid_df = gpd.GeoDataFrame({'zoneid': zoneIds}, geometry=geometry, crs='wgs84').set_index('zoneid')
    validation_df[collection_name] = {'hex': hex_df, 'centroid': centroid_df,
                                      'aoi': aoi, 'max_rf': max_rf, 'zone_rf': max_rf - 3}


def test_h3_to_h3_data_retrieval():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    print("Fail test case with non existing dggrs id")
    response = client.get(f'/dggs-api/v1-pre/dggs/non_exist/zones/{non_exists[0]}/data')
    assert "not supported" in response.text
    assert response.status_code == 400

    _, df_dict = validation_df.popitem()
    iloc_pos = np.random.randint(0, df_dict['hex'].shape[0], 1)
    zone = df_dict['hex'].iloc[iloc_pos[0]]
    max_rf = df_dict['max_rf']
    zone_rf = df_dict['zone_rf']
    over_rf_depth = max_rf - zone_rf + 1
    print(f"Fail test case withdata-retrieval query (h3, {zone['zoneid']}, zone-depth={over_rf_depth}) over refinement")
    response = client.get(f"/dggs-api/v1-pre/dggs/h3/zones/{zone['zoneid']}/data", params={"zone-depth": over_rf_depth})
    assert "over refinement" in response.text
    assert response.status_code == 400

    print(f"Success test case with data-retrieval query (h3, {zone['zoneid']}, default zone-depth = 1)")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{zone["zoneid"]}/data')
    assert response.status_code == 200
    data = ZonesDataDggsJsonResponse(**response.json())
    for k, v in data.values.items():
        assert len(v) == 1
        assert v[0].depth == 1
        assert len(v[0].data) == 7

    print(f"Success test case with data-retrieval query (h3, {zone['zoneid']}, depth=[0] ,return = geojson)")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{zone["zoneid"]}/data', headers={'accept': 'application/geo+json'},
                          params={'zone-depth': '0'})
    assert response.status_code == 200
    data = ZonesDataGeoJson(**response.json())
    assert len(data.features) > 0

    print(f"Success test case with data-retrieval query (h3, {zone['zoneid']}, depth=0,return = geojson, geometry='zone-centroid')")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{zone["zoneid"]}/data', params={'geometry': 'zone-centroid', 'zone-depth': '0'},
                          headers={'accept': 'application/geo+json'})
    assert response.status_code == 200
    data = ZonesDataGeoJson(**response.json())
    assert len(data.features) > 0

    print(f"Success test case with data-retrieval query (h3, {zone['zoneid']}, zone-depth=2)")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{zone["zoneid"]}/data', params={'zone-depth': '2'})
    data = ZonesDataDggsJsonResponse(**response.json())
    assert response.status_code == 200
    for k, v in data.values.items():
        assert len(v) == 1
        assert v[0].depth == 2
        assert len(v[0].data) > 0
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (h3, {zone['zoneid']}, zone-depth=1-2)")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{zone["zoneid"]}/data', params={'zone-depth': '1-2'})
    data = ZonesDataDggsJsonResponse(**response.json())
    assert response.status_code == 200
    zone_depth_counts = [1, 2]
    for k, v in data.values.items():
        assert len(v) == 2
        for data in v:
            assert data.depth in zone_depth_counts
            assert len(data.data) > 0

    print(f"Success test case with data-retrieval query (h3, {zone['zoneid']}, zone-depth=0-2)")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{zone["zoneid"]}/data', params={'zone-depth': '0-2'})
    data = ZonesDataDggsJsonResponse(**response.json())
    assert response.status_code == 200
    zone_depth_counts = [0, 1, 2]
    for k, v in data.values.items():
        assert len(v) == 3
        for data in v:
            assert data.depth in zone_depth_counts
            assert len(data.data) > 0
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (h3, {zone['zoneid']}, zone-depth=0-2, geometry='zone-centroid', return=geojson)")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{zone["zoneid"]}/data', params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                          headers={'accept': 'application/geo+json'})
    data = ZonesDataGeoJson(**response.json())
    assert len(data.features) > 0
    assert response.status_code == 200

    print(f"Success test case with data-retrieval query (h3, {zone['zoneid']}, zone-depth=0-2, geometry='zone-centroid', return=zarr+zip)")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{zone["zoneid"]}/data', params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                          headers={'accept': 'application/zarr+zip'})
    assert response.status_code == 200
    with open("data_zarr.zip", "wb") as f:
        f.write(response.content)
    z = zarr.open('data_zarr.zip')
    print(z.tree())

    print(f"Empty test case with data-retrieval query (h3, {non_exists[0]}, zone-depth=0-2, geometry='zone-centroid', return=geojson)")
    response = client.get(f'/dggs-api/v1-pre/dggs/h3/zones/{non_exists[0]}/data', params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                          headers={'accept': 'application/geo+json'})
    assert response.status_code == 204

