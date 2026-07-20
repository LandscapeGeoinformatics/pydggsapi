import shapely
import requests
import numpy as np
from locust import events
from locust import HttpUser, task, between, tag

global_bbox = None
test_rf = 10
zone_depth = 2
zone_ids = []
zone_ids_coarser_rf = []


@events.init.add_listener
# Create a union of bbox from each published collection for Benchmarking
def on_locust_init(environment, **kwargs):
    global global_bbox, test_rf, zone_ids, zone_ids_coarser_rf
    collections = requests.get(f"{environment.host}/dggs-api/collections").json()
    collections = collections["collections"]
    for collection in collections:
        # only consider the first bbox.
        minx, miny, maxx, maxy = collection["extent"]["spatial"]["bbox"][0]
        aoi = shapely.box(minx, miny, maxx, maxy)
        if global_bbox is None:
            global_bbox = shapely.box(minx, miny, maxx, maxy)
        else:
            global_bbox = shapely.union(global_bbox, aoi).normalize()
    bounds = list(map(str, global_bbox.bounds))
    zone_ids_list = requests.get(f"{environment.host}/dggs-api/dggs/igeo7/zones", params={"bbox": ",".join(bounds),
                                                                                          "zone-level": test_rf,
                                                                                          "compact-zones": False}).json()
    zone_ids = zone_ids_list["zones"]
    zone_ids_list = requests.get(f"{environment.host}/dggs-api/dggs/igeo7/zones", params={"bbox": ",".join(bounds),
                                                                                          "zone-level": test_rf - zone_depth,
                                                                                          "compact-zones": False}).json()
    zone_ids_coarser_rf = zone_ids_list["zones"]
    print(len(zone_ids_coarser_rf))



class BenchmarkingIGEO7_ZarrProvider(HttpUser):
    wait_time = between(1, 5)

    @tag("zone_query")
    @task
    def zone_query(self):
        global global_bbox, test_rf
        bounds = list(map(str, global_bbox.bounds))
        self.client.get("/dggs-api/dggs/igeo7/zones", name="zone_query", params={"bbox": ",".join(bounds),
                                                                                 "zone-level": test_rf,
                                                                                 "compact-zones": False})

    @tag("zone_query")
    @task
    def zones_query_geojson_return(self):
        global global_bbox, test_rf
        bounds = list(map(str, global_bbox.bounds))
        self.client.get("/dggs-api/dggs/igeo7/zones", name="zones_query_geojson_return", headers={'Accept': 'Application/geo+json'},
                        params={"bbox": ",".join(bounds),
                                "zone-level": test_rf,
                                "compact-zones": False})

    @tag("zone_query")
    @task
    def zones_query_cql(self):
        global global_bbox, test_rf
        bounds = list(map(str, global_bbox.bounds))
        self.client.get("/dggs-api/dggs/igeo7/zones", name="zone_query_cql",
                        params={"bbox": ",".join(bounds),
                                "zone-level": test_rf,
                                "compact-zones": False,
                                "filter": "band_1 <= 2"})

    @tag("zone_data_retrieval")
    @task
    def zone_data_retrieval_single_zone(self):
        global zone_ids
        random_zones = np.random.choice(zone_ids, size=1000, replace=False)
        for zone_id in random_zones:
            self.client.get(f"/dggs-api/dggs/igeo7/zones/{zone_id}/data", name="zone data retrieval - single zone",
                            params={"zone-depth": 0})

    @tag("zone_data_retrieval")
    @task
    def zone_data_retrieval_single_zone_geojson(self):
        global zone_ids
        random_zones = np.random.choice(zone_ids, size=1000, replace=False)
        for zone_id in random_zones:
            self.client.get(f"/dggs-api/dggs/igeo7/zones/{zone_id}/data", name="zone data retrieval - single zone (geojson)",
                            headers={'accept': 'application/geo+json'},
                            params={"zone-depth": 0})

    @tag("zone_data_retrieval")
    @task
    def zone_data_retrieval_zone_depth(self):
        global zone_ids_coarser_rf, zone_depth
        random_zones = np.random.choice(zone_ids_coarser_rf, size=1000)
        for zone_id in random_zones:
            self.client.get(f"/dggs-api/dggs/igeo7/zones/{zone_id}/data", name=f"zone data retrieval - zone-depth: {zone_depth}",
                            params={"zone-depth": zone_depth})

    @tag("zone_data_retrieval")
    @task
    def zone_data_retrieval_zone_depth_geojson(self):
        global zone_ids_coarser_rf, zone_depth
        random_zones = np.random.choice(zone_ids_coarser_rf, size=1000)
        for zone_id in random_zones:
            self.client.get(f"/dggs-api/dggs/igeo7/zones/{zone_id}/data", name=f"zone data retrieval - zone-depth: {zone_depth} (geojson)",
                            headers={'accept': 'application/geo+json'},
                            params={"zone-depth": zone_depth})

    @tag("zone_data_retrieval")
    @task
    def zone_data_retrieval_zone_depth_zarr(self):
        global zone_ids_coarser_rf, zone_depth
        random_zones = np.random.choice(zone_ids_coarser_rf, size=1000)
        for zone_id in random_zones:
            self.client.get(f"/dggs-api/dggs/igeo7/zones/{zone_id}/data", name=f"zone data retrieval - zone-depth: {zone_depth} (zarr+zip)",
                            headers={'accept': 'application/zarr+zip'},
                            params={"zone-depth": zone_depth})

    @tag("zone_data_retrieval")
    @task
    def zone_data_retrieval_zone_depth_cql(self):
        global zone_ids_coarser_rf, zone_depth
        random_zones = np.random.choice(zone_ids_coarser_rf, size=1000)
        for zone_id in random_zones:
            self.client.get(f"/dggs-api/dggs/igeo7/zones/{zone_id}/data", name=f"zone data retrieval - zone-depth: {zone_depth} (CQL filter)",
                            params={"zone-depth": zone_depth,
                                    "filter": "band_1 <= 2"})

