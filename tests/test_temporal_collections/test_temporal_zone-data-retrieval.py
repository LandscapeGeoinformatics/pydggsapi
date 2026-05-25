from pydggsapi.schemas.api.collections import Collection
from pydggsapi.schemas.ogc_dggs.dggrs_zones_data import ZonesDataDggsJsonResponse, ZonesDataGeoJson
from pydggsapi.dependencies.collections_providers.parquet_collection_provider import ParquetCollectionProvider
from pydggsapi.dependencies.collections_providers.zarr_collection_provider import ZarrCollectionProvider
from fastapi.testclient import TestClient
import pytest
import importlib
from importlib import reload
import os
from dggrid4py import DGGRIDv8
from dggrid4py.igeo7 import z7int_to_z7hex, z7hex_to_z7string
from dggrid4py.igeo7 import get_z7hex_resolution, z7int_to_z7hex
from tinydb import TinyDB
import tempfile
import shapely
import numpy as np
import pandas as pd
from dggal import Application, pydggal_setup, CRS, ogc, epsg, GeoExtent, Array, GeoPoint
from dggal import IVEA7H, ISEA7H_Z7, rHEALPix, HEALPix

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

non_exist_aoi = shapely.Polygon([[113.81837742963569, 22.521237932154797],
          [113.81837742963569, 22.13760392858767],
          [114.41438573041694, 22.13760392858767],
          [114.41438573041694, 22.521237932154797]])
aoi_3035 = [5204952.96287564, 3973761.18085118, 5324408.86305371, 4067507.93907037]

datetime_syntax_error_list = ["""2025/09/01""",
                              """2025-90-29""",
                              """2025/09/01-2025/09/03""",
                              """2025-09-01/.""",
                              """wqoejrqeotjewoit"""]

datetime_list = ["""2025-09-22/2025-09-26""",
                 """2025-09-23""",
                 """2025-09-24/..""",
                 """../2025-09-24"""]

cql_composition = ["""({var_name} >= {value1}) AND ({var_name} <= {value2})"""]


db = TinyDB(os.environ.get('DGGS_API_CONFIG'))
collections = db.table('collections').all()
collection_providers = db.table('collection_providers').all()
all_dggrs = db.table('dggrs').all()
collections_dict = {}
collection_providers_dict = {}
support_grids = {}
dggal_supported_grids_mapping = {'IVEA7H': IVEA7H,
                                 'RHEALPIX': rHEALPix,
                                 'ISEA7H_Z7': ISEA7H_Z7,
                                 'HEALPIX': HEALPix}

dggal_app = Application(appGlobals=globals())
pydggal_setup(dggal_app)
working = tempfile.mkdtemp()
dggrid = DGGRIDv8(os.environ['DGGRID_PATH'], working_dir=working, silent=True)

for dggrs in all_dggrs:
    dggrs_id, dggrs_config = dggrs.popitem()
    if ("dggal_dggrs_provider" in dggrs_config["classname"]):
        support_grids[dggrs_id] = dggal_supported_grids_mapping[dggrs_config['parameters']['grid']]()
    elif ("igeo7_dggrs_provider" in dggrs_config["classname"]):
        support_grids[dggrs_id] = dggrid


for collection in collections:
    cid, collection_config = collection.popitem()
    collection_config['id'] = cid
    collections_dict[cid] = Collection(**collection_config)

for cp in collection_providers:
    cpid, cp_config = cp.popitem()
    classname = cp_config["classname"]
    module, classname = classname.split('.') if (len(classname.split('.')) == 2) else (classname, classname)
    cls_ = getattr(importlib.import_module(f'pydggsapi.dependencies.collections_providers.{module}'), classname)
    collection_providers_dict[cpid] = cls_(cp_config["datasources"])


validation_df = {}

for collection_name, collection in collections_dict.items():
    datasource_id = collection.collection_provider.datasource_id
    max_rf = collection.collection_provider.max_refinement_level
    dggrsid = collection.collection_provider.dggrsId
    rf1 = max_rf - 3
    cp = collection_providers_dict[collection.collection_provider.providerId]
    temporal_collection = False if (collection.timestamp is None) else True
    temporal_collection = temporal_collection if (cp.datasources[datasource_id].datetime_col is None) else True
    if (not temporal_collection):
        continue
    if (isinstance(cp, ZarrCollectionProvider)):
        # It is a data tree
        dt = cp.datasources[datasource_id].filehandle
        zone_groups = cp.datasources[datasource_id].zone_groups
        ds1 = dt[zone_groups[str(rf1)]].to_dataset().to_dataframe()
        ds1 = ds1.drop('spatial_ref', axis=1)
    elif (isinstance(cp, ParquetCollectionProvider)):
        # duckdb connection
        parquetpath = cp.datasources[datasource_id].filepath
        # pandas doesn't support "**" glob search path
        ds1 = pd.read_parquet(parquetpath.split("**")[0]).reset_index()
        if (collection.collection_provider.dggrsId == 'igeo7'):
            ds1['rf'] = ds1['zone_id'].apply(lambda x: get_z7hex_resolution(z7int_to_z7hex(x)))
        else:
            mygrid = support_grids[collection.collection_provider.dggrsId]
            ds1['rf'] = ds1['zone_id'].apply(lambda x: mygrid.getZoneLevel(x))
        ds1 = ds1[ds1['rf'] == rf1]

    if (collection.collection_provider.dggrsId == 'igeo7'):
        ds1['textual_zone_id'] = ds1['zone_id'].apply(lambda x: z7hex_to_z7string(z7int_to_z7hex(x)))
        ds1 = ds1.drop('zone_id', axis=1)
    else:
        mygrid = support_grids[collection.collection_provider.dggrsId]
        ds1['textual_zone_id'] = ds1['zone_id'].apply(lambda x: mygrid.getZoneTextID(x))
        ds1 = ds1.drop('zone_id', axis=1)
    if (collection.timestamp is not None):
        ds1['time_stamp'] = pd.to_datetime(collection.timestamp)
    if (dggrsid not in list(validation_df.keys())):
        validation_df[dggrsid] = {'datasets': [ds1]}
    else:
        validation_df[dggrsid]['datasets'] += [ds1]


def test_temporal_zone_query_dggrs_zones():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    for dggrsid, validation_set in validation_df.items():
        dataset = pd.concat(validation_set['datasets'])
        iloc_pos = np.random.randint(0, dataset.shape[0], len(datetime_list))
        test_zoneid = dataset.iloc[iloc_pos]['textual_zone_id'].values
        column_names = [c for c in dataset.columns if (c != 'textual_zone_id')]
        for datetime_string, zid in zip(datetime_list, test_zoneid):
            tdata = dataset[dataset['textual_zone_id'] == zid]
            datetime_split = datetime_string.split('/')
            if (len(datetime_split) == 1):
                tdata = tdata[tdata['time_stamp'] == datetime_split[0]]
            else:
                if (datetime_split[0] == '..'):
                    tdata = tdata[tdata['time_stamp'] <= datetime_split[1]]
                elif (datetime_split[1] == '..'):
                    tdata = tdata[tdata['time_stamp'] >= datetime_split[0]]
                else:
                    tdata = tdata[(tdata['time_stamp'] >= datetime_split[0]) & (tdata['time_stamp'] <= datetime_split[1])]

            print(f"Datetime to test : {datetime_string}")
            print(f"test data : {tdata}")
            print(f"Success datetime test case: data-retrieval query ({dggrsid}, {zid}, zone-depth=0)")
            response = client.get(f'/dggs-api/dggs/{dggrsid}/zones/{zid}/data',
                                  params={'zone-depth': 0, 'datetime': datetime_string})
            if (tdata.shape[0] > 0):
                assert response.status_code == 200
                data = ZonesDataDggsJsonResponse(**response.json())
                total_length = 0
                for k, v in data.values.items():
                    assert len(v) == 1
                    assert v[0].depth == 0
                    non_null_data = [v for v in v[0].data if (v is not None)]
                    total_length += len(non_null_data)
                assert total_length == tdata.shape[0]
            else:
                assert response.status_code == 204

            print(f"Success datetime test case: data-retrieval query ({dggrsid}, {zid}, zone-depth=0, return = geojson)")
            response = client.get(f'/dggs-api/dggs/{dggrsid}/zones/{zid}/data', headers={'accept': 'application/geo+json'},
                                  params={'zone-depth': 0, 'datetime': datetime_string})
            if (tdata.shape[0] > 0):
                assert response.status_code == 200
                data = ZonesDataGeoJson(**response.json())
                feature = data.features
                assert len(feature) == tdata.shape[0]
            else:
                assert response.status_code == 204

