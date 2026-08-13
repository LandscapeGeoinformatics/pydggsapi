import shapely
import requests
import math
import numpy as np
from locust import events
from locust import HttpUser, SequentialTaskSet, between, tag, task

global_bbox = None
zone_ids = []
zone_ids_coarser_rf = []


@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument("--zone-depth", type=int, env_var="zone_depth", default=2, help="The zone-depth parameter to use in zone data retrieval")
    parser.add_argument("--test-collection", type=str, env_var="test_collection", default=None, help="The collection to benchmark")
    parser.add_argument("--test-bbox", type=float, nargs="+", env_var="test_bbox", default=None, help="The bbox to benchmark (minx, miny, maxx, maxy)")
    parser.add_argument("--test-rf", type=int, env_var="test_rf", default=10, help="The zone level parameter to use in zone query / zone data retrieval")
    parser.add_argument("--test-size", type=int, env_var="test_size", default=20, help="Nnumber of zones in percentage to test in zone data retrieval")
    parser.add_argument("--test-dggrs", type=str, env_var="test_dggrs", default="igeo7", help="DGGRS ID")
    parser.add_argument("--test-cql", type=str, env_var="test_cql", default=None, help="The CQL uses in zone data retrieval (with zone-depth)")


@events.init.add_listener
# Create a union of bbox from each published collection for Benchmarking
def on_locust_init(environment, **kwargs):
    global global_bbox, zone_ids, zone_ids_coarser_rf
    test_rf = environment.parsed_options.test_rf
    test_collection = environment.parsed_options.test_collection
    test_bbox = environment.parsed_options.test_bbox
    zone_depth = environment.parsed_options.zone_depth
    test_dggrs = environment.parsed_options.test_dggrs
    collections = requests.get(f"{environment.host}/dggs-api/collections").json()
    collections = collections["collections"]
    if (test_bbox is None):
        for collection in collections:
            # only consider the first bbox.
            if (test_collection is None):
                collection_id = collection["id"]
                collection_dggrs = requests.get(f"{environment.host}/dggs-api/collections/{collection_id}/dggs").json()
                collection_dggrs = collection_dggrs["dggrs"]
                for dggrs in collection_dggrs:
                    if (dggrs["id"].lower() == test_dggrs):
                        print(f"add collection {collection_id} spatial extent")
                        minx, miny, maxx, maxy = collection["extent"]["spatial"]["bbox"][0]
                        aoi = shapely.box(minx, miny, maxx, maxy)
                        if global_bbox is None:
                            global_bbox = shapely.box(minx, miny, maxx, maxy)
                        else:
                            global_bbox = shapely.union(global_bbox, aoi).normalize()
            elif (test_collection == collection["id"]):
                collection_dggrs = requests.get(f"{environment.host}/dggs-api/collections/{test_collection}/dggs").json()
                collection_dggrs = collection_dggrs["dggrs"]
                for dggrs in collection_dggrs:
                    if (dggrs["id"].lower() == test_dggrs):
                        print(f"add collection {test_collection} spatial extent")
                        minx, miny, maxx, maxy = collection["extent"]["spatial"]["bbox"][0]
                        aoi = shapely.box(minx, miny, maxx, maxy)
                        global_bbox = shapely.box(minx, miny, maxx, maxy)
    else:
        global_bbox = shapely.box(*test_bbox)
    if (global_bbox is None):
        raise ValueError("global_bbox is None")
    if isinstance(global_bbox, shapely.geometry.MultiPolygon):
        global_bbox = global_bbox.geoms[0]
    bounds = list(map(str, global_bbox.bounds))
    print(f"global_bbox bounds : {bounds}")
    zone_query_url = f"{environment.host}/dggs-api/dggs/{test_dggrs}/zones"
    if (test_collection is not None):
        zone_query_url = f"{environment.host}/dggs-api/collections/{test_collection}/dggs/{test_dggrs}/zones"
    user_classes = [c.__name__ for c in environment.user_classes]
    if ("BenchmarkingZoneDataRetrieval" in user_classes):
        zone_ids_list = requests.get(zone_query_url, params={"bbox": ",".join(bounds), "zone-level": test_rf,
                                                             "compact-zones": False, "limit": 10000000}).json()
        zone_ids = zone_ids_list["zones"]
        print(len(zone_ids))
        zone_ids_list = requests.get(zone_query_url, params={"bbox": ",".join(bounds), "zone-level": test_rf - zone_depth,
                                                             "compact-zones": False, "limit": 10000000}).json()
        zone_ids_coarser_rf = zone_ids_list["zones"]
        print(len(zone_ids_coarser_rf))


class BenchmarkingZoneQuery(HttpUser):
    wait_time = between(1, 5)

    @tag("case_1_2")
    @task
    def zone_query(self):
        global global_bbox
        test_rf = self.environment.parsed_options.test_rf
        test_dggrs = self.environment.parsed_options.test_dggrs
        test_collection = self.environment.parsed_options.test_collection
        bounds = list(map(str, global_bbox.bounds))
        zone_query_url = f"/dggs-api/dggs/{test_dggrs}/zones"
        if (test_collection is not None):
            zone_query_url = f"/dggs-api/collections/{test_collection}/dggs/{test_dggrs}/zones"
        self.client.get(zone_query_url, name=f"zone_query (rf={test_rf}, dggrs={test_dggrs})",
                        params={"bbox": ",".join(bounds),
                                "zone-level": test_rf,
                                "compact-zones": False,
                                "limit": 10000000})

    @tag("case_3")
    @task
    def zones_query_cql(self):
        global global_bbox
        test_rf = self.environment.parsed_options.test_rf
        test_dggrs = self.environment.parsed_options.test_dggrs
        test_collection = self.environment.parsed_options.test_collection
        test_cql = self.environment.parsed_options.test_cql
        bounds = list(map(str, global_bbox.bounds))
        zone_query_url = f"/dggs-api/dggs/{test_dggrs}/zones"
        params = {"bbox": ",".join(bounds),
                  "zone-level": test_rf,
                  "compact-zones": False,
                  "limit": 10000000}
        if (test_cql is not None):
            params.update({"filter": test_cql})
        if (test_collection is not None):
            zone_query_url = f"/dggs-api/collections/{test_collection}/dggs/{test_dggrs}/zones"
        self.client.get(zone_query_url, name=f"zone query CQL (rf={test_rf}, dggrs={test_dggrs})",
                        params=params)


class BenchmarkingZoneDataRetrieval(HttpUser):
    wait_time = between(1, 5)

    @tag("case_1")
    @task
    def zone_data_retrieval_single_zone(self):
        global zone_ids
        test_size_percentage = self.environment.parsed_options.test_size
        test_dggrs = self.environment.parsed_options.test_dggrs
        test_rf = self.environment.parsed_options.test_rf
        test_collection = self.environment.parsed_options.test_collection
        size = math.floor(len(zone_ids) * (test_size_percentage / 100))
        size = 1 if (size == 0) else size
        random_zones = np.random.choice(zone_ids, size=size, replace=False)
        for zone_id in random_zones:
            zone_data_retrieval_url = f"/dggs-api/dggs/{test_dggrs}/zones/{zone_id}/data"
            if (test_collection is not None):
                zone_data_retrieval_url = f"/dggs-api/collections/{test_collection}/dggs/{test_dggrs}/zones/{zone_id}/data"
            self.client.get(zone_data_retrieval_url, name=f"zone data retrieval (rf={test_rf}, dggrs={test_dggrs}, size={size})",
                            params={"zone-depth": 0})

    @tag("case_2")
    @task
    def zone_data_retrieval_zone_depth(self):
        global zone_ids_coarser_rf
        zone_depth = self.environment.parsed_options.zone_depth
        test_size_percentage = self.environment.parsed_options.test_size
        test_dggrs = self.environment.parsed_options.test_dggrs
        test_rf = self.environment.parsed_options.test_rf
        test_collection = self.environment.parsed_options.test_collection
        size = math.floor(len(zone_ids) * (test_size_percentage / 100))
        size = math.floor(len(zone_ids_coarser_rf) * (test_size_percentage / 100))
        size = 1 if (size == 0) else size
        random_zones = np.random.choice(zone_ids_coarser_rf, size=size, replace=False)
        for zone_id in random_zones:
            zone_data_retrieval_url = f"/dggs-api/dggs/{test_dggrs}/zones/{zone_id}/data"
            if (test_collection is not None):
                zone_data_retrieval_url = f"/dggs-api/collections/{test_collection}/dggs/{test_dggrs}/zones/{zone_id}/data"
            self.client.get(zone_data_retrieval_url, name=f"zone data retrieval (zone-depth={zone_depth}, rf={test_rf - zone_depth}, dggrs={test_dggrs}, size={size})",
                            params={"zone-depth": zone_depth})

    @tag("case_2")
    @task
    def zone_data_retrieval_zone_depth_geojson(self):
        global zone_ids_coarser_rf
        zone_depth = self.environment.parsed_options.zone_depth
        test_size_percentage = self.environment.parsed_options.test_size
        test_dggrs = self.environment.parsed_options.test_dggrs
        test_rf = self.environment.parsed_options.test_rf
        test_collection = self.environment.parsed_options.test_collection
        size = math.floor(len(zone_ids_coarser_rf) * (test_size_percentage / 100))
        size = 1 if (size == 0) else size
        random_zones = np.random.choice(zone_ids_coarser_rf, size=size, replace=False)
        for zone_id in random_zones:
            zone_data_retrieval_url = f"/dggs-api/dggs/{test_dggrs}/zones/{zone_id}/data"
            if (test_collection is not None):
                zone_data_retrieval_url = f"/dggs-api/collections/{test_collection}/dggs/{test_dggrs}/zones/{zone_id}/data"
            self.client.get(zone_data_retrieval_url, name=f"zone data retrieval (geojson, zone-depth={zone_depth}, rf={test_rf - zone_depth}, dggrs={test_dggrs}, size={size})",
                            headers={'accept': 'application/geo+json'},
                            params={"zone-depth": zone_depth})

    @tag("case_2")
    @task
    def zone_data_retrieval_zone_depth_zarr(self):
        global zone_ids_coarser_rf
        zone_depth = self.environment.parsed_options.zone_depth
        test_size_percentage = self.environment.parsed_options.test_size
        test_dggrs = self.environment.parsed_options.test_dggrs
        test_rf = self.environment.parsed_options.test_rf
        test_collection = self.environment.parsed_options.test_collection
        size = math.floor(len(zone_ids_coarser_rf) * (test_size_percentage / 100))
        size = math.floor(len(zone_ids_coarser_rf) * (test_size_percentage / 100))
        size = 1 if (size == 0) else size
        random_zones = np.random.choice(zone_ids_coarser_rf, size=size, replace=False)
        for zone_id in random_zones:
            zone_data_retrieval_url = f"/dggs-api/dggs/{test_dggrs}/zones/{zone_id}/data"
            if (test_collection is not None):
                zone_data_retrieval_url = f"/dggs-api/collections/{test_collection}/dggs/{test_dggrs}/zones/{zone_id}/data"
            self.client.get(zone_data_retrieval_url, name=f"zone data retrieval (zarr+zip, zone-depth={zone_depth}, rf={test_rf - zone_depth} dggrs={test_dggrs}, size={size})",
                            headers={'accept': 'application/zarr+zip'},
                            params={"zone-depth": zone_depth})

    @tag("case_3")
    @task
    def zone_data_retrieval_zone_depth_cql(self):
        global zone_ids_coarser_rf, zone_depth
        zone_depth = self.environment.parsed_options.zone_depth
        test_size_percentage = self.environment.parsed_options.test_size
        test_dggrs = self.environment.parsed_options.test_dggrs
        test_rf = self.environment.parsed_options.test_rf
        test_collection = self.environment.parsed_options.test_collection
        test_cql = self.environment.parsed_options.test_cql
        size = math.floor(len(zone_ids_coarser_rf) * (test_size_percentage / 100))
        size = 1 if (size == 0) else size
        random_zones = np.random.choice(zone_ids_coarser_rf, size=size, replace=False)
        params = {"zone-depth": zone_depth}
        if (test_cql is not None):
            params.update({"filter": test_cql})
        for zone_id in random_zones:
            zone_data_retrieval_url = f"/dggs-api/dggs/{test_dggrs}/zones/{zone_id}/data"
            if (test_collection is not None):
                zone_data_retrieval_url = f"/dggs-api/collections/{test_collection}/dggs/{test_dggrs}/zones/{zone_id}/data"
            self.client.get(zone_data_retrieval_url, name=f"zone data retrieval (CQL filter, zone-depth={zone_depth}, rf={test_rf - zone_depth}, dggrs={test_dggrs}, size={size})",
                            params=params)


