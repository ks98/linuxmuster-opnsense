import re
import hashlib
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

# OPNsense alias names may only contain [a-zA-Z0-9_] and are limited to 32
# characters. Source names (e.g. sophomorix roles like
# "classroom-studentcomputer") often contain hyphens or other characters that
# OPNsense rejects, so they must be sanitized before use.
_ALIAS_INVALID_CHARS = re.compile(r'[^a-zA-Z0-9_]')
ALIAS_MAX_LENGTH = 32


def sanitize_alias_name(name, max_length=ALIAS_MAX_LENGTH):
    """
    Converts an arbitrary name into a valid OPNsense alias name: disallowed
    characters become '_'. If the result exceeds max_length it is shortened
    deterministically and a short hash suffix is appended, so that distinct
    long names never collide (important when a per-school prefix pushes an
    alias name over the 32 character limit).
    """
    sanitized = _ALIAS_INVALID_CHARS.sub('_', str(name))
    if len(sanitized) <= max_length:
        return sanitized
    digest = hashlib.sha1(sanitized.encode('utf-8')).hexdigest()[:6]
    keep = max_length - len(digest) - 1  # room for '_' + digest
    return f"{sanitized[:keep]}_{digest}"


def alias_owner_tag(school):
    """Machine-readable owner marker embedded in an alias description so that
    aliases managed for one school are never silently overwritten by another."""
    return f"[linuxmuster-opnsense school={school}]"


_ALIAS_OWNER_RE = re.compile(r"\[linuxmuster-opnsense school=([^\]]+)\]")


def alias_owner_of(description):
    """Returns the owning school parsed from an alias description, or None if
    the description carries no linuxmuster-opnsense owner marker."""
    match = _ALIAS_OWNER_RE.match(description or "")
    return match.group(1) if match else None


class OPNsenseAPIError(Exception):
    """Raised when the OPNsense API reports a logical failure (HTTP 200 but
    result == 'failed', e.g. a validation error)."""


class AliasOwnershipConflict(Exception):
    """Raised when an alias already exists and is owned by a different school,
    so overwriting it would destroy that school's data."""

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
        elif method.lower() == 'put':
            r = requests.put(url, headers=headers, auth=auth, verify=self.verify, json=data, timeout=self.timeout)
        elif method.lower() == 'delete':
            r = requests.delete(url, headers=headers, auth=auth, verify=self.verify, json=data, timeout=self.timeout)
        else:
            raise ValueError("Unsupported HTTP method")

        if r.status_code not in (200, 201):
            r.raise_for_status()

        try:
            result = r.json() if r.text else {}
        except json.JSONDecodeError:
            return {}

        # OPNsense frequently answers logical failures (e.g. validation errors on
        # addItem/setItem) with HTTP 200 and {"result": "failed", ...}. A pure
        # status-code check would treat these as success, so inspect the body.
        if isinstance(result, dict) and result.get("result") == "failed":
            raise OPNsenseAPIError(
                f"OPNsense API reported failure for {method.upper()} {endpoint}: "
                f"{result.get('validations', result)}"
            )

        return result

    def apply_alias_changes(self):
        """
        Sends a single 'reconfigure' request so that pending alias changes take
        effect. Call this once after a batch of create/update/delete operations
        instead of reconfiguring after every single alias.
        """
        self._request("post", "firewall/alias/reconfigure", data={})

    def create_or_update_alias(self, alias_name, ip_list, school=None, kind=None, apply=True):
        """
        Creates or updates an OPNsense alias with a given list of IP addresses.

        When 'school' is given, the alias description is stamped with an owner
        marker and an existing alias owned by a *different* school is never
        overwritten (AliasOwnershipConflict is raised instead). This makes it
        safe to sync several schools onto one firewall.

        When apply is True (default) a 'reconfigure' request is sent afterwards
        to apply the change immediately. Pass apply=False when updating many
        aliases in a loop and call apply_alias_changes() once at the end.
        """
        # OPNsense rejects names with characters outside [a-zA-Z0-9_] (HTTP 200 +
        # result=failed), so sanitize before both lookup and write.
        alias_name = sanitize_alias_name(alias_name)

        # Check if alias already exists
        safe_alias_name = self._encode_path_segment(alias_name)
        uuid_data = self._request("get", f"firewall/alias/getAliasUUID/{safe_alias_name}")

        # If the alias exists, the API might return {"uuid": "..."}
        # If it does not exist, the response is typically an empty list or dict
        if isinstance(uuid_data, dict) and 'uuid' in uuid_data:
            uuid = uuid_data['uuid']
        else:
            uuid = None

        if school is not None:
            description = f"{alias_owner_tag(school)} {kind or 'alias'}: {alias_name}"
        else:
            description = f"Alias for {alias_name}"

        alias_data = {
            "enabled": "1",
            "name": alias_name,
            "type": "host",
            # Join IPs with newline
            "content": "\n".join(ip_list),
            "description": description
        }

        if uuid:
            # Before overwriting, make sure this alias isn't owned by another
            # school (which would silently destroy that school's IP list).
            if school is not None:
                existing = self._request("get", f"firewall/alias/getItem/{uuid}")
                existing_desc = ""
                if isinstance(existing, dict) and isinstance(existing.get("alias"), dict):
                    existing_desc = existing["alias"].get("description", "") or ""
                owner = alias_owner_of(existing_desc)
                if owner is not None and owner != school:
                    raise AliasOwnershipConflict(
                        f"Alias '{alias_name}' is owned by school '{owner}', not "
                        f"'{school}' - skipped. Use a distinct school_prefix per school."
                    )
            # Alias exists -> update
            self._request("post", f"firewall/alias/setItem/{uuid}", data={"alias": alias_data})
        else:
            # Alias does not exist -> create
            self._request("post", "firewall/alias/addItem", data={"alias": alias_data})

        if apply:
            self.apply_alias_changes()

    def delete_alias(self, alias_name, apply=True):
        """
        Deletes an existing alias by name. Returns True if alias was found and deleted,
        otherwise False.
        """
        alias_name = sanitize_alias_name(alias_name)
        safe_alias_name = self._encode_path_segment(alias_name)
        uuid_data = self._request("get", f"firewall/alias/getAliasUUID/{safe_alias_name}")
        # getAliasUUID returns a list (not a dict) when the alias does not exist,
        # so guard against calling .get() on a non-dict.
        uuid = uuid_data.get('uuid') if isinstance(uuid_data, dict) else None
        if uuid:
            self._request("post", f"firewall/alias/delItem/{uuid}")
            if apply:
                self.apply_alias_changes()
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
