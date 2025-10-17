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
cellids = ['00010220', '0001022011', '0001022012']
zone_level = [5, 6, 7, 8, 9]

aoi = shapely.Polygon(aoi)
non_exist_aoi = shapely.Polygon(non_exist_aoi)
validation_zone_level_5_hexagons_gdf = dggrid.grid_cell_polygons_for_extent('IGEO7', 5, clip_geom=aoi, output_address_type='Z7_STRING')
validation_hexagons_gdf = dggrid.grid_cell_polygons_for_extent('IGEO7', 8, clip_geom=aoi, output_address_type='Z7_STRING')
validation_centroids_gdf = dggrid.grid_cell_centroids_for_extent('IGEO7', 8, clip_geom=aoi, output_address_type='Z7_STRING')
validation_zone_level_5_hexagons_gdf.set_index('name', inplace=True)
validation_hexagons_gdf.set_index('name', inplace=True)
validation_centroids_gdf.set_index('name', inplace=True)


def test_zone_query_dggrs_zones_empty_config():
    os.environ['dggs_api_config'] = './empty.json'
    try:
        import pydggsapi.api
        app = reload(pydggsapi.api).app
        client = TestClient(app)
    except Exception as e:
        print(f"Testing with dggrs zoneinfo (no dggrs defined): {e}")


def test_zone_query_dggrs_zones():
    os.environ['dggs_api_config'] = './dggs_api_config_testing.json'
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Fail test case with non existing dggrs id")
    response = client.get('/dggs-api/v1-pre/dggs/non_exist/zones', params={'bbox': "2,3,4,5"})
    pprint(response.json())
    assert "not supported" in response.text
    assert response.status_code == 400

    print("Fail test case with dggs zone query (igeo7 , no params)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones')
    pprint(response.json())
    assert "Either bbox or parent-zone must be set" in response.text
    assert response.status_code == 400

    print("Fail test case with dggs zone query (igeo7 , bbox with len!=4)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', params={"bbox": "2,3,4"})
    pprint(response.json())
    assert "bbox length is not equal to 4" in response.text
    assert response.status_code == 400

    print(f"Success test case with dggs zones query (igeo7, bbox: {aoi.bounds}, compact=False)")
    bounds = list(map(str, aoi.bounds))
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', params={"bbox": ",".join(bounds), 'compact_zone': False})
    pprint(response.json())
    zones = ZonesResponse(**response.json())
    return_zones_list = zones.zones
    return_zones_list.sort()
    validation_zones_list = validation_zone_level_5_hexagons_gdf.index.values.astype(str).tolist()
    validation_zones_list.sort()
    assert len(validation_zones_list) == len(return_zones_list)
    assert all([validation_zones_list[i] == z for i, z in enumerate(return_zones_list)])
    assert response.status_code == 200

    print(f"Success test case with dggs zones query (igeo7, bbox: {aoi.bounds}, zone_level=8, compact=False)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', params={"bbox": ",".join(bounds), 'zone_level': 8, 'compact_zone': False})
    pprint(response.json())
    zones = ZonesResponse(**response.json())
    return_zones_list = zones.zones
    return_zones_list.sort()
    validation_zones_list = validation_hexagons_gdf.index.values.astype(str).tolist()
    validation_zones_list.sort()
    assert len(validation_zones_list) == len(return_zones_list)
    assert all([validation_zones_list[i] == z for i, z in enumerate(return_zones_list)])
    assert response.status_code == 200

    print(f"Success test case with dggs zones query (igeo7, bbox: {aoi.bounds}, zone_level=2, compact=False)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', params={"bbox": ",".join(bounds), 'zone_level': 2, 'compact_zone': False})
    #pprint(response.json())
    #zones = ZonesResponse(**response.json())
    #return_zones_list = zones.zones
    #assert len(return_zones_list) > 0
    assert response.status_code == 204

    print(f"Success test case with dggs zones query (igeo7, bbox: {aoi.bounds}, zone_level=8, compact=False, geojson)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', headers={'Accept': 'Application/geo+json'},
                          params={"bbox": ",".join(bounds), 'zone_level': 8, 'compact_zone': False})
    pprint(response.json())
    zones_geojson = ZonesGeoJson(**response.json())
    return_features_list = zones_geojson.features
    geometry = [shapely.from_geojson(json.dumps(f.geometry.__dict__)) for f in return_features_list]
    zonesID = [f.properties['zoneId'] for f in return_features_list]
    return_gdf = gpd.GeoDataFrame({'name': zonesID}, geometry=geometry, crs='wgs84').set_index('name')
    validation_hexagons_gdf.sort_index(inplace=True)
    return_gdf.sort_index(inplace=True)
    assert len(return_gdf) == len(validation_hexagons_gdf)
    assert all([shapely.equals(return_gdf.iloc[i]['geometry'], validation_hexagons_gdf.iloc[i]['geometry']) for i in range(len(return_gdf))])
    assert response.status_code == 200

    print(f"Success test case with dggs zones query (igeo7, parent zone: {cellids[0]}, zone_level=8, compact=False, geojson)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', headers={'Accept': 'Application/geo+json'},
                          params={"parent_zone": cellids[0], 'zone_level': 8, 'compact_zone': False})
    pprint(response.json())
    zones_geojson = ZonesGeoJson(**response.json())
    return_features_list = zones_geojson.features
    assert response.status_code == 200

    print(f"Empty test case with dggs zones query (igeo7, bbox: {non_exist_aoi.bounds}, zone_level=8, compact=False, geojson)")
    non_exist_bounds = list(map(str, non_exist_aoi.bounds))
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', headers={'Accept': 'Application/geo+json'},
                          params={"bbox": ",".join(non_exist_bounds), 'zone_level': 8, 'compact_zone': False})
    assert response.status_code == 204

    print(f"Empty test case with dggs zones query (igeo7, parent zone: 055266135, zone_level=8, compact=False, geojson)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', headers={'Accept': 'Application/geo+json'},
                          params={"parent_zone": '055266135', 'zone_level': 8, 'compact_zone': False})
    assert response.status_code == 204
