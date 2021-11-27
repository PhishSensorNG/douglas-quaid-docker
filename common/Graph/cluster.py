#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict

from common.Graph import node
from common.environment_variable import load_server_logging_conf_file

load_server_logging_conf_file()


class Cluster(node.Node):
    """
    Handle a cluster of the graph
    """

    def __init__(self, label: str, tmp_id, image: str):
        super().__init__(label, tmp_id, image)

        # For clusters only
        self.members = set()
        self.group = ""

    def add_member_id(self, node_id):
        self.members.add(node_id)

    def get_nb_members(self):
        return len(self.members)

    def update_member_id(self, old_id, new_id):
        """
        Modify an id in the list of members. Replace old by new.
        :param old_id: Old id to replace
        :param new_id: New id to replace to
        :return: Nothing, change internal state of the object only.
        """

        if {old_id}.issubset(self.members):
            self.members.remove(old_id)
            self.members.add(new_id)

    # ==================== Request ====================

    def are_in_same_cluster(self, id_1, id_2):
        """
        Return True if both nodes id are in this cluster # TODO : make test !
        :param id_1: first id
        :param id_2: second id
        :return: boolean, True if both id are part of the cluster members
        """

        return {id_1, id_2}.issubset(self.members)

    # ==================== Export / Import ====================

    def export_as_dict(self):
        tmp_json = super().export_as_dict()
        tmp_json["members"] = sorted(list(self.members))  # Sorted to keep order, mainly for test purposes
        tmp_json["group"] = self.group

        return tmp_json

    @staticmethod
    def create_from_parent(parent: node.Node):
        return Cluster(label=parent.label, tmp_id=parent.id, image=parent.image)

    @staticmethod
    def load_from_dict(tmp_input: Dict):
        """
        Load/ Import a Cluster object from a dict
        :param tmp_input: A Dict version of the Cluster to import
        :return: The Cluster as an object
        """
        tmp_cluster = Cluster.create_from_parent(node.Node.load_from_dict(tmp_input))

        for m in tmp_input["members"]:
            tmp_cluster.add_member_id(m)

        tmp_cluster.group = tmp_input["group"]

        return tmp_cluster

    # ==================== To string ====================

    # Overwrite to print the content of the cluster instead of the cluster memory address
    def __repr__(self):
        return self.get_str()

    def __str__(self):
        return self.get_str()

    def get_str(self):
        return ''.join(map(str, [super().get_str(), ' members=', list(self.members), ' group=', self.group]))
