# webmercator zoom levels
# https://wiki.openstreetmap.org/wiki/Zoom_levels
import morecantile
from morecantile import Tile


class Mercator:

    def __init__(self):
        self.diff_deg_dict = {
            0.0: 1000.0,    # distance change at 0° latitude for 0.01° longitude difference
            30.0: 870.0,    # distance change at 30° latitude for 0.01° longitude difference
            60.0: 500.0,    # distance change at 60° latitude for 0.01° longitude difference
            87.5: 43.62     # distance change at 87.5° latitude for 0.01° longitude difference
        }

        self.zoom_info = {
            0: {"Tiles": 1, "Tile width deg lons": 360, "m per pixel": 156543},
            1: {"Tiles": 4, "Tile width deg lons": 180, "m per pixel": 78272},
            2: {"Tiles": 16, "Tile width deg lons": 90, "m per pixel": 39136},
            3: {"Tiles": 64, "Tile width deg lons": 45, "m per pixel": 19568},
            4: {"Tiles": 256, "Tile width deg lons": 22.5, "m per pixel": 9784},
            5: {"Tiles": 1024, "Tile width deg lons": 11.25, "m per pixel": 4892},
            6: {"Tiles": 4096, "Tile width deg lons": 5.625, "m per pixel": 2446},
            7: {"Tiles": 16384, "Tile width deg lons": 2.813, "m per pixel": 1223},
            8: {"Tiles": 65536, "Tile width deg lons": 1.406, "m per pixel": 611.496},
            9: {"Tiles": 262144, "Tile width deg lons": 0.703, "m per pixel": 305.748},
            10: {"Tiles": 1048576, "Tile width deg lons": 0.352, "m per pixel": 152.874},
            11: {"Tiles": 4194304, "Tile width deg lons": 0.176, "m per pixel": 76.437},
            12: {"Tiles": 16777216, "Tile width deg lons": 0.088, "m per pixel": 38.219},
            13: {"Tiles": 67108864, "Tile width deg lons": 0.044, "m per pixel": 19.109},
            14: {"Tiles": 268435456, "Tile width deg lons": 0.022, "m per pixel": 9.555},
            15: {"Tiles": 1073741824, "Tile width deg lons": 0.011, "m per pixel": 4.777},
            16: {"Tiles": 4294967296, "Tile width deg lons": 0.0055, "m per pixel": 2.389},
            17: {"Tiles": 17179869184, "Tile width deg lons": 0.00275, "m per pixel": 1.194},
            18: {"Tiles": 68719476736, "Tile width deg lons": 0.001375, "m per pixel": 0.597},
            19: {"Tiles": 274877906944, "Tile width deg lons": 0.0006875, "m per pixel": 0.299},
            20: {"Tiles": 1099511627776, "Tile width deg lons": 0.00034375, "m per pixel": 0.149},
            21: {"Tiles": 4398046511104, "Tile width deg lons": 0.000171661, "m per pixel": 0.07},
            22: {"Tiles": 17592186044416, "Tile width deg lons": 0.000085831, "m per pixel": 0.03},
        }

    def get(self, zoom):
        # zoom must be integer and between 0 and 20 inclusive
        if not isinstance(zoom, int):
            raise TypeError("zoom must be integer")
        if zoom < 0 or zoom > 22:
            raise ValueError("zoom must be between 0 and 22 inclusive")

        return self.zoom_info[zoom]

    # given a lt and tile width in long deg, calculate km across
    def get_tile_width_km(self, lt, tile_width_deg):
        # lt must be float and between 0 and 90 inclusive
        if not isinstance(lt, float):
            raise TypeError("lt must be float")
        if lt < 0 or lt > 90:
            raise ValueError("lt must be between 0 and 90 inclusive")

        # tile_width_deg must be float and between 0 and 360 inclusive
        if not isinstance(tile_width_deg, float):
            raise TypeError("tile_width_deg must be float")
        if tile_width_deg < 0 or tile_width_deg > 360:
            raise ValueError("tile_width_deg must be between 0 and 360 inclusive")

        # find the distortion given the latitude
        diff_deg = 1000.0

        for lt_bound, diff_deg_base in self.diff_deg_dict.items():
            if lt > lt_bound:
                diff_deg = diff_deg_base
                break

        # get the tile width in km
        # just havesine?
        tile_width_km = tile_width_deg * diff_deg

        return tile_width_km

    def getWGS84bbox(self, z, x, y):
        tms = morecantile.tms.get("WebMercatorQuad")
        tile = Tile(x, y, z)
        return tms.xy_bounds(tile), tile

