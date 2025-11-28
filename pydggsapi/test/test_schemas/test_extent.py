import pytest

from pydggsapi.schemas.ogc_collections.extent import Extent, SpatialExtent, TemporalExtent


@pytest.mark.parametrize(
    "bbox",
    [
        [[-180.0, -90.0, 180.0, 90.0]],
        [[-180, -90.0, 0, 0], [0, 0, 180, 90.0]],
    ],
)
def test_spatial_bbox(bbox):
    spatial = SpatialExtent(bbox=bbox)
    assert spatial.bbox == bbox


@pytest.mark.parametrize(
    "bbox",
    [
        [[-180.0]],
        [[-180.0, -90.0]],
        [[-180.0, -90.0, 180.0]],
        [[-180.0, -90.0, 180.0, -180.0, 0]],
        [[-180.0, -90.0, 180.0, -180.0, 0, 100, 200]],
        [
            [-180.0, -90.0, 180.0, -180.0, 0, 100],  # OK
            [-180.0, -90.0, 180.0, -180.0, 0],  # invalid
        ],
    ],
)
def test_spatial_bbox_sizes(bbox):
    with pytest.raises(ValueError):
        SpatialExtent(bbox=bbox)


@pytest.mark.parametrize(
    "interval",
    [
        ["2025"],
        ["2024-01-01", "2024-12-31", "2025-01-01"],
    ],
)
def test_temporal_interval_sizes(interval):
    with pytest.raises(ValueError):
        TemporalExtent(interval=[interval])


@pytest.mark.parametrize(
    ["extent", "expect"],
    [
        (
            {"spatial": {"bbox": [[-180.0, -90.0, 180.0, 90.0]]}},
            {
                "spatial": {
                    "bbox": [[-180.0, -90.0, 180.0, 90.0]],
                    "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"  # inserted by default
                },
            },
        ),
        (
            {
                "spatial": {"bbox": [[-180.0, -90.0, 180.0, 90.0]]},
                "temporal": {"interval": [["2024-01-01", "2024-12-31"]]},
            },
            {
                "spatial": {
                    "bbox": [[-180.0, -90.0, 180.0, 90.0]],
                    "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"  # inserted by default
                },
                "temporal": {
                    "interval": [["2024-01-01", "2024-12-31"]],
                    "trs": "http://www.opengis.net/def/uom/ISO-8601/0/Gregorian"  # inserted by default},
                }
            },
        ),
        (
            {
                "spatial": {"bbox": [[-180.0, -90.0, 180.0, 90.0]]},
                "temporal": {"interval": [["2024-01-01", "2024-12-31"]]},
                "year": {
                    "interval": [[1950, 2000], [2050, 2100]],
                    "trs": "year-temporal-uri",
                },
                "pressure": {
                    "interval": [[10, 50]],
                    "definition": "pressure",
                    "unit": "hPa",
                    "grid": {
                        "firstCoordinate": 10,
                        "cellsCount": 5,
                        "resolution": 10,
                    }
                },
                "elevation": {
                    "vrs": "some-elevation-reference-system",
                    "interval": [[0, 200]],
                    "unit": "m",
                    "variableType": "continuous",
                }
            },
            {
                "spatial": {
                    "bbox": [[-180.0, -90.0, 180.0, 90.0]],
                    "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"  # inserted by default
                },
                "temporal": {
                    "interval": [["2024-01-01", "2024-12-31"]],
                    "trs": "http://www.opengis.net/def/uom/ISO-8601/0/Gregorian"  # inserted by default},
                },
                "year": {
                    "interval": [[1950, 2000], [2050, 2100]],
                    "trs": "year-temporal-uri",
                },
                "pressure": {
                    "interval": [[10, 50]],
                    "definition": "pressure",
                    "unit": "hPa",
                    "unitLang": "UCUM",  # inserted by default
                    "grid": {
                        "firstCoordinate": 10,
                        "cellsCount": 5,
                        "resolution": 10,
                    }
                },
                "elevation": {
                    "vrs": "some-elevation-reference-system",
                    "interval": [[0, 200]],
                    "unit": "m",
                    "unitLang": "UCUM",  # inserted by default
                    "variableType": "continuous",
                }
            }
        ),
    ]
)
def test_extent(extent, expect):
    """
    Test various extent combinations expected to be valid.

    Notably, test the edge cases with additional dimensions where specific combinations are expected
    (see https://github.com/opengeospatial/ogcapi-common/issues/368).
    """
    result = Extent(**extent)
    assert result.model_dump() == expect


def test_extent_additional_no_interval_invalid():
    extent = {
        "elevation": {
            "vrs": "some-elevation-reference-system",
            # "interval": [[0, 200]],  # omitted on purpose
            "unit": "m",
            "variableType": "continuous",
        }
    }
    with pytest.raises(ValueError):
        Extent(**extent)
