from pydggsapi.schemas.ogc_dggs.dggrs_zones import ZonesResponse, ZonesGeoJson
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
from pprint import pprint
from dggrid4py import DGGRIDv8
from dggrid4py.auxlat import geoseries_to_authalic, geoseries_to_geodetic
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
extra_conf = {
    "output_address_type": 'HIERNDX',
    "output_cell_label_type": 'OUTPUT_ADDRESS_TYPE',
    "output_hier_ndx_system": 'Z7',
    "output_hier_ndx_form": 'DIGIT_STRING',
    # initial vertex lon setting
    "dggs_vert0_lon": 11.20
}

aoi = shapely.Polygon(aoi)
aoi_authalic = geoseries_to_authalic(gpd.GeoSeries(aoi))[0]
non_exist_aoi = shapely.Polygon(non_exist_aoi)
validation_zone_level_5_hexagons_gdf = dggrid.grid_cell_polygons_for_extent('IGEO7', 5, clip_geom=aoi_authalic, **extra_conf)
validation_hexagons_gdf = dggrid.grid_cell_polygons_for_extent('IGEO7', 8, clip_geom=aoi_authalic, **extra_conf)
validation_centroids_gdf = dggrid.grid_cell_centroids_for_extent('IGEO7', 8, clip_geom=aoi_authalic, **extra_conf)

validation_hexagons_gdf.geometry = geoseries_to_geodetic(validation_hexagons_gdf.geometry)
validation_centroids_gdf.geometry = geoseries_to_geodetic(validation_centroids_gdf.geometry)
validation_zone_level_5_hexagons_gdf.geometry = geoseries_to_geodetic(validation_zone_level_5_hexagons_gdf.geometry)

validation_zone_level_5_hexagons_gdf.set_index('name', inplace=True)
validation_hexagons_gdf.set_index('name', inplace=True)
validation_centroids_gdf.set_index('name', inplace=True)


def test_zone_query_dggrs_zones():
    os.environ['dggs_api_config'] = './dggs_api_config_testing.json'
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Fail test case with non existing dggrs id")
    response = client.get('/dggs-api/v1-pre/dggs/non_exist/zones', params={'bbox': "2,3,4,5"})
    assert "not supported" in response.text
    assert response.status_code == 400

    print("Fail test case with dggs zone query (igeo7 , no params)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones')
    assert "Either bbox or parent-zone must be set" in response.text
    assert response.status_code == 400

    print("Fail test case with dggs zone query (igeo7 , bbox with len!=4)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', params={"bbox": "2,3,4"})
    assert "bbox length is not equal to 4" in response.text
    assert response.status_code == 400

    print(f"Success test case with dggs zones query (igeo7, bbox: {aoi.bounds}, compact=False)")
    bounds = list(map(str, aoi.bounds))
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', params={"bbox": ",".join(bounds), 'compact-zone': False})
    zones = ZonesResponse(**response.json())
    return_zones_list = zones.zones
    return_zones_list.sort()
    validation_zones_list = validation_zone_level_5_hexagons_gdf.index.values.astype(str).tolist()
    validation_zones_list.sort()
    assert len(validation_zones_list) == len(return_zones_list)
    assert all([validation_zones_list[i] == z for i, z in enumerate(return_zones_list)])
    assert response.status_code == 200

    print(f"Success test case with dggs zones query (igeo7, bbox: {aoi.bounds}, zone_level=8, compact=False)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', params={"bbox": ",".join(bounds), 'zone-level': 8, 'compact-zone': False})
    zones = ZonesResponse(**response.json())
    return_zones_list = zones.zones
    return_zones_list.sort()
    validation_zones_list = validation_hexagons_gdf.index.values.astype(str).tolist()
    validation_zones_list.sort()
    assert len(validation_zones_list) == len(return_zones_list)
    assert all([validation_zones_list[i] == z for i, z in enumerate(return_zones_list)])
    assert response.status_code == 200

    print(f"Success test case with dggs zones query (igeo7, bbox: {aoi.bounds}, zone_level=2, compact=False)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', params={"bbox": ",".join(bounds), 'zone-level': 2, 'compact-zone': False})
    #pprint(response.json())
    #zones = ZonesResponse(**response.json())
    #return_zones_list = zones.zones
    #assert len(return_zones_list) > 0
    assert response.status_code == 400

    print(f"Success test case with dggs zones query (igeo7, bbox: {aoi.bounds}, zone_level=8, compact=False, geojson)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', headers={'Accept': 'Application/geo+json'},
                          params={"bbox": ",".join(bounds), 'zone-level': 8, 'compact-zone': False})
    print(response.json())
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
                          params={"parent-zone": cellids[0], 'zone-level': 8, 'compact-zone': False})
    zones_geojson = ZonesGeoJson(**response.json())
    return_features_list = zones_geojson.features
    assert response.status_code == 200

    print(f"Empty test case with dggs zones query (igeo7, bbox: {non_exist_aoi.bounds}, zone_level=8, compact=False, geojson)")
    non_exist_bounds = list(map(str, non_exist_aoi.bounds))
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', headers={'Accept': 'Application/geo+json'},
                          params={"bbox": ",".join(non_exist_bounds), 'zone-level': 8, 'compact-zone': False})
    assert response.status_code == 204

    print(f"Empty test case with dggs zones query (igeo7, parent zone: 055266135, zone_level=8, compact=False, geojson)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7/zones', headers={'Accept': 'Application/geo+json'},
                          params={"parent-zone": '055266135', 'zone-level': 8, 'compact-zone': False})
    assert response.status_code == 204
