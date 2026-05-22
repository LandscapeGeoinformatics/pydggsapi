from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import ZonesDataDggsJsonResponse, ZonesDataGeoJson
from pydggsapi.schemas.api.collections import Collection
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
non_exist_aoi = shapely.Polygon([[113.81837742963569, 22.521237932154797],
                 [113.81837742963569, 22.13760392858767],
                 [114.41438573041694, 22.13760392858767],
                 [114.41438573041694, 22.521237932154797]])


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
    bbox[0], bbox[1], bbox[2], bbox[3] = round(bbox[0] + 0.1 ,3), round(bbox[1] + 0.05, 3), round(bbox[2] - 0.1, 3), round(bbox[3] - 0.05, 3)
    rf = collection.collection_provider.max_refinement_level - 2
    mygrid = support_grids[collection.collection_provider.dggrsId]()
    geoextent = GeoExtent(GeoPoint(bbox[1], bbox[0]), GeoPoint(bbox[3], bbox[2]))
    zone_ids = mygrid.listZones(rf, geoextent)
    zone_ids = [int(z) for z in zone_ids]
    zone_ids_textual = [mygrid.getZoneTextID(zid) for zid in zone_ids]
    geometry = [shapely.from_geojson(json.dumps(generateZoneGeometry(mygrid, zid, None, False).__dict__))for zid in zone_ids]
    hex_df = gpd.GeoDataFrame({'zone_id': zone_ids_textual}, geometry=geometry, crs='wgs84')
    geometry = [shapely.from_geojson(json.dumps(generateZoneGeometry(mygrid, zid, None, True).__dict__))for zid in zone_ids]
    centroid_df = gpd.GeoDataFrame({'zone_id': zone_ids_textual}, geometry=geometry, crs='wgs84')

    non_exist_bbox = non_exist_aoi.bounds
    geoextent = GeoExtent(GeoPoint(non_exist_bbox[1], non_exist_bbox[0]), GeoPoint(non_exist_bbox[3], non_exist_bbox[2]))
    non_exist_zone_ids = mygrid.listZones(rf, geoextent)
    non_exist_zone_ids = [mygrid.getZoneTextID(zid) for zid in non_exist_zone_ids]

    validation_df[collection_name] = {'hex': hex_df, 'centroid': centroid_df.set_index('zone_id'),
                                      'dggrsid': collection.collection_provider.dggrsId,
                                      'max_rf': collection.collection_provider.max_refinement_level,
                                      'zone_rf': rf,
                                      'non_exist_zoneids': non_exist_zone_ids
                                      }


def test_dggal_data_retrieval():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    print("Fail test case with non existing dggrs id")
    response = client.get('/dggs-api/v1-pre/dggs/non_exist/zones/0013415612/data')
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
        response = client.get(f"/dggs-api/v1-pre/dggs/{dggrsid}/zones/{zone['zone_id']}/data", params={"zone-depth": over_rf_depth})
        assert "over refinement" in response.text
        assert response.status_code == 400

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, default zone-depth = 1)")
        response = client.get(f'/dggs-api/v1-pre/dggs/{dggrsid}/zones/{zone["zone_id"]}/data')
        assert response.status_code == 200
        data = ZonesDataDggsJsonResponse(**response.json())
        for k, v in data.values.items():
            assert len(v) == 1
            assert v[0].depth == 1
            assert len(v[0].data) > 0

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth=0 ,return = geojson)")
        response = client.get(f'/dggs-api/v1-pre/dggs/{dggrsid}/zones/{zone["zone_id"]}/data', headers={'accept': 'application/geo+json'},
                              params={'zone-depth': '0'})
        assert response.status_code == 200
        data = ZonesDataGeoJson(**response.json())
        assert len(data.features) > 0

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth=0,return = geojson, geometry='zone-centroid')")
        response = client.get(f'/dggs-api/v1-pre/dggs/{dggrsid}/zones/{zone["zone_id"]}/data', params={'geometry': 'zone-centroid', 'zone-depth': '0'},
                              headers={'accept': 'application/geo+json'})
        assert response.status_code == 200
        data = ZonesDataGeoJson(**response.json())
        assert len(data.features) > 0

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth=2)")
        response = client.get(f'/dggs-api/v1-pre/dggs/{dggrsid}/zones/{zone["zone_id"]}/data', params={'zone-depth': '2'})
        data = ZonesDataDggsJsonResponse(**response.json())
        assert response.status_code == 200
        for k, v in data.values.items():
            assert len(v) == 1
            assert v[0].depth == 2
            assert len(v[0].data) > 0
        assert response.status_code == 200

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth=1-2)")
        response = client.get(f'/dggs-api/v1-pre/dggs/{dggrsid}/zones/{zone["zone_id"]}/data', params={'zone-depth': '1-2'})
        data = ZonesDataDggsJsonResponse(**response.json())
        assert response.status_code == 200
        zone_depth_counts = [1, 2]
        for k, v in data.values.items():
            assert len(v) == 2
            for data in v:
                assert data.depth in zone_depth_counts
                assert len(data.data) > 0

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth=0-2)")
        response = client.get(f'/dggs-api/v1-pre/dggs/{dggrsid}/zones/{zone["zone_id"]}/data', params={'zone-depth': '0-2'})
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
        response = client.get(f'/dggs-api/v1-pre/dggs/{dggrsid}/zones/{zone["zone_id"]}/data', params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                              headers={'accept': 'application/geo+json'})
        data = ZonesDataGeoJson(**response.json())
        assert len(data.features) > 0
        assert response.status_code == 200

        print(f"Success test case with data-retrieval query ({dggrsid}, {zone['zone_id']}, zone-depth=0-2, geometry='zone-centroid', return=zarr+zip)")
        response = client.get(f'/dggs-api/v1-pre/dggs/{dggrsid}/zones/{zone["zone_id"]}/data',
                              params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                              headers={'accept': 'application/zarr+zip'})
        assert response.status_code == 200
        with open("data_zarr.zip", "wb") as f:
            f.write(response.content)
        z = zarr.open('data_zarr.zip')
        print(z.tree())

        iloc_pos = np.random.randint(0, len(df_dict['non_exist_zoneids']), 1)
        non_exists_zoneid = df_dict['non_exist_zoneids'][iloc_pos[0]]
        print(f"Empty test case with data-retrieval query ({dggrsid}, {non_exists_zoneid}, zone-depth=0-2, geometry='zone-centroid', return=geojson)")
        response = client.get(f'/dggs-api/v1-pre/dggs/{dggrsid}/zones/{non_exists_zoneid}/data',
                              params={'zone-depth': '0-2', 'geometry': 'zone-centroid'},
                              headers={'accept': 'application/geo+json'})
        assert response.status_code == 204


