#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Not that this could use : flask/bin/python
# Inspired from : https://github.com/D4-project/IPASN-History/blob/master/website/web/__init__.py
# If you are derouted by the lack of decorator, go there : https://stackoverflow.com/questions/17129573/can-i-use-external-methods-as-route-decorators-in-python-flask

import argparse
import logging
import time
import uuid
from typing import Dict

import flask
import werkzeug.datastructures as datastructures

import carlhauser_server.API.in_memory_files_ops as id_generator
import carlhauser_server.Configuration.database_conf as database_conf
import carlhauser_server.Configuration.webservice_conf as webservice_conf
import carlhauser_server.DatabaseAccessor.database_utilities as db_utils
import carlhauser_server.DatabaseAccessor.database_worker as database_worker
import common.ImportExport.json_import_export as json_import_export
import common.ImportExport.picture_import_export as picture_import_export
from carlhauser_server.Helpers import arg_parser
from common.environment_variable import QueueNames, EndPoints
from common.environment_variable import get_homedir
from common.environment_variable import load_server_logging_conf_file
from carlhauser_server.Singletons import database_start_stop
load_server_logging_conf_file()


# ==================== ------ SERVER Flask API definition ------- ====================

class EndpointAction(object):
    """
    Defines an Endpoint for a specific action for any client.
    """

    def __init__(self, action):
        """
        Create the endpoint by specifying which action we want the endpoint to perform, at each call
        :param action: The function to execute on endpoint call
        """
        # Defines which action (which function) should be called
        self.action = action

        # DEBUG FOR TEST PURPOSES # self.response = flask.Response("Welcome to carl-hauser", status=200, headers={})

    def __call__(self, *args):
        """
        Standard method that effectively perform the stored action of this endpoint.
        :param args: Arguments to give to the stored function
        :return: The response, which is a jsonified version of the function returned value
        """

        # Perform the action
        answer = self.action(*args)

        # Create the answer (bundle it in a correctly formatted HTTP answer)
        if isinstance(answer, str):
            # If it's a string, we bundle it has a HTML-like answer
            self.response = flask.Response(answer, status=200, headers={})
        else:
            # If it's something else (dict, ..) we jsonify and send it
            self.response = flask.jsonify(answer)

        # Send it
        return self.response


class FlaskAppWrapper(object):
    def __init__(self, name: str, tmp_ws_conf: webservice_conf.Default_webservice_conf, tmp_db_conf: database_conf.Default_database_conf):
        # STD attributes
        self.ws_conf = tmp_ws_conf
        self.logger = logging.getLogger(__name__)

        # Specific attributes
        self.app = flask.Flask(name)

        # An accessor to push stuff in queues, mainly
        self.database_worker: database_worker.Database_Worker = database_worker.Database_Worker(
            tmp_db_conf=tmp_db_conf)
        self.db_utils: db_utils.DBUtilities = None
        self.db_startstop = database_start_stop.Database_StartStop(
            db_conf=tmp_db_conf)

    def run(self):
        """
        Final action to call to run the flask process, which generate endpoints, and so.
        Handle SLL Certificate, if they are provided = use them, else = self sign a certificate on the fly
        :return: no return (continuously executing. Return error code if stopped and so)
        """
        if self.ws_conf.CERT_FILE is None or self.ws_conf.KEY_FILE is None:
            self.logger.error(
                f"Provided CERT OR KEY file not found :  {self.ws_conf.CERT_FILE} and {self.ws_conf.KEY_FILE}")
            # Replaced with below code to run it using waitress
            # serve(self.app, host=self.ws_conf.ip, port=self.ws_conf.port, ssl_context='adhoc')
            self.app.run(ssl_context='adhoc', port=self.ws_conf.port)
        else:
            self.logger.info(
                f"Provided CERT OR KEY file used : {self.ws_conf.CERT_FILE} and {self.ws_conf.KEY_FILE}")
            # Replaced with below code to run it using waitress
            self.app.run(ssl_context=(str(self.ws_conf.CERT_FILE), str(
                self.ws_conf.KEY_FILE)), port=self.ws_conf.port)  # ssl_context='adhoc')
            # serve(self.app, host=self.ws_conf.ip, port=self.ws_conf.port, ssl_context=(str(self.ws_conf.CERT_FILE), str(self.ws_conf.KEY_FILE)))

            self.logger.critical(
                f"Server running on {self.ws_conf.ip}:{self.ws_conf.port} ... ")

    def add_all_endpoints(self):
        """
        Add all endpoints = all callable URL of the API, and link them to the good functions
        :return: Nothing
        """

        # Add root endpoint
        tmp_ep_name = "/"
        self.add_endpoint(endpoint=tmp_ep_name,
                          endpoint_name=tmp_ep_name, handler=self.ping)

        # Add action endpoints
        tmp_ep_name = "/" + EndPoints.ADD_PICTURE
        self.add_endpoint(endpoint=tmp_ep_name,
                          endpoint_name=tmp_ep_name, handler=self.add_picture)
        tmp_ep_name = "/" + EndPoints.REQUEST_PICTURE
        self.add_endpoint(endpoint=tmp_ep_name, endpoint_name=tmp_ep_name,
                          handler=self.request_similar_picture)
        tmp_ep_name = "/" + EndPoints.WAIT_FOR_REQUEST
        self.add_endpoint(
            endpoint=tmp_ep_name, endpoint_name=tmp_ep_name, handler=self.is_request_ready)
        tmp_ep_name = "/" + EndPoints.WAIT_FOR_ADD
        self.add_endpoint(
            endpoint=tmp_ep_name, endpoint_name=tmp_ep_name, handler=self.are_pipelines_empty)
        tmp_ep_name = "/" + EndPoints.EMPTY_PIPELINE
        self.add_endpoint(
            endpoint=tmp_ep_name, endpoint_name=tmp_ep_name, handler=self.are_pipelines_empty)
        tmp_ep_name = "/" + EndPoints.GET_REQUEST_RESULT
        self.add_endpoint(endpoint=tmp_ep_name,
                          endpoint_name=tmp_ep_name, handler=self.get_results)
        tmp_ep_name = "/" + EndPoints.REQUEST_DB
        self.add_endpoint(
            endpoint=tmp_ep_name, endpoint_name=tmp_ep_name, handler=self.export_db_as_graphe)
        tmp_ep_name = "/" + EndPoints.FLUSH_DB
        self.add_endpoint(
            endpoint=tmp_ep_name, endpoint_name=tmp_ep_name, handler=self.flush_databases)

    def add_endpoint(self, endpoint=None, endpoint_name=None, handler=None):
        """
        Add one endpoint to the flask application. Accept GET, POST and PUT.
        :param endpoint: Callable URL.
        :param endpoint_name: Name of the Endpoint
        :param handler: function to execute on call on the URL
        :return: Nothing
        """
        self.app.add_url_rule(endpoint, endpoint_name, EndpointAction(
            handler), methods=['GET', 'POST', 'PUT'])

    # ==================== ------ API Calls ------- ====================

    def ping(self, *args) -> Dict:
        """
        Handle a ping request on server side. Creates a pong answer
        :param args: None is required
        :return: The result json (pong)
        """

        result_json = {}
        result_json["Called_function"] = "ping"
        result_json = self.add_std_info(result_json)

        result_json["Status"] = "The API is ALIVE :)"
        # Note that "flask.request" is a global object, but is linked to the local context by flask. No worries :)

        return result_json
        # Test it with curl 127.0.0.1:443

    # ================= ADD PICTURES =================
    def add_picture(self) -> Dict:
        """
        Handle an adding of a picture request on server side.
        :return: The result json (status of the request, etc.)
        """
        result_json = {}
        result_json["Called_function"] = EndPoints.ADD_PICTURE
        result_json = self.add_std_info(result_json)

        # Answer ONLY to PUT HTTP request
        if flask.request.method == 'PUT':
            try:
                # Received : werkzeug.datastructures.FileStorage. Should use ".read()" to get picture's value
                f = flask.request.files['image']

                # Convert, save and send picture to server
                result_json = self.enqueue_and_save_picture(file=f,
                                                            result_json=result_json,
                                                            queue=QueueNames.FEATURE_TO_ADD)

            except Exception as e:
                self.logger.error(f"Error during PUT handling {e}")
                result_json["Status"] = "Failure"
                result_json["Error"] = "Error during Hash computation or database adding"
        else:
            result_json = self.add_bad_method_info(
                result_json, good_method_instead="PUT")

        return result_json
        # Test it with curl 127.0.0.1:443/add_pict

    # ================= ADD PICTURES - WAITING =================
    def are_pipelines_empty(self) -> Dict:
        """
        Handle a check of emptiness on the pipelines (list of queues)
        :return: The result json (status of the request, etc.)
        """

        result_json = {}
        result_json["Called_function"] = EndPoints.EMPTY_PIPELINE
        result_json = self.add_std_info(result_json)

        # Answer to PUT HTTP request
        if flask.request.method == 'GET':
            try:
                # Fetch results
                # TODO : Special function for "cleaner/more performant" check ?
                result_json["are_empty"] = self.database_worker.are_all_queues_empty()
                result_json["Status"] = "Success"

            except Exception as e:
                self.logger.error(
                    f"Normal error during GET handling ({EndPoints.EMPTY_PIPELINE} request) {e}")
                result_json["Status"] = "Failure"
                result_json["Error"] = "Error during queues request"
        else:
            result_json = self.add_bad_method_info(
                result_json, good_method_instead="GET")

        return result_json
        # Test it with curl 127.0.0.1:443/are_pipelines_empty

    # ================= REQUEST PICTURES =================

    def request_similar_picture(self) -> Dict:
        """
        Handle a request of one picture, to return a list of similar pictures
        :return: The result json (status of the request, etc.)
        """

        result_json = {}
        result_json["Called_function"] = EndPoints.REQUEST_PICTURE
        result_json = self.add_std_info(result_json)

        # Answer to PUT HTTP request
        if flask.request.method == 'POST':
            try:
                # Received : werkzeug.datastructures.FileStorage. Should use ".read()" to get picture's value
                f = flask.request.files['image']

                # Convert, save and send picture to server
                result_json = self.enqueue_and_save_picture(file=f,
                                                            result_json=result_json,
                                                            queue=QueueNames.FEATURE_TO_REQUEST)

            except Exception as e:
                self.logger.error(f"Error during PUT handling {e}")
                result_json["Status"] = "Failure"
                result_json["Error"] = "Error during Hash computation or database request"
        else:
            result_json = self.add_bad_method_info(
                result_json, good_method_instead="POST")

        return result_json
        # Test it with curl 127.0.0.1:443/request_similar_picture

    def get_results(self) -> Dict:
        """
        Handle a retrieval of results
        :return: The result json (status of the request, etc.)
        """

        result_json = {}
        result_json["Called_function"] = EndPoints.GET_REQUEST_RESULT
        result_json = self.add_std_info(result_json)

        # Answer to PUT HTTP request
        if flask.request.method == 'GET':
            try:
                # Received : werkzeug.datastructures.FileStorage. Should use ".read()" to get picture's value
                tmp_id = flask.request.args.get('request_id')
                self.logger.debug(
                    f"Request ID to be answered in server : {type(tmp_id)} ==> {tmp_id} ")  # {f.read()}

                # Fetch results
                result_dict = self.database_worker.get_request_result(
                    self.database_worker.cache_db_no_decode, tmp_id)

                result_json["Status"] = "Success"
                result_json["request_id"] = tmp_id
                result_json["results"] = result_dict
            except Exception as e:
                self.logger.error(f"Error during GET handling {e}")
                result_json["Status"] = "Failure"
                result_json["Error"] = "Error during Hash computation or database request"
        else:
            result_json = self.add_bad_method_info(
                result_json, good_method_instead="GET")

        return result_json
        # Test it with curl 127.0.0.1:443/get_results

    # ================= REQUEST PICTURES - WAITING =================

    def is_request_ready(self) -> Dict:
        """
        Handle a check of a request readiness
        :return: The result json (status of the request, etc.)
        """

        result_json = {}
        result_json["Called_function"] = EndPoints.WAIT_FOR_REQUEST
        result_json = self.add_std_info(result_json)

        # Answer to PUT HTTP request
        if flask.request.method == 'GET':
            try:
                # Received : werkzeug.datastructures.FileStorage. Should use ".read()" to get picture's value
                tmp_id = flask.request.args.get('request_id')
                self.logger.debug(
                    f"Request ID to be checked if ready in server : {type(tmp_id)} ==> {tmp_id} ")  # {f.read()}

                # Fetch results
                # TODO : Special function for "cleaner/more performant" check ?
                _ = self.database_worker.get_request_result(
                    self.database_worker.cache_db_no_decode, tmp_id)

                result_json["Status"] = "Success"
                result_json["request_id"] = tmp_id
                result_json["is_ready"] = True
            except Exception as e:
                self.logger.error(
                    f"Normal error during GET handling ('is_ready' request) {e}")
                result_json["Status"] = "Failure"
                result_json["Error"] = "Error during database request"
                result_json["is_ready"] = False
        else:
            result_json = self.add_bad_method_info(
                result_json, good_method_instead="GET")

        return result_json
        # Test it with curl 127.0.0.1:443/is_ready

    def is_add_ready(self) -> Dict:
        """
        Handle a check of a add readiness
        :return: The result json (status of the request, etc.)
        """
        # TODO : Specify one id. For now, just check the "emptiness" of all pipelines

        return self.are_pipelines_empty()
        # Test it with curl 127.0.0.1:443/wait_for_add

    # ================= EXPORT AND DUMP =================

    def export_db_as_graphe(self) -> Dict:
        """
        Handle a dump of the database request
        :return: The result json (status of the request, etc.)
        """

        result_json = {}
        result_json["Called_function"] = EndPoints.REQUEST_DB
        result_json = self.add_std_info(result_json)

        # Answer to PUT HTTP request
        if flask.request.method == 'GET':
            try:
                # Request export of the database and save it as a json graph
                self.db_utils = db_utils.DBUtilities(
                    db_access_decode=self.database_worker.storage_db_decode, db_access_no_decode=self.database_worker.storage_db_no_decode)
                graph = self.db_utils.get_storage_graph()
                graph_dict = graph.export_as_dict()

                # Save to file
                json_import_export.save_json(
                    graph_dict, get_homedir() / "export_folder" / "db_graphe.json")

                result_json["Status"] = "Success"
                result_json["db"] = graph_dict
            except Exception as e:
                self.logger.error(f"Error during GET handling {e}")
                result_json["Status"] = "Failure"
                result_json["Error"] = "Error during db exportation to file"
        else:
            result_json = self.add_bad_method_info(
                result_json, good_method_instead="GET")

        return result_json
        # Test it with curl 127.0.0.1:443

    # ================= FLUSH =================

    def flush_databases(self) -> Dict:
        """
        Handle a flush of the database request
        :return: The result json (status of the request, etc.)
        """

        result_json = {}
        result_json["Called_function"] = EndPoints.FLUSH_DB
        result_json = self.add_std_info(result_json)

        # Answer to PUT HTTP request
        if flask.request.method == 'GET':
            try:
                self.db_startstop.flush_all_redis()
                result_json["Status"] = "Success"

            except Exception as e:
                self.logger.error(f"Error during GET handling {e}")
                result_json["Status"] = "Failure"
                result_json["Error"] = "Error during db exportation to file"
        else:
            result_json = self.add_bad_method_info(
                result_json, good_method_instead="GET")

        return result_json
        # Test it with curl 127.0.0.1:443

    # ================= UTILITIES =================

    @staticmethod
    def add_std_info(result_json: Dict) -> Dict:
        """
        Add standard information to the result_json
        :param result_json: The result json/dict to which to add standard values
        :return: the modified result_json
        """
        result_json["Call_method"] = flask.request.method  # 'GET' or 'POST' ...
        result_json["Call_time"] = time.ctime()  # 'GET' or 'POST' ...

        return result_json

    @staticmethod
    def add_bad_method_info(result_json: Dict, good_method_instead: str = None) -> Dict:
        """
        Add error values to the result_json if method is bad
        :param result_json: The result json/dict to which to add standard values
        :param good_method_instead: the method that should be used by the resquest
        :return: the modified result_json
        """
        result_json["Status"] = "Failure"

        # Construct a message depending on the good method to use
        if good_method_instead is None:
            result_json["Error"] = "BAD METHOD : use another method (GET, PUT, POST, ...)."

        elif good_method_instead == "POST":
            result_json["Error"] = "BAD METHOD : use POST instead of GET, PUT, ..."

        elif good_method_instead == "PUT":
            result_json["Error"] = "BAD METHOD : use PUT instead of GET, POST, ..."

        elif good_method_instead == "GET":
            result_json["Error"] = "BAD METHOD : use GET instead of POST, PUT, ..."

        return result_json

    def enqueue_and_save_picture(self, file: datastructures.FileStorage, result_json: Dict, queue: QueueNames) -> Dict:
        """
        Hash the picture, generate a BMP file, enqueue it, return the result_json with relevant values
        :param queue: Queue to add the picture
        :param file: the file provided by the client
        :param result_json: The result json/dict to which to add standard values
        :return: the modified result_json
        """
        # Received : werkzeug.datastructures.FileStorage. Should use ".read()" to get picture's value
        self.logger.debug(
            f"Image received in server : {type(file)} ")  # {f.read()}

        # Compute input picture hash and convert to BMP
        f_hash = id_generator.get_SHA1(file)
        f_bmp = id_generator.convert_to_bmp(file)  # Returns a bytes array
        self.logger.debug(
            f"Image transformed in BMP in server : {type(f_bmp)} ")  # {f_bmp}

        # Save received picture to disk
        picture_import_export.save_picture(f_bmp, get_homedir(
        ) / 'datasets' / 'received_pictures' / (str(f_hash) + '.bmp'))
        # If the filename need to be used : secure_filename(f.filename)

        # Generate uuid from SHA-1 : # Done : Create request UUID ? Or keep image hash ?
        tmp_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f_hash))

        # Enqueue picture to processing
        self.logger.debug(
            f"Adding to feature queue : {f_hash} hash transformed into -> {tmp_uuid} uuid v5")  # {f_bmp}
        self.database_worker.add_to_queue(self.database_worker.cache_db_decode,
                                          queue_name=queue,
                                          input_id=tmp_uuid,
                                          dict_to_store={"img": f_bmp})

        result_json["Status"] = "Success"
        result_json["id"] = tmp_uuid

        return result_json


# Launcher for this worker. Launch this file to launch a worker
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Launch Flask API on server side')
    parser = arg_parser.add_arg_db_conf(parser)
    parser = arg_parser.add_arg_ws_conf(parser)

    args = parser.parse_args()

    db_conf, _, _, ws_conf = arg_parser.parse_conf_files(args)

    # Create the Flask API and run it
    # Create Flask endpoint from configuration files
    api = FlaskAppWrapper('api', tmp_ws_conf=ws_conf, tmp_db_conf=db_conf)
    api.add_all_endpoints()

    # Run Flask API endpoint
    api.run()  # debug=True
