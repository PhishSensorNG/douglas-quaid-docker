import logging
from typing import List

from common.environment_variable import JSON_parsable_Dict
from common.environment_variable import load_server_logging_conf_file

load_server_logging_conf_file()


class Default_scalability_conf(JSON_parsable_Dict):
    def __init__(self):
        self.logger = logging.getLogger(__name__)

        self.NB_PICS_TO_REQUEST = 10

        self.STARTING_NB_PICS_IN_DB = 5
        self.MULTIPLIER_LIST = [2, 5]
        self.LINEAR_INCREMENT = 20
        self.MAX_NB_PICS_TO_SEND = 100000
        self.MAX_NB_BOXES = 100  # Hard limit to generate boxes. No more than 100 points.

    def generate_boxes(self, max_nb_pictures: int) -> List[int]:
        """
        Generate a list of boxes size from a list of multiplier, a starting point and a maximum list of picture. From 10 000 and [2,5], and 5, generates [5,10,50,100,500, 1000 ...]
        :param max_nb_pictures: Maximum box size to reach
        :return: A List of integer
        """
        list_boxes = []
        curr_box = self.STARTING_NB_PICS_IN_DB

        i = 0
        box_reached_max = False

        while len(list_boxes) < self.MAX_NB_BOXES and not box_reached_max:
            # Multiply current box size per the current multiplier
            curr_box = self.MULTIPLIER_LIST[i] * curr_box

            list_boxes.append(curr_box)

            # If we went out of bound, stop
            if curr_box >= max_nb_pictures:
                box_reached_max = True

            # Get the next multiplier
            i = (i + 1) % len(self.MULTIPLIER_LIST)

        return list_boxes

    def generate_boxes_linear(self, max_nb_pictures: int) -> List[int]:
        """
        Generate a list of boxes size from an increment, a starting point and a maximum list of picture. From 10 000 and 20, and start at 5 generates [5,25,45,65 ...]
        :param max_nb_pictures: Maximum box size to reach
        :return: A List of integer
        """
        list_boxes = []
        curr_box = self.STARTING_NB_PICS_IN_DB

        box_reached_max = False

        while len(list_boxes) < self.MAX_NB_BOXES and not box_reached_max:
            # Multiply current box size per the current multiplier
            curr_box = self.LINEAR_INCREMENT * (len(list_boxes) + 1)

            list_boxes.append(curr_box)

            # If we went out of bound, stop
            if curr_box >= max_nb_pictures:
                box_reached_max = True

        return list_boxes

    # ==================== To string ====================

    # Overwrite to print the content of the cluster instead of the cluster memory address
    def __repr__(self):
        return self.get_str()

    def __str__(self):
        return self.get_str()

    def get_str(self):
        return ''.join(map(str, [' NB_PICS_TO_REQUEST=', self.NB_PICS_TO_REQUEST,
                                 ' STARTING_NB_PICS_IN_DB=', self.STARTING_NB_PICS_IN_DB,
                                 ' MULTIPLIER_LIST=', self.MULTIPLIER_LIST]))


def parse_from_dict(conf):
    tmp_conf = Default_scalability_conf()
    tmp_conf.__dict__.update(conf)
    # Or : tmp_conf.__dict__ = conf

    return tmp_conf
    # return namedtuple("Default_calibrator_conf", conf.keys())(*conf.values())
