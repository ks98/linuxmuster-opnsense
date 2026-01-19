import requests
import json
from .config import SchoolConfig
from urllib.parse import quote
import warnings

try:
    from urllib3.exceptions import SubjectAltNameWarning
except ImportError:
    SubjectAltNameWarning = None

# Temporary workaround until this is fixed in linuxmuster-base
if SubjectAltNameWarning is not None:
    warnings.filterwarnings("ignore", category=SubjectAltNameWarning)

DEFAULT_TIMEOUT = (5, 30)

class LinuxmusterOPNsenseAPI:
    """
    This class provides methods to interact with the OPNsense API, based on
    the configuration from SchoolConfig.
    """
    def __init__(self, school_name='default-school'):
        # Initialize configuration
        self.school_config = SchoolConfig(school_name)

        self.base_url = self.school_config.base_url

        # Determine SSL verification mode (file path or boolean)
        if self.school_config.ca_bundle:
            self.verify = self.school_config.ca_bundle
        else:
            self.verify = self.school_config.verify_ssl

        self.timeout = DEFAULT_TIMEOUT

        self.api_key = self.school_config.api_key
        self.api_secret = self.school_config.api_secret

    def _encode_path_segment(self, value):
        return quote(str(value), safe="")

    def _request(self, method, endpoint, data=None, params=None):
        """
        Internal helper method for sending requests to the OPNsense API.
        It automatically sets the appropriate headers and handles status code checks.
        """
        url = f"{self.base_url}/{endpoint}"
        auth = (self.api_key, self.api_secret)

        headers = {}
        if method.lower() in ('post', 'put', 'delete'):
            headers["Content-Type"] = "application/json"

        if method.lower() == 'get':
            r = requests.get(url, auth=auth, verify=self.verify, params=params, timeout=self.timeout)
        elif method.lower() == 'post':
            r = requests.post(url, headers=headers, auth=auth, verify=self.verify, json=data, timeout=self.timeout)
        elif method.lower() == 'delete':
            r = requests.delete(url, headers=headers, auth=auth, verify=self.verify, json=data, timeout=self.timeout)
        else:
            raise ValueError("Unsupported HTTP method")

        if r.status_code not in (200, 201):
            r.raise_for_status()

        try:
            return r.json() if r.text else {}
        except json.JSONDecodeError:
            return {}

    def create_or_update_alias(self, alias_name, ip_list):
        """
        Creates or updates an OPNsense alias with a given list of IP addresses. 
        After creation or update, a 'reconfigure' request is sent to apply changes.
        """
        # Check if alias already exists
        safe_alias_name = self._encode_path_segment(alias_name)
        uuid_data = self._request("get", f"firewall/alias/getAliasUUID/{safe_alias_name}")

        # If the alias exists, the API might return {"uuid": "..."}
        # If it does not exist, the response is typically an empty list or dict
        if isinstance(uuid_data, dict) and 'uuid' in uuid_data:
            uuid = uuid_data['uuid']
        else:
            uuid = None

        alias_data = {
            "enabled": "1",
            "name": alias_name,
            "type": "host",
            # Join IPs with newline
            "content": "\n".join(ip_list),
            "description": f"Alias for {alias_name}"
        }

        if uuid:
            # Alias exists -> update
            self._request("post", f"firewall/alias/setItem/{uuid}", data={"alias": alias_data})
        else:
            # Alias does not exist -> create
            self._request("post", "firewall/alias/addItem", data={"alias": alias_data})

        # Reconfigure to apply changes
        self._request("post", "firewall/alias/reconfigure", data={})

    def delete_alias(self, alias_name):
        """
        Deletes an existing alias by name. Returns True if alias was found and deleted,
        otherwise False.
        """
        safe_alias_name = self._encode_path_segment(alias_name)
        uuid_data = self._request("get", f"firewall/alias/getAliasUUID/{safe_alias_name}")
        uuid = uuid_data.get('uuid', None)
        if uuid:
            self._request("post", f"firewall/alias/delItem/{uuid}")
            self._request("post", "firewall/alias/reconfigure")
            return True
        return False

    def search_captive_sessions(self, current=1, rowCount=-1, sort=None, searchPhrase="", selected_zones=None):
        """
        Sends a POST request to /api/captiveportal/session/search/ to list
        Captive Portal sessions.
        """
        if sort is None:
            sort = {}
        if selected_zones is None:
            selected_zones = []

        data = {
            "current": current,
            "rowCount": rowCount,
            "sort": sort,
            "searchPhrase": searchPhrase,
            "selected_zones": selected_zones
        }

        return self._request("post", "captiveportal/session/search/", data=data)

    def disconnect_captive_session(self, session_id):
        """
        Sends a POST request to /api/captiveportal/session/disconnect to end
        a session by its sessionId.
        """
        data = {"sessionId": session_id}
        return self._request("post", "captiveportal/session/disconnect", data=data)

    def list_voucher_groups(self):
        """
        Retrieves all voucher groups for the configured provider (see config).
        Corresponds to GET /api/captiveportal/voucher/listVoucherGroups/<provider>
        Returns a list of group names, e.g. ["test", "test2", ...].
        """
        provider = self._encode_path_segment(self.school_config.voucher_provider)
        endpoint = f"captiveportal/voucher/listVoucherGroups/{provider}"
        return self._request("get", endpoint)

    def list_vouchers_in_group(self, group):
        """
        Lists all vouchers in a specific group.
        GET /api/captiveportal/voucher/listVouchers/<provider>/<group>/
        Returns a list of dictionaries with voucher info.
        """
        provider = self._encode_path_segment(self.school_config.voucher_provider)
        safe_group = self._encode_path_segment(group)
        endpoint = f"captiveportal/voucher/listVouchers/{provider}/{safe_group}/"
        return self._request("get", endpoint)

    def create_vouchers(self, group, validity_seconds, expiry_seconds, count=1):
        """
        Creates new vouchers in a specific group.
        POST /api/captiveportal/voucher/generateVouchers/<provider>/
        Returns a list of dictionaries with newly created voucher data.
        """
        provider = self._encode_path_segment(self.school_config.voucher_provider)
        endpoint = f"captiveportal/voucher/generateVouchers/{provider}/"
        data = {
            "count": str(count),
            "validity": str(validity_seconds),
            "expirytime": str(expiry_seconds),
            "vouchergroup": group
        }
        return self._request("post", endpoint, data=data)

    def expire_voucher(self, username):
        """
        Expires (invalidates) a single voucher by username.
        POST /api/captiveportal/voucher/expireVoucher/<provider>/
        """
        provider = self._encode_path_segment(self.school_config.voucher_provider)
        endpoint = f"captiveportal/voucher/expireVoucher/{provider}/"
        data = {"username": username}
        return self._request("post", endpoint, data=data)

    def drop_expired_vouchers(self, group):
        """
        Drops (removes) all expired vouchers in a group.
        POST /api/captiveportal/voucher/dropExpiredVouchers/<provider>/<group>/
        """
        provider = self._encode_path_segment(self.school_config.voucher_provider)
        safe_group = self._encode_path_segment(group)
        endpoint = f"captiveportal/voucher/dropExpiredVouchers/{provider}/{safe_group}/"
        data = {}
        return self._request("post", endpoint, data=data)

    def drop_voucher_group(self, group):
        """
        Drops (removes) an entire voucher group, including all vouchers within.
        POST /api/captiveportal/voucher/dropVoucherGroup/<provider>/<group>/
        """
        provider = self._encode_path_segment(self.school_config.voucher_provider)
        safe_group = self._encode_path_segment(group)
        endpoint = f"captiveportal/voucher/dropVoucherGroup/{provider}/{safe_group}/"
        data = {}
        return self._request("post", endpoint, data=data)
