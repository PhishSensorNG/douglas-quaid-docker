import pathlib

from common.environment_variable import get_homedir, JSON_parsable_Dict


class Default_webservice_conf(JSON_parsable_Dict):
    def __init__(self):
        # Please note that CERT and KEY files must be in carl-hauser/carlhauser_server (where the flask server is)
        self.CERT_FILE: pathlib.Path = get_homedir() / 'carlhauser_server' / 'cert.pem'  # './cert.pem'
        self.KEY_FILE: pathlib.Path = get_homedir() / 'carlhauser_server' / 'key.pem'  # './key.pem'

        self.ip = '127.0.0.1'
        self.port = 5000


def parse_from_dict(conf):
    tmp_conf = Default_webservice_conf()
    tmp_conf.__dict__.update(conf)
    # Or : tmp_conf.__dict__ = conf

    return tmp_conf
    # return namedtuple("Default_webservice_conf", conf.keys())(*conf.values())


'''
# ==================== To string ====================

    # Overwrite to print the content of the cluster instead of the cluster memory address
    def __repr__(self):
        return self.get_str()

    def __str__(self):
        return self.get_str()

    def get_str(self):
        return ''.join(map(str, [' \nCERT_FILE=', self.CERT_FILE,
                                 ' \nKEY_FILE=', self.KEY_FILE]))
'''
