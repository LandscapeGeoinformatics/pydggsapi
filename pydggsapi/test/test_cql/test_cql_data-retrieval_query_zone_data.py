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

cql_list = ["""{var_name} > {value}""",
            """{var_name} <= {value}""",
            """{var_name} >= {value}"""]

cql_composition = ["""({var_name} >= {value1}) AND ({var_name} <= {value2})"""]


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
            """{var_name} < {value}""",
            """{var_name} <= {value}""",
            """{var_name} >= {value}"""]

cql_composition = ["""({var_name} >= {value1}) AND ({var_name} <= {value2})"""]


db = TinyDB(os.environ.get('dggs_api_config'))
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
    aoi = shapely.box(minx, miny, maxx, maxy)
    datasource_id = collection.collection_provider.datasource_id
    max_rf = collection.collection_provider.max_refinement_level
    dggrsid = collection.collection_provider.dggrsId
    rf1 = str(max_rf - 3)
    cp = collection_providers_dict[collection.collection_provider.providerId]

    if (isinstance(cp, ZarrCollectionProvider)):
        # It is a data tree
        dt = cp.datasources[datasource_id].filehandle
        zone_groups = cp.datasources[datasource_id].zone_groups
        ds1 = dt[zone_groups[rf1]].to_dataset().to_dataframe().reset_index()
        ds1 = ds1.drop('spatial_ref', axis=1)
    elif (isinstance(cp, ParquetCollectionProvider)):
        parquetpath = cp.datasources[datasource_id].filepath
        ds1 = pd.read_parquet(parquetpath)
        if (ds1.index.name == 'zone_id'):
            ds1.reset_index(inplace=True)

    if (collection.collection_provider.dggrsId == 'igeo7'):
        ds1['textual_zone_id'] = ds1['zone_id'].apply(lambda x: z7hex_to_z7string(z7int_to_z7hex(x)))
        ds1 = ds1.set_index('textual_zone_id').drop('zone_id', axis=1)
    else:
        mygrid = support_grids[collection.collection_provider.dggrsId]
        ds1['textual_zone_id'] = ds1['zone_id'].apply(lambda x: mygrid.getZoneTextID(x))
        ds1 = ds1.set_index('textual_zone_id').drop('zone_id', axis=1)

    if (dggrsid not in list(validation_df.keys())):
        validation_df[dggrsid] = {'datasets': [ds1]}
    else:
        validation_df[dggrsid]['datasets'] += [ds1]


def test_cql_data_retrieval():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    for dggrsid, validation_sets in validation_df.items():
        datasets = validation_sets['datasets']
        iloc_pos = np.random.randint(0, datasets[0].shape[0], len(cql_list))
        test_zoneid = datasets[0].iloc[iloc_pos].index.values
        column_names = datasets[0].columns
        test_data = []
        for ds in datasets:
            t = ds.loc[test_zoneid]
            t = t.loc[~t.index.duplicated(keep='first'), :]
            test_data.append(t)
        test_data = pd.concat(test_data).reset_index()
        for cql_string, zid in zip(cql_list, test_zoneid):
            tdata = test_data[test_data['textual_zone_id'] == zid]
            if ("<" in cql_string):
                value = max(tdata[column_names[0]].values)
                if ("=" in cql_string):
                    tdata = tdata[tdata[column_names[0]] <= value]
                else:
                    tdata = tdata[tdata[column_names[0]] < value]
            elif (">" in cql_string):
                value = min(tdata[column_names[0]].values)
                if ("=" in cql_string):
                    tdata = tdata[tdata[column_names[0]] >= value]
                else:
                    tdata = tdata[tdata[column_names[0]] > value]

            cql_string = cql_string.format(var_name=column_names[0], value=value)
            print(f"CQL to test : {cql_string}")
            print(f"test data : {tdata}")
            print(f"Success CQL test case: data-retrieval query ({dggrsid}, {zid}, zone-depth=0)")
            response = client.get(f'/dggs-api/v1-pre/dggs/{dggrsid}/zones/{zid}/data',
                                  params={'zone-depth': 0, 'filter': cql_string})
            if (tdata.shape[0] > 0):
                assert response.status_code == 200
                data = ZonesDataDggsJsonResponse(**response.json())
                total_length = 0
                for k, v in data.values.items():
                    assert len(v) == 1
                    assert v[0].depth == 0
                    total_length += len(v[0].data)
                assert total_length == tdata.shape[0]
            else:
                assert response.status_code == 204

            print(f"Success CQL test case: data-retrieval query ({dggrsid}, {zid}, zone-depth=0, return = geojson)")
            response = client.get(f'/dggs-api/v1-pre/dggs/{dggrsid}/zones/{zid}/data', headers={'accept': 'application/geo+json'},
                                  params={'zone-depth': 0, 'filter': cql_string})
            if (tdata.shape[0] > 0):
                assert response.status_code == 200
                data = ZonesDataGeoJson(**response.json())
                # only 1 feature shall return at zone-depth 0
                feature = data.features[0]
                feature.properties.pop("zoneId")
                feature.properties.pop("depth")
                assert len(feature.properties.values()) == tdata.shape[0]
            else:
                assert response.status_code == 204

