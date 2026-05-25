from pydggsapi.schemas.api.collections import Collection
from pydggsapi.schemas.ogc_dggs.dggrs_zones import ZonesResponse, ZonesGeoJson
from pydggsapi.dependencies.collections_providers.parquet_collection_provider import ParquetCollectionProvider
from pydggsapi.dependencies.collections_providers.zarr_collection_provider import ZarrCollectionProvider
from fastapi.testclient import TestClient
import pytest
import importlib
from importlib import reload
import os
from dggrid4py import DGGRIDv8
from dggrid4py.igeo7 import get_z7hex_resolution, z7int_to_z7hex
# rom geopandas import GeoSeries
from tinydb import TinyDB
import tempfile
import shapely
import pandas as pd
import numpy as np
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

cql_syntax_error_list = ["""band1 > 1 and band1 < 3""",
                         """band1 > \"a\"""",
                         """band1 <> 3""",
                         """(band1 < 20 AND (band1 > 9""",
                         """band1 like 'ANY*'"""]

cql_list = ["""{var_name} > {value}""",
            """{var_name} <= {value}""",
            """{var_name} >= {value}"""]

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
    minx, miny, maxx, maxy = collection.extent.spatial.bbox[0]
    # create a smaller bbox
    #minx, miny = round(minx + 0.1, 3), round(miny + 0.05, 3)
    #maxx, maxy = round(maxx - 0.1, 3), round(maxy - 0.05, 3)
    aoi = shapely.box(minx, miny, maxx, maxy)
    datasource_id = collection.collection_provider.datasource_id
    max_rf = collection.collection_provider.max_refinement_level
    dggrsid = collection.collection_provider.dggrsId
    rf1 = max_rf - 3
    rf2 = max_rf - 1
    ds1, ds2 = None, None
    cp = collection_providers_dict[collection.collection_provider.providerId]
    if (isinstance(cp, ZarrCollectionProvider)):
        # It is a data tree
        dt = cp.datasources[datasource_id].filehandle
        zone_groups = cp.datasources[datasource_id].zone_groups
        ds1 = dt[zone_groups[str(rf1)]].to_dataset().to_dataframe()
        ds2 = dt[zone_groups[str(rf2)]].to_dataset().to_dataframe()
        ds1 = ds1.drop('spatial_ref', axis=1).reset_index()
        ds2 = ds2.drop('spatial_ref', axis=1).reset_index()
        test_rf = {rf1: [ds1], rf2: [ds2]}
    elif (isinstance(cp, ParquetCollectionProvider)):
        # duckdb connection
        parquetpath = cp.datasources[datasource_id].filepath
        ds1 = pd.read_parquet(parquetpath)
        if (ds1.index.name == 'zone_id'):
            ds1.reset_index(inplace=True)
        if (collection.collection_provider.dggrsId == 'igeo7'):
            ds1['rf'] = ds1['zone_id'].apply(lambda x: get_z7hex_resolution(z7int_to_z7hex(x)))
        else:
            mygrid = support_grids[collection.collection_provider.dggrsId]
            ds1['rf'] = ds1['zone_id'].apply(lambda x: mygrid.getZoneLevel(x))
        ds2 = ds1[ds1['rf'] == int(rf2)].drop('rf', axis=1)
        ds1 = ds1[ds1['rf'] == int(rf1)].drop('rf', axis=1)
        test_rf = {rf1: [ds1], rf2: [ds2]}

    if (dggrsid not in list(validation_df.keys())):
        validation_df[dggrsid] = {'aoi': shapely.box(minx, miny, maxx, maxy),
                                  'test_rf': test_rf
                                  }
    else:
        for rf in [rf1, rf2]:
            if (rf in list(validation_df[dggrsid]['test_rf'].keys())):
                validation_df[dggrsid]['test_rf'][rf] += test_rf[rf]
            else:
                validation_df[dggrsid]['test_rf'][rf] = test_rf[rf]


def test_cql_zone_query_dggrs_zones():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    for cql_error in cql_syntax_error_list:
        print(f"Fail test case for cql syntax error (igeo, bbox: {non_exist_aoi.bounds}, compact=False)")
        bounds = list(map(str, non_exist_aoi.bounds))
        response = client.get('/dggs-api/dggs/igeo7/zones', params={"bbox": ",".join(bounds), "zone-level": 7,
                                                                           "compact-zone": False,
                                                                           "filter": cql_error})
        assert response.status_code == 400

    for dggrsid, validation_set in validation_df.items():
        aoi = validation_set['aoi']
        bounds = list(map(str, aoi.bounds))
        test_rf = validation_set['test_rf']
        for rf, ds_list in test_rf.items():
            dataset = pd.concat(ds_list).drop_duplicates("zone_id").set_index('zone_id')
            column_names = dataset.columns
            iloc_pos = np.random.randint(0, dataset.shape[0], len(cql_list))
            test_values = dataset.iloc[iloc_pos].values
            for cql_string, tdata in zip(cql_list, test_values):
                if (">" in cql_string):
                    test_value = np.nanmin(tdata)
                    validation_data = dataset[dataset[column_names[0]] > test_value]
                elif (">=" in cql_string):
                    test_value = np.nanmin(tdata)
                    validation_data = dataset[dataset[column_names[0]] >= test_value]
                elif ("<=" in cql_string):
                    test_value = np.nanmax(tdata)
                    validation_data = dataset[dataset[column_names[0]] <= test_value]
                cql_string = cql_string.format(var_name=column_names[0], value=test_value)
                print(f"Success test case with dggs zones query ({dggrsid}, bbox: {aoi.bounds}, zone_level={rf}, \
                        compact=False, cql: {cql_string})")
                response = client.get(f'/dggs-api/dggs/{dggrsid}/zones', params={"bbox": ",".join(bounds),
                                                                                        "zone-level": rf,
                                                                                        "compact-zone": False,
                                                                                        "filter": cql_string})
                print(validation_data)
                if (validation_data.shape[0] > 0):
                    assert response.status_code == 200
                    zones = ZonesResponse(**response.json())
                    # because the zones return are mixed from different collections
                    # so checking against the number of zones return against a single collection is not correct
                    # assert len(zones.zones) == validation_data.shape[0]
                else:
                    assert response.status_code == 204
            iloc_pos = np.random.randint(0, dataset.shape[0], 2)
            test_values = dataset.iloc[iloc_pos].values
            for cql_string in cql_composition:
                cql_string = cql_string.format(var_name=column_names[0], value1=test_values[0][0], value2=test_values[1][0])
                print(f"Success test case with dggs zones query ({dggrsid}, bbox: {aoi.bounds}, zone_level={rf}, \
                        compact=False, cql: {cql_string})")
                response = client.get(f'/dggs-api/dggs/{dggrsid}/zones', params={"bbox": ",".join(bounds),
                                                                                        "zone-level": rf,
                                                                                        "compact-zone": False,
                                                                                        "filter": cql_string})
                if ("AND" in cql_string):
                    validation_data = dataset[(dataset[column_names[0]] >= test_values[0][0]) &
                                              (dataset[column_names[0]] <= test_values[1][0])]
                elif ("OR" in cql_string):
                    validation_data = dataset[(dataset[column_names[0]] == test_values[0][0]) |
                                              (dataset[column_names[0]] == test_values[1][0])]
                if (validation_data.shape[0] > 0):
                    assert response.status_code == 200
                    zones = ZonesResponse(**response.json())
                    # because the zones return are mixed from different collections
                    # so checking against the number of zones return against a single collection is not correct
                    # assert len(zones.zones) == validation_data.shape[0]


