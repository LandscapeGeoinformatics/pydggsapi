Appendix 
========

Environment variables used by pydggsapi
---------------------------------------

Mandatory
~~~~~~~~~

============================== =========================================== ===============================
Environment variable name      Defautl value                               Description
============================== =========================================== ===============================
DGGS_API_CONFIG                No default, mandatory                       Path to pydggsapi configration
============================== =========================================== ===============================

Optional
~~~~~~~~~
============================== =========================================== ===============================
Environment variable name      Defautl value                               Description
============================== =========================================== ===============================
WORKERS                        4                                           Uvicorn number of workers
BIND                           0.0.0.0:8000                                Uvicorn binding address
DGGS_PREFIX                    /dggs-api                                   pydggsapi url prefix
TILES_PREFIX                   /tiles-api                                  pydggsapi MVT tiles url prefix
API_TITLE                      University of Tartu, OGC DGGS API v1-pre    FastAPI title
API_DESCRIPTION                OGC DGGS API                                FastAPI description
ROOT_PATH                      None                                        FastAPI root_path
OPENAPI_URL                    /openapi.json                               FastAPI openapi path
DOCS_URL                       /docs                                       FastAPI docs url
SWAGGER_UI_OAUTH2_REDIRECT_URL /docs/oauth2-redirect                       FastAPI openapi aith redirect url
CORS                           ["http://localhost"]                        FastAPI Cross-origin resource sharing
GZIP_ENABLED                   True                                        FastAPI enable Gzip compression
GZIP_COMPRESS_LEVEL            5                                           FastAPI Gzip compress level
GZIP_MINIMUM_SIZE              500                                         FastAPI minimum size for compression
REDOC_URL                      /redoc
DGGRID_PATH                    None                                        Path to dggrid executable, only use with IGEO7DGGRSProvider
============================== =========================================== ===============================

