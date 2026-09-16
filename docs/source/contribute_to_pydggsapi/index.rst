Contribution to pydggsapi
=============================

Using Docker Compose for development
------------------------------------------

Contributors can develop pydggsapi using Docker to set up an isolated environment, reducing dependency issues. It can be done by configuring the `docker-compose.yaml` file in the docker folder to set up the development environment as needed. The following document outlines the steps to set up the development container. We assumed that the Docker service is installed on the development platform as a prerequisite.

Configuration of `docker-compose.yaml` and `docker_development.env`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Inside the `docker` folder under the local repository, there are two files that need to be configured before starting the development container, they are: 
 1. `docker-compose.yaml` and 
 2. `docker_development.env`

docker-compose.yaml
"""""""""""""""""""

+----------+-------------------------+-----------------------------------------------------------------------------+
| services | path                    | description                                                                 |
+==========+=========================+=============================================================================+ 
| api      | developement/watch/path | Automatically updates the running container in real-time when modifying the |
|          |                         | local source. It should point to the `pydggsapi` folder in the local        |
|          |                         | repository.                                                                 |
+----------+-------------------------+-----------------------------------------------------------------------------+



==================  ==================  =======================
volumes                     path        description
==================  ==================  =======================
dggs_api_config     driver_opts/device  Absolute path to a local folder that holds pydggsapi configuration files
pydggsapi_datasets  driver_opts/device  Absolute path to a local folder that holds the set of collections to publish
==================  ==================  =======================


docker_development.env
""""""""""""""""""""""

Contributors can export any environment variables defined in :doc:`Appendix </appendix/index>` to override the default value. For example, the file name of the dggs_api_config may differ from Docker's default value (`pydggsapi-config.json`). 

Collection paths
""""""""""""""""
The volume `pydggsapi_datasets` is mapped to the path `/opt/local/src/pydggsapi/demo_data` of the Docker container; therefore, the collection paths defined in the pydggsapi configuration(DGGS_API_CONFIG) should follow the mapped path, where it should point to `demo_data/<data_source_name>`

For example:

.. code-block:: json

   "est_topo_dem_10m_elva": {
        "filepath": "demo_data/est_topo_dem_10m_clipped_Elva_igeo7_datatree.zarr",
        "id_col": "zone_id",
        "zone_groups":{
             "1": "refinement_level_1",
             "2": "refinement_level_2",
        }
    }



Start up the Docker container with `docker-compose.yaml`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

After the above configurations are set correctly, the development container can be started by the following command at the root directory of the local repository. 

.. code-block:: bash

    sudo docker compose -f ./docker/docker-compose.yaml up api --watch


Using Docker Compose to run unit test cases with pytest
-----------------------------------------------------------

Contributors can also develop and run unit tests of pydggsapi with a Docker container. It can be done by configuring the `docker-compose.yaml` file in the Docker folder to set up the development environment as needed. The following document outlines the steps to set up the test-runner container. 

Configuration of `docker-compose.yaml` and `docker_pytest.env`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Inside the `docker` folder under the local repository, there are two files that need to be configured before starting the development container, they are: 
 1. `docker-compose.yaml` and 
 2. `docker_pytest.env`


docker-compose.yaml
"""""""""""""""""""

==================  ==================  =======================
volumes                     path        description
==================  ==================  =======================
dggs_api_config     driver_opts/device  Absolute path to a local folder that holds pydggsapi configuration files
pytest_datasets     driver_opts/device  Absolute path to a local folder that holds the set of collections for testing
pytest_testcases    driver_opts/device  Absolute path to a local folder that holds the set of test cases performed by pytest
==================  ==================  =======================

docker_pytest.env
""""""""""""""""""""""

Contributors can export any environment variables defined in :doc:`Appendix </appendix/index>` to override the default value. For example, the file name of the dggs_api_config may differ from the one used in the development configuration.

Collection paths
""""""""""""""""
The volume `pytest_datasets` is mapped to the path `/opt/local/src/pydggsapi/testing_data` of the Docker container; therefore, the collection paths defined in the pydggsapi configuration(DGGS_API_CONFIG) should follow the mapped path, where it should point to `testing_data/<data_source_name>`

For example:

.. code-block:: json

   "est_topo_dem_10m_elva": {
        "filepath": "testing_data/est_topo_dem_10m_clipped_Elva_igeo7_datatree.zarr",
        "id_col": "zone_id",
        "zone_groups":{
             "1": "refinement_level_1",
             "2": "refinement_level_2",
        }
    }


Start up the Docker container with `docker-compose.yaml`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

After the above configurations are set correctly, the test-runner container can be started by the following command at the root directory of the local repository. 

.. code-block:: bash

    sudo docker compose -f ./docker/docker-compose.yaml up test-runner



