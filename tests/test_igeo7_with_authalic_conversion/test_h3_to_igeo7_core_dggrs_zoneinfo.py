from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoResponse
from pydggsapi.schemas.api.collections import Collection
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
import h3
import numpy as np
import geopandas as gpd
from tinydb import TinyDB
import shapely
import json


db = TinyDB(os.environ.get('DGGS_API_CONFIG'))
collections = db.table('collections').all()
collections_dict = {}


def _cell_to_shapely(cellid, geometry):
    method = h3.cell_to_boundary if (geometry == 'zone-region') else h3.cell_to_latlng
    GEO = shapely.Polygon if (geometry == 'zone-region') else shapely.Point
    points = method(cellid)
    points = [points] if (geometry != 'zone-region') else points
    points = tuple(p[::-1] for p in points)
    return GEO(points)


for collection in collections:
    cid, collection_config = collection.popitem()
    if (collection_config['collection_provider']['dggrsId'] == 'igeo7'):
        collection_config['id'] = cid
        collections_dict[cid] = Collection(**collection_config)

validation_df = {}

for collection_name, collection in collections_dict.items():
    minx, miny, maxx, maxy = collection.extent.spatial.bbox[0]
    # create a smaller bbox
    minx, miny = round(minx + 0.1, 3), round(miny + 0.05, 3)
    maxx, maxy = round(maxx - 0.1, 3), round(maxy - 0.05, 3)
    bbox = shapely.box(minx, miny, maxx, maxy)
    rf = collection.collection_provider.max_refinement_level - 4
    zoneIds = h3.h3shape_to_cells_experimental(h3.geo_to_h3shape(bbox), rf, contain='overlap')
    geometry = [_cell_to_shapely(z, 'zone-region') for z in zoneIds]
    hex_df = gpd.GeoDataFrame({'zoneid': zoneIds}, geometry=geometry, crs='wgs84')
    geometry = [_cell_to_shapely(z, 'zone-centorid') for z in zoneIds]
    centroid_df = gpd.GeoDataFrame({'zoneid': zoneIds}, geometry=geometry, crs='wgs84').set_index('zoneid')
    validation_df[collection_name] = {'hex': hex_df, 'centroid': centroid_df}

non_exists = ['86411cb77ffffff']


def test_h3_to_igeo7_core_dggs_zoneinfo():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    for collection_name, df_dict in validation_df.items():
        iloc_pos = np.random.randint(0, df_dict['hex'].shape[0], 1)
        zone = df_dict['hex'].iloc[iloc_pos[0]]
        zone_centroid_geometry = df_dict['centroid'].loc[zone['zoneid']]['geometry']
        print(f"Success test case with dggs zone info (h3 {zone['zoneid']})")
        response = client.get(f'/dggs-api/dggs/h3/zones/{zone["zoneid"]}')
        assert response.status_code == 200
        zoneinfo = ZoneInfoResponse(**response.json())
        centroid = shapely.from_geojson(json.dumps(zoneinfo.centroid.__dict__))
        hexagon = shapely.from_geojson(json.dumps(zoneinfo.geometry.__dict__))
        assert hexagon.equals_exact(zone['geometry'])
        assert centroid.equals_exact(zone_centroid_geometry)

        print("Fail test case with collections (non-existing dggrs id)")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/not_exit/zones/{non_exists[0]}')
        assert "not supported" in response.text
        assert response.status_code == 400

        print(f'Success test case with collections on zones info ({collection_name}, h3, {zone["zoneid"]})')
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/h3/zones/{zone["zoneid"]}')
        assert response.status_code == 200
        zoneinfo = ZoneInfoResponse(**response.json())
        centroid = shapely.from_geojson(json.dumps(zoneinfo.centroid.__dict__))
        hexagon = shapely.from_geojson(json.dumps(zoneinfo.geometry.__dict__))
        assert hexagon.equals_exact(zone['geometry'])
        assert centroid.equals_exact(zone_centroid_geometry)

        print(f"Fail test case with collections on non-exist zones info ({collection_name}, h3, {non_exists[0]})")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/h3/zones/{non_exists[0]}')
        assert response.status_code == 204
