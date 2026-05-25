from pydggsapi.schemas.ogc_dggs.dggrs_zones import ZonesResponse, ZonesGeoJson
from pydggsapi.schemas.api.collections import Collection
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
from pprint import pprint
from dggrid4py import DGGRIDv8
from dggrid4py.auxlat import geoseries_to_authalic, geoseries_to_geodetic
from geopandas import GeoSeries
from tinydb import TinyDB
import tempfile
import shapely
import json
import geopandas as gpd
import numpy as np


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

db = TinyDB(os.environ.get('dggs_api_config'))
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
    hex_df = dggrid.grid_cell_polygons_for_extent('IGEO7', 5, clip_geom=authalic_aoi, **extra_conf)
    centroid_df = dggrid.grid_cell_centroids_from_cellids(hex_df['name'], 'IGEO7', 5, **extra_conf)
    hex_df['geometry'] = geoseries_to_geodetic(hex_df['geometry'])
    centroid_df['geometry'] = geoseries_to_geodetic(centroid_df['geometry'])

    hex_df2 = dggrid.grid_cell_polygons_for_extent('IGEO7', max_rf-2, clip_geom=authalic_aoi, **extra_conf)
    centroid_df2 = dggrid.grid_cell_centroids_from_cellids(hex_df2['name'], 'IGEO7', max_rf-2, **extra_conf)
    hex_df2['geometry'] = geoseries_to_geodetic(hex_df2['geometry'])
    centroid_df2['geometry'] = geoseries_to_geodetic(centroid_df2['geometry'])
    validation_df[collection_name] = { 5 : {'hex': hex_df, 'centroid': centroid_df.set_index('name'),
                                                   'aoi': aoi},
                                       max_rf-2: {'hex': hex_df2, 'centroid': centroid_df2.set_index('name'),
                                                'aoi': aoi}
                                      }



non_exist_aoi = shapely.Polygon([[113.81837742963569, 22.521237932154797],
                 [113.81837742963569, 22.13760392858767],
                 [114.41438573041694, 22.13760392858767],
                 [114.41438573041694, 22.521237932154797]])


def test_zone_query_dggrs_zones():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Fail test case with non existing dggrs id")
    response = client.get('/dggs-api/v1-pre/dggs/non_exist/zones', params={'bbox': "2,3,4,5"})
    assert "not supported" in response.text
    assert response.status_code == 400

    print(f"Fail test case with dggs zones query (igeo7, bbox: {non_exist_aoi.bounds}, compact=False), missing zone-level")
    bounds = list(map(str, non_exist_aoi.bounds))
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', params={"bbox": ",".join(bounds), 'compact-zone': False})
    assert "zone-level must be specified" in response.text
    assert response.status_code == 400

    print("Fail test case with dggs zone query (igeo7 , no params)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones')
    assert "Either bbox or parent-zone must be set" in response.text
    assert response.status_code == 400

    print("Fail test case with dggs zone query (igeo7 , bbox with len!=4)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', params={"bbox": "2,3,4"})
    assert "bbox length is not equal to 4" in response.text
    assert response.status_code == 400

    print(f"Empty test case with dggs zones query (igeo7, bbox: {non_exist_aoi.bounds}, zone_level=8, compact=False, geojson)")
    non_exist_bounds = list(map(str, non_exist_aoi.bounds))
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', headers={'Accept': 'Application/geo+json'},
                          params={"bbox": ",".join(non_exist_bounds), 'zone-level': 8, 'compact-zone': False})
    assert response.status_code == 204

    print(f"Empty test case with dggs zones query (igeo7, parent zone: 055266135, zone_level=8, compact=False, geojson)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', headers={'Accept': 'Application/geo+json'},
                          params={"parent-zone": '055266135', 'zone-level': 8, 'compact-zone': False})
    assert response.status_code == 204

    for collection_name, df_dict in validation_df.items():
        rf5_validation_set = df_dict.pop(5)
        aoi = rf5_validation_set['aoi']
        print(f"Success test case with dggs zones query (igeo7, bbox: {aoi.bounds}, zone-level=5,compact=False)")
        bounds = list(map(str, aoi.bounds))
        response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', params={"bbox": ",".join(bounds), "zone-level": 5, "compact-zone": False})
        zones = ZonesResponse(**response.json())
        return_zones_list = zones.zones
        return_zones_list.sort()
        validation_zones_list = rf5_validation_set['hex'].sort_values('name')['name'].tolist()
        validation_zones_list.sort()
        assert len(validation_zones_list) == len(return_zones_list)
        assert all([validation_zones_list[i] == z for i, z in enumerate(return_zones_list)])
        assert response.status_code == 200

        iloc_pos = np.random.randint(0, rf5_validation_set['hex'].shape[0], 1)
        zone = rf5_validation_set['hex'].iloc[iloc_pos[0]]
        print(f"Success test case with dggs zones query (igeo7, parent zone: {zone['name']}, zone_level=8, compact=False, geojson)")
        response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', headers={'Accept': 'Application/geo+json'},
                              params={"parent-zone": zone['name'], 'zone-level': 8, 'compact-zone': False})
        zones_geojson = ZonesGeoJson(**response.json())
        return_features_list = zones_geojson.features
        assert response.status_code == 200

        for rf, validation_set in df_dict.items():
            aoi = validation_set['aoi']
            bounds = list(map(str, aoi.bounds))
            print(f"Success test case with dggs zones query (igeo7, bbox: {aoi.bounds}, zone_level={rf}, compact=False)")
            response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', params={"bbox": ",".join(bounds), 'zone-level': rf, 'compact-zone': False})
            zones = ZonesResponse(**response.json())
            return_zones_list = zones.zones
            return_zones_list.sort()
            validation_zones_list = validation_set['hex'].sort_values('name')['name'].tolist()
            validation_zones_list.sort()
            assert len(return_zones_list) == len(validation_zones_list)
            assert all([validation_zones_list[i] == z for i, z in enumerate(return_zones_list)])
            assert response.status_code == 200

            print(f"Success test case with dggs zones query (igeo7, bbox: {aoi.bounds}, zone_level={rf}, compact=False, geojson)")
            response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', headers={'Accept': 'Application/geo+json'},
                                  params={"bbox": ",".join(bounds), 'zone-level': rf, 'compact-zone': False})
            zones_geojson = ZonesGeoJson(**response.json())
            return_features_list = zones_geojson.features
            geometry = [shapely.from_geojson(json.dumps(f.geometry.__dict__)) for f in return_features_list]
            zonesID = [f.properties['zoneId'] for f in return_features_list]
            return_gdf = gpd.GeoDataFrame({'name': zonesID}, geometry=geometry, crs='wgs84').set_index('name').sort_index()
            validation_hexagons_gdf = validation_set['hex'].set_index('name').sort_index()
            assert len(return_gdf) == len(validation_hexagons_gdf)
            assert all([shapely.equals(return_gdf.iloc[i]['geometry'], validation_hexagons_gdf.iloc[i]['geometry']) for i in range(len(return_gdf))])
            assert response.status_code == 200

