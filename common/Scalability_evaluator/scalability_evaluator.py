#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import logging
import pathlib
import time
from typing import List, Set, Dict

import redis

import carlhauser_server.Configuration.distance_engine_conf as dec
import carlhauser_server.Configuration.feature_extractor_conf as fec
import common.ChartMaker.two_dimensions_plot as two_dimensions_plot
import common.ImportExport.json_import_export as json_import_export
import common.Scalability_evaluator.scalability_conf as scalability_conf
import common.TestInstanceLauncher.one_db_conf as test_database_only_conf
import common.TestInstanceLauncher.one_db_instance_launcher as test_database_handler
from carlhauser_client.API.extended_api import Extended_API
from carlhauser_server.DatabaseAccessor.database_utilities import DBUtilities
from common.Scalability_evaluator.scalability_datastructures import ScalabilityData, ComputationTime, PathlibSet, Pathobject
from common.environment_variable import dir_path
from common.environment_variable import load_server_logging_conf_file
import carlhauser_client.Helpers.dict_utilities as dict_utilities

load_server_logging_conf_file()


class ScalabilityEvaluator:

    def __init__(self, tmp_scalability_conf=scalability_conf.Default_scalability_conf()):
        self.logger = logging.getLogger()
        self.ext_api: Extended_API = Extended_API.get_api()

        # self.test_db_handler: test_database_handler.TestInstanceLauncher = None
        print(tmp_scalability_conf)
        self.scalability_conf: scalability_conf.Default_scalability_conf = tmp_scalability_conf

    @staticmethod
    def load_pictures(pictures_folder: pathlib.Path) -> Set[pathlib.Path]:
        pictures_set = set()

        # Load all path to pictures in a set
        for x in pictures_folder.resolve().glob('**/*'):  # pictures_folder.resolve().iterdir():
            if x.is_file():
                pictures_set.add(Pathobject(x))

        return pictures_set

    def evaluate_scalability(self,
                             pictures_folder: pathlib.Path,
                             output_folder: pathlib.Path) -> ScalabilityData:

        # ==== Separate the folder files ====
        pictures_set = self.load_pictures(pictures_folder)

        # Extract X pictures to evaluate their matching (at each cycle, the sames)
        # TODO : REMOVED FOR NOW. SHOULD BE ABLE TO DELETE RESULTS TO WORK. # pictures_set, pics_to_evaluate = self.biner(pictures_set, self.scalability_conf.NB_PICS_TO_REQUEST)

        # Put TOTAL-X pictures into boxes (10, 50, 100, 500, 1000, 5000, 10000, 50000, 100000 ...)
        # Generate the boxes
        list_boxes_sizes = self.scalability_conf.generate_boxes(self.scalability_conf.MAX_NB_PICS_TO_SEND)

        # ==== Upload pictures + Make requests ====
        scalability_data = self.get_scalability_list(list_boxes_sizes, pictures_set, output_folder=output_folder)  # , pics_to_evaluate)

        self.logger.info(f"Scalability data : {scalability_data}")
        self.print_data(scalability_data, output_folder)

        return scalability_data

    def get_scalability_list(self, list_boxes_sizes: List[int], pictures_set: Set[pathlib.Path],  # pics_to_evaluate: Set[pathlib.Path],
                             dist_conf: dec.Default_distance_engine_conf = dec.Default_distance_engine_conf(),
                             fe_conf: fec.Default_feature_extractor_conf = fec.Default_feature_extractor_conf(), output_folder: pathlib.Path = None):
        # ==== Upload pictures + Make requests ====
        scalability_data = ScalabilityData()

        db_conf = test_database_only_conf.TestInstance_database_conf()  # For test sockets only

        # Launch a modified server
        self.logger.debug(f"Creation of a full instance of redis (Test only) ... ")
        test_db_handler = test_database_handler.TestInstanceLauncher()
        test_db_handler.create_full_instance(db_conf=db_conf, dist_conf=dist_conf, fe_conf=fe_conf)

        # Get direct access to DB to retrieve statistics
        db_access_no_decode = redis.Redis(unix_socket_path=test_db_handler.db_handler.get_socket_path('test'), decode_responses=False)
        db_access_decode = redis.Redis(unix_socket_path=test_db_handler.db_handler.get_socket_path('test'), decode_responses=True)
        db_utils = DBUtilities(db_access_decode=db_access_decode, db_access_no_decode=db_access_no_decode)

        nb_picture_total_in_db = 0
        global_mapping = {}

        # For each box
        for i, curr_box_size in enumerate(list_boxes_sizes):
            # Get a list of pictures to send
            pictures_set, pics_to_request = self.biner(pictures_set, self.scalability_conf.NB_PICS_TO_REQUEST)
            pictures_set, pics_to_store = self.biner(pictures_set, curr_box_size)

            self.logger.info(f"Nb of pictures left to be uploaded later : {len(pictures_set)}")
            self.logger.info(f"Nb of pictures to upload (adding) : {len(pics_to_store)}")

            # If we are not out of pictures to send
            if len(pics_to_store) != 0:
                # Evaluate time for this database size and store it
                tmp_scal_datastruct, mapping, request_list = self.evaluate_scalability_lists(list_pictures_eval=pics_to_request,  # pics_to_evaluate,
                                                                                             list_picture_to_up=pics_to_store,
                                                                                             tmp_id=i)
                global_mapping = {**global_mapping, **mapping}

                # Store few more values
                # Nb of picture in teh database right now
                nb_picture_total_in_db += tmp_scal_datastruct.nb_picture_added
                tmp_scal_datastruct.nb_picture_total_in_db = db_utils.get_nb_stored_pictures()

                # Nb of pictures sent at the beginning to be added
                tmp_scal_datastruct.nb_picture_tried_to_be_added = len(pics_to_store)
                tmp_scal_datastruct.nb_picture_tried_to_be_requested = len(pics_to_request)

                # Nb of cluster and their content
                tmp_scal_datastruct.nb_clusters_in_db = len(db_utils.get_cluster_list())
                tmp_scal_datastruct.clusters_sizes = db_utils.get_list_cluster_sizes()

                # Print error
                if tmp_scal_datastruct.nb_picture_total_in_db != nb_picture_total_in_db:
                    self.logger.error(
                        f"Error in scalability evaluator, number of picture really in DB and computed as should being in DB are differents : {tmp_scal_datastruct.nb_picture_total_in_db} {nb_picture_total_in_db}")
                scalability_data.list_request_time.append(tmp_scal_datastruct)

                if output_folder is not None:
                    save_path_json = output_folder / ("global_mapping" + str(i) + ".json")
                    json_import_export.save_json(request_list, save_path_json)

                    save_path_json = output_folder / ("mapping" + str(i) + ".json")
                    json_import_export.save_json(mapping, save_path_json)

        # Export graph
        if output_folder is not None:
            self.export_graph(output_folder, global_mapping)
            '''
            db_dump = self.ext_api.get_db_dump_as_graph()
            db_dump_dict = db_dump.export_as_dict()
            save_path_json = output_folder / "original_storage_graph_dump.json"
            json_import_export.save_json(db_dump_dict, save_path_json)
            # Full of new ids

            save_path_json = output_folder / "global_mapping.json"
            json_import_export.save_json(global_mapping, save_path_json)
            # old name -> new id

            db_dump_dict = dict_utilities.apply_revert_mapping(db_dump_dict, global_mapping)

            # db_dump.replace_id_from_mapping(mapping)
            db_dump_dict = dict_utilities.copy_id_to_image(db_dump_dict)

            save_path_json = output_folder / "modified_storage_graph_dump.json"
            json_import_export.save_json(db_dump_dict, save_path_json)
            '''
        else:
            self.logger.critical("outputfolder is None ! ")

            # node server.js -i ./../DATASETS/PHISHING/PHISHING-DATASET-DISTRIBUTED-DEDUPLICATED/ -t ./TMP -o ./TMP -j ./../douglas-quaid/datasets/OUTPUT_EVALUATION/threshold_0.0195/modified_storage_graph_dump.json

        # Kill server instance
        self.logger.debug(f"Shutting down Redis test instance")
        test_db_handler.tearDown()

        return scalability_data

    def export_graph(self, output_folder: pathlib.Path, global_mapping):
        db_dump = self.ext_api.get_db_dump_as_graph()
        db_dump_dict = db_dump.export_as_dict()
        save_path_json = output_folder / "original_storage_graph_dump.json"
        json_import_export.save_json(db_dump_dict, save_path_json)
        # Full of new ids

        save_path_json = output_folder / "global_mapping.json"
        json_import_export.save_json(global_mapping, save_path_json)
        # old name -> new id

        db_dump_dict = dict_utilities.apply_revert_mapping(db_dump_dict, global_mapping)

        # db_dump.replace_id_from_mapping(mapping)
        db_dump_dict = dict_utilities.copy_id_to_image(db_dump_dict)

        save_path_json = output_folder / "modified_storage_graph_dump.json"
        json_import_export.save_json(db_dump_dict, save_path_json)

    def evaluate_scalability_lists(self,
                                   list_pictures_eval: Set[pathlib.Path],
                                   list_picture_to_up: Set[pathlib.Path],
                                   tmp_id: int) -> (ComputationTime, Dict, List):
        # Tricky tricky : create a fake Pathlib folder to perform the upload
        self.logger.debug(f"Faking pathlib folders ... ")
        simulated_folder_add = PathlibSet(list_picture_to_up)
        simulated_folder_request = PathlibSet(list_pictures_eval)

        # Time Management - Start
        self.logger.debug(f"Starting timer ... ")
        start_upload = time.time()

        # Upload pictures of one bin
        self.logger.debug(f"Sending pictures ... ")
        mapping, nb_pictures_add = self.ext_api.add_many_pictures_and_wait_global(simulated_folder_add)

        # Time Management - Stop
        self.logger.debug(f"Stopping timer ... ")
        stop_upload = abs(start_upload - time.time())
        self.logger.info(f"Upload of {nb_pictures_add} took {stop_upload}s, so {stop_upload / (nb_pictures_add if nb_pictures_add != 0 else 1)}s per picture.")

        # Time Management - Start
        self.logger.debug(f"Starting timer ... ")
        start_request = time.time()

        # Make request of the X standard pictures
        self.logger.debug(f"Requesting pictures ... ")
        request_list, nb_pictures_req = self.ext_api.request_many_pictures_and_wait_global(simulated_folder_request)

        # Time Management - Stop
        self.logger.debug(f"Stopping timer ... ")
        stop_request = abs(start_request - time.time())
        self.logger.info(f"Request of {nb_pictures_req} took {stop_request}s, so {stop_request / (nb_pictures_req if nb_pictures_req != 0 else 1)}s per picture.")

        # Construct storage object = Store the request times
        resp_time = ComputationTime()
        resp_time.adding_time = stop_upload
        resp_time.request_time = stop_request
        resp_time.nb_picture_added = nb_pictures_add
        resp_time.nb_picture_requested = nb_pictures_req
        resp_time.iteration = tmp_id

        return resp_time, mapping, request_list

    @staticmethod
    def biner(potential_pictures: Set[pathlib.Path], nb_to_bin):
        # Extract <nbtobin> pitures from the provided set. Return both modified set and bin
        bin_set = set()

        for i in range(min(nb_to_bin, len(potential_pictures))):
            bin_set.add(potential_pictures.pop())

        return potential_pictures, bin_set

    def print_data(self, scalabilitygraph: ScalabilityData, output_folder: pathlib.Path, file_name: str = "scalability_graph.pdf"):
        twoDplot = two_dimensions_plot.TwoDimensionsPlot()
        twoDplot.print_scalability_data(scalabilitygraph, output_folder, file_name)

        # Save to file
        json_import_export.save_json(scalabilitygraph.list_request_time, output_folder / "scalability_graph.json")
        self.logger.info("Results scalability_graph json saved.")


# Launcher for this worker. Launch this file to launch a worker
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Launch DouglasQuaid Scalability Evaluator on your own dataset to get custom scalability measure')
    parser.add_argument("-s", '--source_path', dest="src", required=True, type=dir_path, action='store',
                        help='Source path of folder of pictures to evaluate. Should be a subset of your production data.')
    parser.add_argument("-d", '--dest_path', dest="dest", required=True, type=dir_path, action='store',
                        help='Destination path to store results of the evaluation (configuration files generated, etc.)')
    args = parser.parse_args()

    try:
        scalability_evaluator = ScalabilityEvaluator()
        scalability_evaluator.evaluate_scalability(pathlib.Path(args.src), pathlib.Path(args.dest))

    except AttributeError as e:
        parser.error(f"Too few arguments : {e}")
