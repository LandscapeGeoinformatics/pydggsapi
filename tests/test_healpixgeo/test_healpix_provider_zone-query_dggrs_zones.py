from pydggsapi.schemas.ogc_dggs.dggrs_zones import ZonesResponse, ZonesGeoJson
from pydggsapi.schemas.api.collections import Collection
from pydggsapi.schemas.common_geojson import GeoJSONPolygon, GeoJSONPoint
from pydggsapi.dependencies.dggrs_providers.dggal_dggrs_provider import generateZoneGeometry
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
from tinydb import TinyDB
import numpy as np
import shapely
import json
import geopandas as gpd
import healpix_geo
from typing import List

supported_grids_mapping = {"healpixgeo_nested": healpix_geo.nested,
                           "healpixgeo_zuniq": healpix_geo.zuniq}

support_grids = {}

db = TinyDB(os.environ.get('DGGS_API_CONFIG'))
all_dggrs = db.table('dggrs').all()
collections = db.table('collections').all()
collections_dict = {}


def _nested_generateZoneGeometries(zoneIds: List[int], refinement_level: int, centroids: bool = False) -> GeoJSONPoint | GeoJSONPolygon | None:
    if centroids:
        lon, lat = healpix_geo.nested.healpix_to_lonlat(zoneIds, refinement_level, "WGS84")
        points = np.stack([lon, lat], axis=-1)
        # for list only consist of one zone, the shape of vertices is [1, 1, 2]
        if (len(zoneIds) == 1):
            points = np.squeeze(points, axis=1)
        points = list(map(lambda x: GeoJSONPoint(type="Point", coordinates=(x[0], x[1])), points))
        return points
    else:
        lon, lat = healpix_geo.nested.vertices(zoneIds, refinement_level, "WGS84")
        vertices = np.stack([lon, lat], axis=-1)
        vertices = np.squeeze(vertices.view(dtype=np.dtype([('x', 'float64'), ('y', 'float64')])), axis=-1)
        # for list only consist of one zone, the shape of vertices is [1, 1, 4]
        if (len(zoneIds) == 1):
            vertices = np.squeeze(vertices, axis=1)
        polygon = list(map(lambda x: GeoJSONPolygon(type="Polygon", coordinates=[x.tolist()]), vertices))
        return polygon


def _zuniq_generateZoneGeometries(zoneIds: List[int], refinement_level: None, centroids: bool = False) -> GeoJSONPoint | GeoJSONPolygon | None:
    if centroids:
        lon, lat = healpix_geo.zuniq.healpix_to_lonlat(zoneIds, "WGS84")
        points = np.stack([lon, lat], axis=-1)
        # for list only consist of one zone, the shape of vertices is [1, 1, 2]
        if (len(zoneIds) == 1):
            points = np.squeeze(points, axis=1)
        points = list(map(lambda x: GeoJSONPoint(type="Point", coordinates=(x[0], x[1])), points))
        return points
    else:
        lon, lat = healpix_geo.zuniq.vertices(zoneIds, "WGS84")
        vertices = np.stack([lon, lat], axis=-1)
        vertices = np.squeeze(vertices.view(dtype=np.dtype([('x', 'float64'), ('y', 'float64')])), axis=-1)
        # for list only consist of one zone, the shape of vertices is [1, 1, 4]
        if (len(zoneIds) == 1):
            vertices = np.squeeze(vertices, axis=1)
        polygon = list(map(lambda x: GeoJSONPolygon(type="Polygon", coordinates=[x.tolist()]), vertices))
        return polygon


non_exist_aoi = shapely.Polygon([[113.81837742963569, 22.521237932154797],
                 [113.81837742963569, 22.13760392858767],
                 [114.41438573041694, 22.13760392858767],
                 [114.41438573041694, 22.521237932154797]])


for dggrs in all_dggrs:
    dggrs_id, dggrs_config = dggrs.popitem()
    if ("healpixgeo_dggrs_provider" in dggrs_config["classname"]):
        support_grids[dggrs_id] = supported_grids_mapping[dggrs_id]

assert len(support_grids.keys()) > 0


for collection in collections:
    cid, collection_config = collection.popitem()
    if (collection_config['collection_provider']['dggrsId'] in list(support_grids.keys())):
        collection_config['id'] = cid
        collections_dict[cid] = Collection(**collection_config)

assert len(collections_dict.keys()) > 0

validation_df = {}
for collection_name, collection in collections_dict.items():
    bbox = collection.extent.spatial.bbox[0]
    # create a smaller bbox
    # minx, miny = round(minx + 0.1, 3), round(miny + 0.05, 3)
    # maxx, maxy = round(maxx - 0.1, 3), round(maxy - 0.05, 3)
    rf = collection.collection_provider.max_refinement_level - 2
    mygrid = support_grids[collection.collection_provider.dggrsId]
    results = mygrid.zone_coverage(tuple(bbox), rf, ellipsoid="WGS84", flat=False)
    zones_ids = results[0]

    if ("nested" in collection.collection_provider.dggrsId):
        generateZoneGeometry = _nested_generateZoneGeometries
        textual_zones_ids = list(map(lambda x: f"{str(rf).zfill(2)}_{str(x)}", zones_ids))
    else:
        generateZoneGeometry = _zuniq_generateZoneGeometries
        textual_zones_ids = list(map(lambda x: f"{str(x)}", zones_ids))

    geometry = generateZoneGeometry(zones_ids, rf, False)
    geometry = list(map(lambda g: shapely.geometry.shape(g.__dict__), geometry))
    hex_df = gpd.GeoDataFrame({'zone_id': textual_zones_ids}, geometry=geometry, crs='wgs84')
    geometry = generateZoneGeometry(zones_ids, rf, True)
    geometry = list(map(lambda g: shapely.geometry.shape(g.__dict__), geometry))
    centroid_df = gpd.GeoDataFrame({'zone_id': textual_zones_ids}, geometry=geometry, crs='wgs84')

    rf2 = rf - 3
    results = mygrid.zone_coverage(tuple(bbox), rf2, ellipsoid="WGS84", flat=False)
    zones_ids = results[0]
    if ("nested" in collection.collection_provider.dggrsId):
        generateZoneGeometry = _nested_generateZoneGeometries
        textual_zones_ids = list(map(lambda x: f"{str(rf2).zfill(2)}_{str(x)}", zones_ids))
    else:
        generateZoneGeometry = _zuniq_generateZoneGeometries
        textual_zones_ids = list(map(lambda x: f"{str(x)}", zones_ids))

    geometry = generateZoneGeometry(zones_ids, rf2, False)
    geometry = list(map(lambda g: shapely.geometry.shape(g.__dict__), geometry))
    hex_df2 = gpd.GeoDataFrame({'zone_id': textual_zones_ids}, geometry=geometry, crs='wgs84')
    geometry = generateZoneGeometry(zones_ids, rf2, True)
    geometry = list(map(lambda g: shapely.geometry.shape(g.__dict__), geometry))
    centroid_df2 = gpd.GeoDataFrame({'zone_id': textual_zones_ids}, geometry=geometry, crs='wgs84')

    validation_df[collection_name] = {rf: {'hex': hex_df, 'centroid': centroid_df.set_index('zone_id')},
                                      rf2: {'hex': hex_df2, 'centroid': centroid_df2.set_index('zone_id')},
                                      'dggrsid': collection.collection_provider.dggrsId,
                                      'aoi': bbox}


def test_healpixgeo_zone_query_dggrs_zones():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    print("Fail test case with non existing dggrs id")
    response = client.get('/dggs-api/dggs/non_exist/zones', params={'bbox': "2,3,4,5"})
    assert "not supported" in response.text
    assert response.status_code == 400

    for collection_name, df_dict in validation_df.items():

        dggrsid = df_dict.pop('dggrsid')
        aoi = shapely.box(*df_dict.pop('aoi'))
        print(f"Fail test case with dggs zones query ({dggrsid}, bbox: {non_exist_aoi.bounds}, compact=False), missing zone-level")
        bounds = list(map(str, non_exist_aoi.bounds))
        response = client.get(f'/dggs-api/dggs/{dggrsid}/zones', params={"bbox": ",".join(bounds), 'compact-zones': False})
        assert "zone-level must be specified" in response.text
        assert response.status_code == 400

        print("Fail test case with dggs zone query ({dggrsid} , no params)")
        response = client.get(f'/dggs-api/dggs/{dggrsid}/zones')
        assert "Either bbox or parent-zone must be set" in response.text
        assert response.status_code == 400

        print("Fail test case with dggs zone query ({dggrsid} , bbox with len!=4)")
        response = client.get(f'/dggs-api/dggs/{dggrsid}/zones', params={"bbox": "2,3,4"})
        assert "bbox length is not equal to 4" in response.text
        assert response.status_code == 400

        print(f"Empty test case with dggs zones query ({dggrsid}, bbox: {non_exist_aoi.bounds}, zone_level=8, compact=False, geojson)")
        non_exist_bounds = list(map(str, non_exist_aoi.bounds))
        response = client.get(f'/dggs-api/dggs/{dggrsid}/zones', headers={'Accept': 'Application/geo+json'},
                              params={"bbox": ",".join(non_exist_bounds), 'zone-level': 8, 'compact-zones': False})
        assert response.status_code == 204

        for rf, validation_set in df_dict.items():
            bounds = list(map(str, aoi.bounds))
            print(f"Success test case with dggs zones query ({dggrsid}, bbox: {aoi.bounds}, zone_level={rf}, compact=False)")
            response = client.get(f'/dggs-api/dggs/{dggrsid}/zones', params={"bbox": ",".join(bounds), 'zone-level': rf, 'compact-zones': False})
            assert response.status_code == 200
            zones = ZonesResponse(**response.json())
            return_zones_list = zones.zones
            return_zones_list.sort()
            validation_zones_list = validation_set['hex'].sort_values('zone_id')['zone_id'].tolist()
            validation_zones_list.sort()
            assert all(np.isin(return_zones_list, validation_zones_list))

            iloc_pos = np.random.randint(0, validation_set['hex'].shape[0], 1)
            zone = validation_set['hex'].iloc[iloc_pos[0]]
            print(f"Success test case with dggs zones query ({dggrsid}, parent zone: {zone['zone_id']}, zone_level={rf + 1}, compact=False, geojson)")
            response = client.get(f'/dggs-api/dggs/{dggrsid}/zones', headers={'Accept': 'Application/geo+json'},
                                  params={"parent-zone": zone['zone_id'], 'zone-level': rf + 1, 'compact-zones': False})
            assert (response.status_code == 200 or response.status_code == 204)

            print(f"Success test case with dggs zones query ({dggrsid}, bbox: {aoi.bounds}, zone_level={rf}, compact=False, geojson)")
            response = client.get(f'/dggs-api/dggs/{dggrsid}/zones', headers={'Accept': 'Application/geo+json'},
                                  params={"bbox": ",".join(bounds), 'zone-level': rf, 'compact-zones': False})
            assert response.status_code == 200
            zones_geojson = ZonesGeoJson(**response.json())
            return_features_list = zones_geojson.features
            geometry = [shapely.geometry.shape(f.geometry.__dict__) for f in return_features_list]
            zonesID = [f.properties['zoneId'] for f in return_features_list]
            return_gdf = gpd.GeoDataFrame({'zone_id': zonesID}, geometry=geometry, crs='wgs84').set_index('zone_id').sort_index()
            validation_hexagons_gdf = validation_set['hex'].set_index('zone_id').sort_index()
            assert all(np.isin(return_zones_list, validation_zones_list))
            join_df = return_gdf.join(validation_hexagons_gdf, rsuffix='_validation')
            assert all(join_df['geometry'].apply(lambda x: x.equals_exact(join_df['geometry_validation'], normalize=True)))




