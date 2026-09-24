from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import ZonesDataDggsJsonResponse, ZonesDataGeoJson
from pydggsapi.schemas.api.collections import Collection
from pydggsapi.schemas.common_geojson import GeoJSONPolygon, GeoJSONPoint
from pydggsapi.dependencies.dggrs_providers.dggal_dggrs_provider import generateZoneGeometry
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
import shapely
import json
from tinydb import TinyDB
import geopandas as gpd
import numpy as np
import zarr
import healpix_geo
from typing import List

support_grids = {"healpixgeo_zuniq": healpix_geo.zuniq}


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

# only look for nested indexed collections

# test on nested indexed collections only
for collection in collections:
    cid, collection_config = collection.popitem()
    if (collection_config['collection_provider']['dggrsId'] in ["healpixgeo_nested"]):
        collection_config['id'] = cid
        collections_dict[cid] = Collection(**collection_config)

assert len(collections_dict.keys()) > 0

validation_df = {}
for collection_name, collection in collections_dict.items():
    minx, miny, maxx, maxy = collection.extent.spatial.bbox[0]
    # create a smaller bbox
    minx, miny = round(minx + 0.1, 3), round(miny + 0.05, 3)
    maxx, maxy = round(maxx - 0.1, 3), round(maxy - 0.05, 3)
    rf = collection.collection_provider.max_refinement_level - 2
    mygrid = support_grids["healpixgeo_zuniq"]
    results = mygrid.zone_coverage((minx, miny, maxx, maxy), rf, ellipsoid="WGS84", flat=False)
    zuniq_zones_ids = results[0]

    generateZoneGeometry = _zuniq_generateZoneGeometries
    textual_zones_ids = list(map(lambda x: f"{str(x)}", zuniq_zones_ids))

    geometry = generateZoneGeometry(zuniq_zones_ids, rf, False)
    geometry = list(map(lambda g: shapely.geometry.shape(g.__dict__), geometry))
    hex_df = gpd.GeoDataFrame({'zone_id': textual_zones_ids}, geometry=geometry, crs='wgs84')
    geometry = generateZoneGeometry(zuniq_zones_ids, rf, True)
    geometry = list(map(lambda g: shapely.geometry.shape(g.__dict__), geometry))
    centroid_df = gpd.GeoDataFrame({'zone_id': textual_zones_ids}, geometry=geometry, crs='wgs84')

    non_exist_bbox = non_exist_aoi.bounds
    non_exist_zone_ids = mygrid.zone_coverage(tuple(non_exist_bbox), rf, ellipsoid="WGS84", flat=False)
    non_exist_zone_ids = non_exist_zone_ids[0]
    textual_non_exist_zone_ids = list(map(lambda x: f"{str(x)}", non_exist_zone_ids))

    validation_df[collection_name] = {'hex': hex_df, 'centroid': centroid_df.set_index('zone_id'),
                                      'dggrsid': "healpixgeo_zuniq",
                                      'max_rf': collection.collection_provider.max_refinement_level,
                                      'zone_rf': rf,
                                      'non_exist_zoneids': textual_non_exist_zone_ids
                                      }


def test_healpixgeo_data_retrieval_zuniq_to_nested():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    print("Fail test case with non existing dggrs id")
    response = client.get('/dggs-api/dggs/non_exist/zones/0013415612/data')
    assert "not supported" in response.text
    assert response.status_code == 400

    for collection_name, df_dict in validation_df.items():
        iloc_pos = np.random.randint(0, df_dict['hex'].shape[0], 1)
        max_rf = df_dict['max_rf']
        zone_rf = df_dict['zone_rf']
        dggrsid = df_dict['dggrsid']
        zone = df_dict['hex'].iloc[iloc_pos[0]]
        over_rf_depth = max_rf - zone_rf + 1
        print(f"Fail test case withdata-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth={over_rf_depth}) over refinement")
        response = client.get(f"/dggs-api/collections/{collection_name}/dggs/{dggrsid}/zones/{zone['zone_id']}/data",
                              params={"zone-depth": over_rf_depth})
        assert "over refinement" in response.text
        assert response.status_code == 400

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, default zone-depth = 1)")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/{dggrsid}/zones/{zone["zone_id"]}/data')
        assert response.status_code == 200
        data = ZonesDataDggsJsonResponse(**response.json())
        for k, v in data.values.items():
            assert len(v) == 1
            assert v[0].depth == 1
            assert len(v[0].data) > 0

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth=0 ,return = geojson)")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/{dggrsid}/zones/{zone["zone_id"]}/data',
                              headers={'accept': 'application/geo+json'},
                              params={'zone-depth': '0'})
        assert response.status_code == 200
        data = ZonesDataGeoJson(**response.json())
        assert len(data.features) > 0

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth=0,return = geojson, geometry='zone-centroid')")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/{dggrsid}/zones/{zone["zone_id"]}/data',
                              params={'geometry': 'zone-centroid', 'zone-depth': '0'},
                              headers={'accept': 'application/geo+json'})
        assert response.status_code == 200
        data = ZonesDataGeoJson(**response.json())
        assert len(data.features) > 0

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth=2)")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/{dggrsid}/zones/{zone["zone_id"]}/data',
                              params={'zone-depth': '2'})
        data = ZonesDataDggsJsonResponse(**response.json())
        assert response.status_code == 200
        for k, v in data.values.items():
            assert len(v) == 1
            assert v[0].depth == 2
            assert len(v[0].data) > 0
        assert response.status_code == 200

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth=1-2)")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/{dggrsid}/zones/{zone["zone_id"]}/data',
                              params={'zone-depth': '1-2'})
        data = ZonesDataDggsJsonResponse(**response.json())
        assert response.status_code == 200
        zone_depth_counts = [1, 2]
        for k, v in data.values.items():
            assert len(v) == 2
            for data in v:
                assert data.depth in zone_depth_counts
                assert len(data.data) > 0

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth=0-2)")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/{dggrsid}/zones/{zone["zone_id"]}/data',
                              params={'zone-depth': '0-2'})
        data = ZonesDataDggsJsonResponse(**response.json())
        assert response.status_code == 200
        zone_depth_counts = [0, 1, 2]
        for k, v in data.values.items():
            assert len(v) == 3
            for data in v:
                assert data.depth in zone_depth_counts
                assert len(data.data) > 0
        assert response.status_code == 200

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth=0-2, geometry='zone-centroid', return=geojson)")
        response = client.get(f'/dggs-api/dggs/{dggrsid}/zones/{zone["zone_id"]}/data', params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                              headers={'accept': 'application/geo+json'})
        data = ZonesDataGeoJson(**response.json())
        assert len(data.features) > 0
        assert response.status_code == 200

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth=0-2, geometry='zone-centroid', return=zarr+zip)")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/{dggrsid}/zones/{zone["zone_id"]}/data',
                              params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                              headers={'accept': 'application/zarr+zip'})
        assert response.status_code == 200
        with open("data_zarr.zip", "wb") as f:
            f.write(response.content)
        store = zarr.storage.ZipStore("data_zarr.zip", read_only=True)
        z = zarr.open(store=store, mode="r")
        print(z.tree())

        iloc_pos = np.random.randint(0, len(df_dict['non_exist_zoneids']), 1)
        non_exists_zoneid = df_dict['non_exist_zoneids'][iloc_pos[0]]
        print(f"Empty test case with data-retrieval query ({dggrsid}, {non_exists_zoneid}, zone-depth=0-2, geometry='zone-centroid', return=geojson)")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/{dggrsid}/zones/{non_exists_zoneid}/data',
                              params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                              headers={'accept': 'application/geo+json'})
        assert response.status_code == 204


