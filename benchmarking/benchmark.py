import shapely
import requests
import math
import numpy as np
from locust import events
from locust import HttpUser, task, between, tag

global_bbox = None
zone_ids = []
zone_ids_coarser_rf = []


@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument("--zone-depth", type=int, env_var="zone_depth", default=2, help="The zone-depth parameter to use in zone data retrieval")
    parser.add_argument("--test-rf", type=int, env_var="zone_level", default=10, help="The zone level parameter to use in zone query / zone data retrieval")
    parser.add_argument("--test-size", type=int, env_var="test_size", default=20, help="Nnumber of zones in percentage to test in zone data retrieval")
    parser.add_argument("--test-dggrs", type=str, env_var="test_dggrs", default="igeo7", help="DGGRS ID")


@events.init.add_listener
# Create a union of bbox from each published collection for Benchmarking
def on_locust_init(environment, **kwargs):
    global global_bbox, zone_ids, zone_ids_coarser_rf
    test_rf = environment.parsed_options.test_rf
    zone_depth = environment.parsed_options.zone_depth
    test_dggrs = environment.parsed_options.test_dggrs
    collections = requests.get(f"{environment.host}/dggs-api/collections").json()
    collections = collections["collections"]
    for collection in collections:
        # only consider the first bbox.
        collection_id = collection["id"]
        collection_dggrs = requests.get(f"{environment.host}/dggs-api/collections/{collection_id}/dggs").json()
        collection_dggrs = collection_dggrs["dggrs"]
        for dggrs in collection_dggrs:
            if (dggrs["id"].lower() == test_dggrs):
                minx, miny, maxx, maxy = collection["extent"]["spatial"]["bbox"][0]
                aoi = shapely.box(minx, miny, maxx, maxy)
                if global_bbox is None:
                    global_bbox = shapely.box(minx, miny, maxx, maxy)
                else:
                    global_bbox = shapely.union(global_bbox, aoi).normalize()
    bounds = list(map(str, global_bbox.bounds))
    zone_ids_list = requests.get(f"{environment.host}/dggs-api/dggs/{test_dggrs}/zones", params={"bbox": ",".join(bounds),
                                                                                                 "zone-level": test_rf,
                                                                                                 "compact-zones": False}).json()
    zone_ids = zone_ids_list["zones"]
    zone_ids_list = requests.get(f"{environment.host}/dggs-api/dggs/{test_dggrs}/zones", params={"bbox": ",".join(bounds),
                                                                                                 "zone-level": test_rf - zone_depth,
                                                                                                 "compact-zones": False}).json()
    zone_ids_coarser_rf = zone_ids_list["zones"]
    print(len(zone_ids_coarser_rf))


class BenchmarkingZoneQuery(HttpUser):
    wait_time = between(1, 5)

    @tag("zone_query")
    @task
    def zone_query(self):
        global global_bbox
        test_rf = self.environment.parsed_options.test_rf
        test_dggrs = self.environment.parsed_options.test_dggrs
        bounds = list(map(str, global_bbox.bounds))
        self.client.get(f"/dggs-api/dggs/{test_dggrs}/zones", name=f"zone_query (rf={test_rf}, dggrs={test_dggrs})",
                        params={"bbox": ",".join(bounds),
                                "zone-level": test_rf,
                                "compact-zones": False})

    @tag("zone_query")
    @task
    def zones_query_geojson_return(self):
        global global_bbox
        test_rf = self.environment.parsed_options.test_rf
        test_dggrs = self.environment.parsed_options.test_dggrs
        bounds = list(map(str, global_bbox.bounds))
        self.client.get(f"/dggs-api/dggs/{test_dggrs}/zones", name=f"zones query geojson return (rf={test_rf}, dggrs={test_dggrs})",
                        headers={'Accept': 'Application/geo+json'},
                        params={"bbox": ",".join(bounds),
                                "zone-level": test_rf,
                                "compact-zones": False})

    @tag("zone_query")
    @task
    def zones_query_cql(self):
        global global_bbox
        test_rf = self.environment.parsed_options.test_rf
        test_dggrs = self.environment.parsed_options.test_dggrs
        bounds = list(map(str, global_bbox.bounds))
        self.client.get(f"/dggs-api/dggs/{test_dggrs}/zones", name=f"zone query CQL (rf={test_rf}, dggrs={test_dggrs})",
                        params={"bbox": ",".join(bounds),
                                "zone-level": test_rf,
                                "compact-zones": False,
                                "filter": "band_1 <= 2"})


class BenchmarkingZoneDataRetrieval(HttpUser):
    wait_time = between(1, 5)

    @tag("zone_data_retrieval")
    @task
    def zone_data_retrieval_single_zone(self):
        global zone_ids
        test_size_percentage = self.environment.parsed_options.test_size
        test_dggrs = self.environment.parsed_options.test_dggrs
        test_rf = self.environment.parsed_options.test_rf
        size = math.floor(len(zone_ids) * (test_size_percentage / 100))
        size = 1 if (size == 0) else size
        random_zones = np.random.choice(zone_ids, size=size, replace=False)
        for zone_id in random_zones:
            self.client.get(f"/dggs-api/dggs/{test_dggrs}/zones/{zone_id}/data", name=f"zone data retrieval - single zone (rf={test_rf}, dggrs={test_dggrs}, size={size})",
                            params={"zone-depth": 0})

    @tag("zone_data_retrieval")
    @task
    def zone_data_retrieval_single_zone_geojson(self):
        global zone_ids
        test_size_percentage = self.environment.parsed_options.test_size
        test_dggrs = self.environment.parsed_options.test_dggrs
        test_rf = self.environment.parsed_options.test_rf
        size = math.floor(len(zone_ids) * (test_size_percentage / 100))
        size = 1 if (size == 0) else size
        random_zones = np.random.choice(zone_ids, size=size, replace=False)
        for zone_id in random_zones:
            self.client.get(f"/dggs-api/dggs/{test_dggrs}/zones/{zone_id}/data", name=f"zone data retrieval - single zone (geojson, rf={test_rf}, dggrs={test_dggrs}, size={size})",
                            headers={'accept': 'application/geo+json'},
                            params={"zone-depth": 0})

    @tag("zone_data_retrieval")
    @task
    def zone_data_retrieval_zone_depth(self):
        global zone_ids_coarser_rf
        zone_depth = self.environment.parsed_options.zone_depth
        test_size_percentage = self.environment.parsed_options.test_size
        test_dggrs = self.environment.parsed_options.test_dggrs
        test_rf = self.environment.parsed_options.test_rf
        size = math.floor(len(zone_ids_coarser_rf) * (test_size_percentage / 100))
        size = 1 if (size == 0) else size
        random_zones = np.random.choice(zone_ids_coarser_rf, size=size, replace=False)
        for zone_id in random_zones:
            self.client.get(f"/dggs-api/dggs/{test_dggrs}/zones/{zone_id}/data", name=f"zone data retrieval zone-depth: {zone_depth} (rf={test_rf - zone_depth}, dggrs={test_dggrs}, size={size})",
                            params={"zone-depth": zone_depth})

    @tag("zone_data_retrieval")
    @task
    def zone_data_retrieval_zone_depth_geojson(self):
        global zone_ids_coarser_rf
        zone_depth = self.environment.parsed_options.zone_depth
        test_size_percentage = self.environment.parsed_options.test_size
        test_dggrs = self.environment.parsed_options.test_dggrs
        test_rf = self.environment.parsed_options.test_rf
        size = math.floor(len(zone_ids_coarser_rf) * (test_size_percentage / 100))
        size = 1 if (size == 0) else size
        random_zones = np.random.choice(zone_ids_coarser_rf, size=size, replace=False)
        for zone_id in random_zones:
            self.client.get(f"/dggs-api/dggs/{test_dggrs}/zones/{zone_id}/data", name=f"zone data retrieval - zone-depth: {zone_depth} (geojson, rf={test_rf - zone_depth}, dggrs={test_dggrs}, size={size})",
                            headers={'accept': 'application/geo+json'},
                            params={"zone-depth": zone_depth})

    @tag("zone_data_retrieval")
    @task
    def zone_data_retrieval_zone_depth_zarr(self):
        global zone_ids_coarser_rf
        zone_depth = self.environment.parsed_options.zone_depth
        test_size_percentage = self.environment.parsed_options.test_size
        test_dggrs = self.environment.parsed_options.test_dggrs
        test_rf = self.environment.parsed_options.test_rf
        size = math.floor(len(zone_ids_coarser_rf) * (test_size_percentage / 100))
        size = 1 if (size == 0) else size
        random_zones = np.random.choice(zone_ids_coarser_rf, size=size, replace=False)
        for zone_id in random_zones:
            self.client.get(f"/dggs-api/dggs/{test_dggrs}/zones/{zone_id}/data", name=f"zone data retrieval - zone-depth: {zone_depth} (zarr+zip, rf={test_rf - zone_depth} dggrs={test_dggrs}, size={size})",
                            headers={'accept': 'application/zarr+zip'},
                            params={"zone-depth": zone_depth})

    @tag("zone_data_retrieval")
    @task
    def zone_data_retrieval_zone_depth_cql(self):
        global zone_ids_coarser_rf, zone_depth
        zone_depth = self.environment.parsed_options.zone_depth
        test_size_percentage = self.environment.parsed_options.test_size
        test_dggrs = self.environment.parsed_options.test_dggrs
        test_rf = self.environment.parsed_options.test_rf
        size = math.floor(len(zone_ids_coarser_rf) * (test_size_percentage / 100))
        size = 1 if (size == 0) else size
        random_zones = np.random.choice(zone_ids_coarser_rf, size=size, replace=False)
        for zone_id in random_zones:
            self.client.get(f"/dggs-api/dggs/{test_dggrs}/zones/{zone_id}/data", name=f"zone data retrieval - zone-depth: {zone_depth} (CQL filter, rf={test_rf - zone_depth}, dggrs={test_dggrs}, size={size})",
                            params={"zone-depth": zone_depth,
                                    "filter": "band_1 <= 2"})
