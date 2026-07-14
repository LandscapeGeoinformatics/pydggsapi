import os
import shapely
from tinydb import TinyDB
from locust import events
from pydggsapi.schemas.api.collections import Collection
from locust import HttpUser, task, between

global_bbox = None
global_max_rf = -1
global_min_rf = -1


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    global global_bbox, global_max_rf, global_min_rf
    db = TinyDB(os.environ.get('DGGS_API_CONFIG'))
    collections = db.table('collections').all()
    for collection in collections:
        cid, collection_config = collection.popitem()
        if (collection_config['collection_provider']['dggrsId'] == 'igeo7'):
            collection_config['id'] = cid
            collection = Collection(**collection_config)
            minx, miny, maxx, maxy = collection.extent.spatial.bbox[0]
            aoi = shapely.box(minx, miny, maxx, maxy)
            if global_bbox is None:
                global_bbox = shapely.box(minx, miny, maxx, maxy)
            else:
                global_bbox = shapely.union(global_bbox, aoi).normalize()
            max_rf = collection.collection_provider.max_refinement_level
            min_rf = collection.collection_provider.min_refinement_level
            global_max_rf = max_rf if (global_max_rf < max_rf) else global_max_rf
            global_min_rf = min_rf if (global_min_rf < min_rf) else global_min_rf


class BenchmarkingIGEO7_ZarrProvider(HttpUser):
    wait_time = between(1, 5)
    global global_bbox, max_rf

    @task
    def zones_query_max_refinement_level(self):
        bounds = list(map(str, global_bbox.bounds))
        print(f"Benchmarking IGEO7 Zarr Provider Zones query(bound: {global_bbox.bounds}, zone_level={global_max_rf}, compact=False)")
        self.client.get("/dggs-api/dggs/igeo7/zones", params={"bbox": ",".join(bounds),
                                                              "zone-level": global_max_rf,
                                                              "compact-zones": False})



