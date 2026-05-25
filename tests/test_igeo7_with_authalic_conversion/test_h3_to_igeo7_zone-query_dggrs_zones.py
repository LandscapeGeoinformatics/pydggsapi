from pydggsapi.schemas.ogc_dggs.dggrs_zones import ZonesResponse, ZonesGeoJson
from pydggsapi.schemas.api.collections import Collection
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import h3
import os
import shapely
import json
from tinydb import TinyDB
import geopandas as gpd


db = TinyDB(os.environ.get('DGGS_API_CONFIG'))
collections = db.table('collections').all()
collections_dict = {}


def _cell_to_shapely(cellid, geometry):
    method = h3.cell_to_boundary if (geometry == 'zone-region') else h3.cell_to_latlng
    GEO = shapely.Polygon if (geometry == 'zone-region') else shapely.Point
    points = method(cellid)
    points = [points] if (geometry != 'zone-region') else points
    points = tuple(p[::-1] for p in points)
    return GEO(points)


for collection in collections:
    cid, collection_config = collection.popitem()
    if (collection_config['collection_provider']['dggrsId'] == 'igeo7'):
        collection_config['id'] = cid
        collections_dict[cid] = Collection(**collection_config)

validation_df = {}

for collection_name, collection in collections_dict.items():
    minx, miny, maxx, maxy = collection.extent.spatial.bbox[0]
    # create a smaller bbox
    minx, miny = round(minx + 0.1, 3), round(miny + 0.05, 3)
    maxx, maxy = round(maxx - 0.1, 3), round(maxy - 0.05, 3)
    aoi = shapely.box(minx, miny, maxx, maxy)
    zoneIds = h3.h3shape_to_cells_experimental(h3.geo_to_h3shape(aoi), 3, contain='overlap')
    geometry = [_cell_to_shapely(z, 'zone-region') for z in zoneIds]
    hex_df = gpd.GeoDataFrame({'zoneid': zoneIds}, geometry=geometry, crs='wgs84').set_index('zoneid')
    geometry = [_cell_to_shapely(z, 'zone-centorid') for z in zoneIds]
    centroid_df = gpd.GeoDataFrame({'zoneid': zoneIds}, geometry=geometry, crs='wgs84').set_index('zoneid')

    zoneIds = h3.h3shape_to_cells_experimental(h3.geo_to_h3shape(aoi), 6, contain='overlap')
    geometry = [_cell_to_shapely(z, 'zone-region') for z in zoneIds]
    hex_df2 = gpd.GeoDataFrame({'zoneid': zoneIds}, geometry=geometry, crs='wgs84').set_index('zoneid')
    geometry = [_cell_to_shapely(z, 'zone-centorid') for z in zoneIds]
    centroid_df2 = gpd.GeoDataFrame({'zoneid': zoneIds}, geometry=geometry, crs='wgs84').set_index('zoneid')
    validation_df[collection_name] = {3: {'hex': hex_df, 'centroid': centroid_df,
                                          'aoi': aoi},
                                      6: {'hex': hex_df2, 'centroid': centroid_df2,
                                          'aoi': aoi}
                                      }


def test_h3_to_igeo7_zone_query_dggrs_zones():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    for collection_name, df_dict in validation_df.items():

        for rf, validation_set in df_dict.items():
            aoi = validation_set['aoi']
            bounds = list(map(str, aoi.bounds))
            print(f"Success test case with dggs zones query (h3, bbox: {aoi.bounds}, zone_level={rf}, compact=False)")
            response = client.get('/dggs-api/dggs/h3/zones', params={"bbox": ",".join(bounds), 'zone-level': rf, 'compact-zone': False})
            zones = ZonesResponse(**response.json())
            return_zones_list = zones.zones
            return_zones_list.sort()
            validation_zones_list = validation_set['hex'].sort_index().index.tolist()
            assert len(return_zones_list) == len(validation_zones_list)
            assert all([validation_zones_list[i] == z for i, z in enumerate(return_zones_list)])
            assert response.status_code == 200

            print(f"Success test case with dggs zones query (h3, bbox: {aoi.bounds}, zone_level={rf}, compact=False, geojson)")
            response = client.get('/dggs-api/dggs/h3/zones', headers={'Accept': 'Application/geo+json'},
                                  params={"bbox": ",".join(bounds), 'zone-level': rf, 'compact-zone': False})
            zones_geojson = ZonesGeoJson(**response.json())
            return_features_list = zones_geojson.features
            geometry = [shapely.from_geojson(json.dumps(f.geometry.__dict__)) for f in return_features_list]
            zonesID = [f.properties['zoneId'] for f in return_features_list]
            return_gdf = gpd.GeoDataFrame({'zoneid': zonesID}, geometry=geometry, crs='wgs84').set_index('zoneid').sort_index()
            validation_hexagons_gdf = validation_set['hex'].sort_index()
            assert len(return_gdf) == len(validation_hexagons_gdf)
            assert all([shapely.equals(return_gdf.iloc[i]['geometry'], validation_hexagons_gdf.iloc[i]['geometry']) for i in range(len(return_gdf))])
            assert response.status_code == 200

