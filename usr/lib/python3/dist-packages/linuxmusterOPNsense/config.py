import configparser
import os

# This class reads and provides configuration values for a given school (INI file).
class SchoolConfig:
    def __init__(self, school_name):
        if not isinstance(school_name, str) or not school_name:
            raise ValueError("School name must be a non-empty string.")
        if school_name.strip() != school_name:
            raise ValueError("School name must not contain leading/trailing whitespace.")
        if os.sep in school_name or (os.altsep and os.altsep in school_name):
            raise ValueError("School name must not contain path separators.")

        self.school_name = school_name
        config_file = f'/etc/linuxmuster/opnsense/{school_name}.ini'
        if not os.path.exists(config_file):
            # User-facing error in English:
            raise FileNotFoundError(f"School configuration file {config_file} was not found.")
        self.config = configparser.ConfigParser()
        self.config.read(config_file)

    @property
    def api_key(self):
        return self.config.get('opnsense', 'api_key')

    @property
    def api_secret(self):
        return self.config.get('opnsense', 'api_secret')

    @property
    def base_url(self):
        return self.config.get('opnsense', 'base_url', fallback='https://firewall/api')

    @property
    def verify_ssl(self):
        return self.config.getboolean('opnsense', 'verify_ssl', fallback=True)

    @property
    def ca_bundle(self):
        return self.config.get('opnsense', 'ca_bundle', fallback='')

    @property
    def school_name_conf(self):
        return self.config.get('school', 'name', fallback=self.school_name)

    @property
    def sync_roles(self):
        return self.config.getboolean('aliases', 'sync_roles', fallback=False)

    @property
    def roles_prefix(self):
        return self.config.get('aliases', 'roles_prefix', fallback='ROLE_')

    @property
    def sync_rooms(self):
        return self.config.getboolean('aliases', 'sync_rooms', fallback=False)

    @property
    def rooms_prefix(self):
        return self.config.get('aliases', 'rooms_prefix', fallback='ROOM_')

    @property
    def sync_hwgroups(self):
        return self.config.getboolean('aliases', 'sync_hwgroups', fallback=False)

    @property
    def hwgroups_prefix(self):
        return self.config.get('aliases', 'hwgroups_prefix', fallback='HWGROUP_')

    @property
    def voucher_provider(self):
        return self.config.get('voucher', 'provider', fallback='Voucher')
