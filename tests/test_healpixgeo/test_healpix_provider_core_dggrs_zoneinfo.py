from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoResponse
from pydggsapi.schemas.api.collections import Collection
from pydggsapi.schemas.common_geojson import GeoJSONPolygon, GeoJSONPoint
from pydggsapi.dependencies.dggrs_providers.dggal_dggrs_provider import generateZoneGeometry

from fastapi.testclient import TestClient
import pytest
import os
from importlib import reload
from tinydb import TinyDB
import geopandas as gpd
import numpy as np
import shapely
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

for dggrs in all_dggrs:
    dggrs_id, dggrs_config = dggrs.popitem()
    if ("healpixgeo_dggrs_provider" in dggrs_config["classname"]):
        support_grids[dggrs_id] = supported_grids_mapping[dggrs_id]


assert len(support_grids.keys()) > 0


for collection in collections:
    cid, collection_config = collection.popitem()
    if (collection_config['collection_provider']['dggrsId'] in support_grids):
        collection_config['id'] = cid
        collections_dict[cid] = Collection(**collection_config)

assert len(collections_dict.keys()) > 0

validation_df = {}
for collection_name, collection in collections_dict.items():
    bbox = collection.extent.spatial.bbox[0]
    # create a smaller bbox
    #minx, miny = round(minx + 0.1, 3), round(miny + 0.05, 3)
    #maxx, maxy = round(maxx - 0.1, 3), round(maxy - 0.05, 3)
    rf = collection.collection_provider.max_refinement_level - 1
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
    validation_df[collection_name] = {'dggrsid': collection.collection_provider.dggrsId,
                                      'hex': hex_df, 'centroid': centroid_df.set_index('zone_id')}


def test_healpix_core_dggs_zoneinfo():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    for collection_name, df_dict in validation_df.items():
        iloc_pos = np.random.randint(0, df_dict['hex'].shape[0], 1)
        dggrsid = df_dict['dggrsid']
        zone = df_dict['hex'].iloc[iloc_pos[0]]
        zone_centroid_geometry = df_dict['centroid'].loc[zone['zone_id']]['geometry']
        print(f"Success test case with dggs zone info ({dggrsid} {zone['zone_id']})")
        response = client.get(f'/dggs-api/dggs/{dggrsid}/zones/{zone["zone_id"]}')
        zoneinfo = ZoneInfoResponse(**response.json())
        centroid = shapely.geometry.shape(zoneinfo.centroid.__dict__)
        hexagon = shapely.geometry.shape(zoneinfo.geometry.__dict__)
        assert hexagon.equals_exact(zone['geometry'])
        assert centroid.equals_exact(zone_centroid_geometry)
        assert response.status_code == 200

        print("Fail test case with collections (non-existing dggrs id)")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/not_exit/zones/13_00000000')
        assert "not supported" in response.text
        assert response.status_code == 400

        print(f'Success test case with collections on zones info ({collection_name}, {dggrsid}, {zone["zone_id"]})')
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/{dggrsid}/zones/{zone["zone_id"]}')
        zoneinfo = ZoneInfoResponse(**response.json())
        centroid = shapely.geometry.shape(zoneinfo.centroid.__dict__)
        hexagon = shapely.geometry.shape(zoneinfo.geometry.__dict__)
        assert hexagon.equals_exact(zone['geometry'])
        assert centroid.equals_exact(zone_centroid_geometry)
        assert response.status_code == 200

        print(f"Fail test case with collections on non-exist zones info ({collection_name}, {dggrsid}, 13_00000000)")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/{dggrsid}/zones/13_00000000')
        assert response.status_code == 204
