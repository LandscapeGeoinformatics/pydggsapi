from pydggsapi.schemas.ogc_dggs.dggrs_zones_info import ZoneInfoResponse
from pydggsapi.schemas.api.collections import Collection
from pydggsapi.dependencies.dggrs_providers.dggal_dggrs_provider import generateZoneGeometry

from fastapi.testclient import TestClient
import pytest
import os
from importlib import reload
from tinydb import TinyDB
import geopandas as gpd
import numpy as np
import shapely
import json
from dggal import Application, pydggal_setup, CRS, ogc, epsg, GeoExtent, Array, GeoPoint
from dggal import IVEA7H, ISEA7H_Z7, rHEALPix, HEALPix

dggal_app = Application(appGlobals=globals())
pydggal_setup(dggal_app)
supported_grids_mapping = {'IVEA7H': IVEA7H,
                           'RHEALPIX': rHEALPix,
                           'ISEA7H_Z7': ISEA7H_Z7,
                           'HEALPIX': HEALPix}

support_grids = {}

db = TinyDB(os.environ.get('dggs_api_config'))
all_dggrs = db.table('dggrs').all()
collections = db.table('collections').all()
collections_dict = {}

for dggrs in all_dggrs:
    dggrs_id, dggrs_config = dggrs.popitem()
    if ("dggal_dggrs_provider" in dggrs_config["classname"]):
        support_grids[dggrs_id] = supported_grids_mapping[dggrs_config['parameters']['grid']]

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
    bbox[0], bbox[1] = bbox[0] + 0.1, bbox[1] + 0.05
    bbox[2], bbox[3] = bbox[2] - 0.1, bbox[3] - 0.05
    rf = collection.collection_provider.max_refinement_level - 1
    mygrid = support_grids[collection.collection_provider.dggrsId]()
    geoextent = GeoExtent(GeoPoint(bbox[1], bbox[0]), GeoPoint(bbox[3], bbox[2]))
    zone_ids = mygrid.listZones(rf, geoextent)
    zone_ids = [int(z) for z in zone_ids]
    zone_ids_textual = [mygrid.getZoneTextID(zid) for zid in zone_ids]
    geometry = [shapely.from_geojson(json.dumps(generateZoneGeometry(mygrid, zid, None, False).__dict__))for zid in zone_ids]
    hex_df = gpd.GeoDataFrame({'zone_id': zone_ids_textual}, geometry=geometry, crs='wgs84')
    geometry = [shapely.from_geojson(json.dumps(generateZoneGeometry(mygrid, zid, None, True).__dict__))for zid in zone_ids]
    centroid_df = gpd.GeoDataFrame({'zone_id': zone_ids_textual}, geometry=geometry, crs='wgs84')
    validation_df[collection_name] = {'dggrsid': collection.collection_provider.dggrsId,
                                      'hex': hex_df, 'centroid': centroid_df.set_index('zone_id')}


def test_dggal_core_dggs_zoneinfo():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    for collection_name, df_dict in validation_df.items():
        iloc_pos = np.random.randint(0, df_dict['hex'].shape[0], 1)
        dggrsid = df_dict['dggrsid']
        zone = df_dict['hex'].iloc[iloc_pos[0]]
        zone_centroid_geometry = df_dict['centroid'].loc[zone['zone_id']]['geometry']
        print(f"Success test case with dggs zone info ({dggrsid} {zone['zone_id']})")
        response = client.get(f'/dggs-api/v1-pre/dggs/{dggrsid}/zones/{zone["zone_id"]}')
        zoneinfo = ZoneInfoResponse(**response.json())
        centroid = shapely.from_geojson(json.dumps(zoneinfo.centroid.__dict__))
        hexagon = shapely.from_geojson(json.dumps(zoneinfo.geometry.__dict__))
        assert hexagon.equals_exact(zone['geometry'])
        assert centroid.equals_exact(zone_centroid_geometry)
        assert response.status_code == 200

        print("Fail test case with collections (non-existing dggrs id)")
        response = client.get(f'/dggs-api/v1-pre/collections/{collection_name}/dggs/not_exit/zones/00000000')
        assert "not supported" in response.text
        assert response.status_code == 400

        print(f'Success test case with collections on zones info ({collection_name}, {dggrsid}, {zone["zone_id"]})')
        response = client.get(f'/dggs-api/v1-pre/collections/{collection_name}/dggs/{dggrsid}/zones/{zone["zone_id"]}')
        zoneinfo = ZoneInfoResponse(**response.json())
        centroid = shapely.from_geojson(json.dumps(zoneinfo.centroid.__dict__))
        hexagon = shapely.from_geojson(json.dumps(zoneinfo.geometry.__dict__))
        assert hexagon.equals_exact(zone['geometry'])
        assert centroid.equals_exact(zone_centroid_geometry)
        assert response.status_code == 200

        print(f"Fail test case with collections on non-exist zones info ({collection_name}, {dggrsid}, 00000000)")
        response = client.get(f'/dggs-api/v1-pre/collections/{collection_name}/dggs/{dggrsid}/zones/00000000')
        assert response.status_code == 204
