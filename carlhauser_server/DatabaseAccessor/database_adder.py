#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from typing import List, Dict
from pprint import pformat
import math
import carlhauser_server.Configuration.database_conf as database_conf
import carlhauser_server.Configuration.distance_engine_conf as distance_engine_conf
import carlhauser_server.Configuration.feature_extractor_conf as feature_extractor_conf
import carlhauser_server.DatabaseAccessor.database_common as database_common
from carlhauser_server.Helpers import arg_parser
from common.environment_variable import load_server_logging_conf_file, make_small_line, QueueNames
import carlhauser_server.DistanceEngine.scoring_datastrutures as scoring_datastrutures

load_server_logging_conf_file()


class Database_Adder(database_common.Database_Common):
    """
    Heritate from the database common, and so has already built in access to cache, storage ..
    """

    def __init__(self, tmp_db_conf: database_conf.Default_database_conf,
                 tmp_dist_conf: distance_engine_conf.Default_distance_engine_conf,
                 tmp_fe_conf: feature_extractor_conf.Default_feature_extractor_conf):
        # STD attributes
        super().__init__(tmp_db_conf, tmp_dist_conf, tmp_fe_conf)

    def process_fetched_data(self, fetched_id, fetched_dict):
        """
        Method to overwrite to specify the worker. Called each time something is fetched from queue.
        Add picture to storage, evaluate near-similar pictures, choose a good cluster and add the picture to this cluster.
        TODO : Add the picture to review and process the recalculation of representative pictures
        :param fetched_id: id to process
        :param fetched_dict: data to process
        :return: Nothing (or to be defined)
        """

        self.logger.info(f"DB Adder worker processing {fetched_id}")
        self.logger.debug(f"Fetched dict {fetched_dict}")

        # Add picture to storage
        self.logger.info(f"Adding picture to storage under id {fetched_id}")
        self.add_picture_to_storage(
            self.storage_db_no_decode, fetched_id, fetched_dict)  # NOT DECODE

        # Get top matching pictures in clusters
        top_matching_pictures, list_matching_clusters = self.get_top_matching_pictures(
            fetched_dict)

        self.logger.debug(
            f"list_matching_clusters {pformat(list_matching_clusters)}")
        self.logger.debug(
            f"top_matching_pictures {pformat(top_matching_pictures)}")

        # Depending on the quality of the match ...
        # if self.is_good_match(top_matching_pictures):
        # TODO : TO VERIFY WHICH TO PICK
        cluster_id = self.choose_cluster_from_cluster_matches(
            list_matching_clusters)
        # cluster_id = self.choose_cluster_from_pics_matches(top_matching_pictures)
        if cluster_id is not None:
            self.logger.error(
                f"Match is good enough with at least one cluster")

            # Add picture to best picture's cluster
            cluster_id = top_matching_pictures[0].cluster_id
            self.db_utils.add_picture_to_cluster(fetched_id, cluster_id)

            # Re-evaluate representative picture(s) of cluster
            self.reevaluate_representative_picture_order(
                cluster_id, fetched_id=fetched_id)
            self.logger.info(
                f"Picture added in existing cluster : {cluster_id}")

        else:
            self.logger.info(f"Match not good enough, with any cluster")
            # Add picture to it's own cluster
            # First picture is "alone" and so central (score=0)
            cluster_id = self.db_utils.add_picture_to_new_cluster(
                fetched_id, score=0)
            self.logger.info(
                f"Picture added in its own new cluster : {cluster_id}")

        # Add to a queue, to be reviewed later, when more pictures will be added
        # TODO : TO ADD self.db_utils.add_to_review(fetched_id)
        self.logger.info(f"Adding done.")
        print(make_small_line())
        print("Adder Worker ready to accept more queries.")

    def choose_cluster_from_cluster_matches(self, list_matching_clusters: List[scoring_datastrutures.ClusterMatch]) -> str:

        # For each picture that has matched
        for curr_cluster in list_matching_clusters:

            # normalized_dist = cur_pic.distance
            if curr_cluster.decision.name == scoring_datastrutures.DecisionTypes.YES.name and \
                    curr_cluster.distance <= self.dist_conf.MAX_DIST_FOR_NEW_CLUSTER:
                self.logger.error(
                    f"Cluster : {curr_cluster.cluster_id} matches enough. Kept")

                return curr_cluster.cluster_id
            else:
                self.logger.error(
                    f"Cluster : {curr_cluster.cluster_id} not matches enough. Discarded.")

        return None

    def choose_cluster_from_pics_matches(self, top_matching_pictures: List[scoring_datastrutures.ImageMatch]) -> str:

        new_top_matching_list = []
        for cur_pic in top_matching_pictures:
            normalized_dist = self.get_ponderated_distance(cur_pic)
            cur_pic.distance = normalized_dist
            new_top_matching_list.append(cur_pic)

        new_top_matching_list.sort(key=lambda x: x.distance)

        # For each picture that has matched
        for cur_pic in new_top_matching_list:

            # normalized_dist = cur_pic.distance
            if cur_pic.decision.name == scoring_datastrutures.DecisionTypes.YES.name and cur_pic.distance <= self.dist_conf.MAX_DIST_FOR_NEW_CLUSTER:
                return cur_pic.cluster_id

        return None

    def get_ponderated_distance(self, picture: scoring_datastrutures.ImageMatch):

        # dist = real dist + majoration/minoration depending on the % difference between expected cluster size and normal size
        target_cluster_size = math.sqrt(self.db_utils.get_nb_stored_pictures())
        # self.logger.debug(f"target_cluster_size : {target_cluster_size} / picture.distance {picture.distance} / self.db_utils.get_pictures_of_cluster(picture.cluster_id) {self.db_utils.get_pictures_of_cluster(picture.cluster_id)}")
        normalized_dist = picture.distance + ((len(self.db_utils.get_pictures_of_cluster(
            picture.cluster_id)) - target_cluster_size) / target_cluster_size)

        return normalized_dist

    def reevaluate_representative_picture_order(self, cluster_id, fetched_id=None):
        """
        Re-evaluate the representative picture of the cluster <cluster_id>,
        knowing or not, that the last added and non evaluated picture of the cluster is <fetched_id>
        :param cluster_id: the id of the cluster to reevaluate
        :param fetched_id: optional, can speed up the process if we know the last picture which was added
        :return: Nothing
        """

        if fetched_id is None:
            # We don't know which picture was the last one added. Perform full re-evaluation
            # 0(N²) operation with N being the number of elements in the cluster

            # Get all picture ids of the cluster
            pictures_sorted_set = self.db_utils.get_pictures_of_cluster(
                cluster_id)

            for curr_pic in pictures_sorted_set:
                # For each picture, compute its centrality and store it
                curr_pic_dict = self.get_dict_from_key(
                    self.storage_db_no_decode, curr_pic, pickle=True)
                centrality_score = self.compute_centrality(
                    pictures_sorted_set, curr_pic_dict)

                # Replace the current sum (set value) of distance by the newly computed on
                self.db_utils.update_picture_score_of_cluster(
                    cluster_id, curr_pic, centrality_score)
        else:
            # We know which picture was added last, and so begin by this one.
            # 0(2.N) operation with N being the number of elements in the cluster

            # Get all picture ids of the cluster, with their actual score
            pictures_sorted_set = self.db_utils.get_pictures_of_cluster(
                cluster_id, with_score=True)

            # Compute the centrality of the new picture and update its score : 0(N)
            new_pic_dict = self.get_dict_from_key(
                self.storage_db_no_decode, fetched_id, pickle=True)
            centrality_score = self.compute_centrality(
                [i[0] for i in pictures_sorted_set], new_pic_dict)
            self.db_utils.update_picture_score_of_cluster(
                cluster_id, fetched_id, centrality_score)

            # And for each other picture, add the distance between itself and this new picture to its score : 0(N)
            for curr_pic, score in pictures_sorted_set:
                # Important ! Because current score is not updated by previous calculation (tricky race condition)
                if curr_pic == fetched_id:
                    continue
                curr_target_pic_dict = self.get_dict_from_key(
                    self.storage_db_no_decode, curr_pic, pickle=True)
                delta_centrality, decision = self.de.get_dist_and_decision_picture_to_picture(
                    new_pic_dict, curr_target_pic_dict)
                # Update the centrality of the current picture with the new "added value".
                self.db_utils.update_picture_score_of_cluster(
                    cluster_id, curr_pic, score + delta_centrality)

        # TODO : Somewhat already done before. May be able to memoize the computed values ?

    def compute_centrality(self, pictures_list_id: List, picture_dict: Dict) -> float:
        """
        Returns centrality of a picture within a list of other pictures.
        :param pictures_list_id: list of pictures id in which the centrality is measured
        :param picture_dict: the picture (dict) which centrality is computed
        :return: the centrality of the picture dict
        """

        self.logger.debug(picture_dict)
        curr_sum = 0

        # For each picture, compute its distance to other picture, summing it temporary
        for curr_target_pic in pictures_list_id:
            curr_target_pic_dict = self.get_dict_from_key(
                self.storage_db_no_decode, curr_target_pic, pickle=True)
            dist, decision = self.de.get_dist_and_decision_picture_to_picture(
                picture_dict, curr_target_pic_dict)
            # TODO : use decision in centrality computation ?
            curr_sum += dist

        self.logger.debug(f"Computed centrality for {pictures_list_id}")

        return curr_sum


# Launcher for this worker. Launch this file to launch a worker
if __name__ == '__main__':
    # python3 -m cProfile -o temp.dat <PROGRAM>.py
    # python3 -m cProfile -o database_adder.dat ./database_adder.py -dbc ./../../tmp_db_conf.json -distc ./../../tmp_dist_conf.json -fec ./../../tmp_fe_conf.json
    # python3 ./database_adder.py -dbc ./../../tmp_db_conf.json -distc ./../../tmp_dist_conf.json -fec ./../../tmp_fe_conf.json
    parser = argparse.ArgumentParser(
        description='Launch a worker for a specific task : adding picture to database')
    parser = arg_parser.add_arg_db_conf(parser)
    parser = arg_parser.add_arg_dist_conf(parser)
    parser = arg_parser.add_arg_fe_conf(parser)

    args = parser.parse_args()

    db_conf, dist_conf, fe_conf, _ = arg_parser.parse_conf_files(args)

    # Create the Database Accessor and run it
    db_accessor = Database_Adder(db_conf, dist_conf, fe_conf)
    db_accessor.input_queue = QueueNames.DB_TO_ADD
    db_accessor.run(sleep_in_sec=db_conf.ADDER_WAIT_SEC)
