"""
Facilities to interface with the Heliophysics Events Knowledgebase.
"""
import json
import codecs
import urllib
import inspect
from itertools import chain
import re
from pathlib import Path
import os

import astropy.table
from astropy.table import Row
from astropy import units as u
from astropy.coordinates import SkyCoord

import sunpy.net._attrs as core_attrs
from sunpy import log
from sunpy.net import attr
from sunpy.net.base_client import BaseClient, QueryResponseTable
from sunpy.net.hek import attrs
from sunpy.time import parse_time
from sunpy.util import dict_keys_same, unique
from sunpy.util.xml import xml_to_dict
from sunpy import __file__

__all__ = ['HEKClient', 'HEKTable', 'HEKRow']

DEFAULT_URL = 'https://www.lmsal.com/hek/her?'
UNIT_FILE_PATH = Path(os.path.dirname(__file__)) / "net" / "hek"/ "unit_properties.json"
COORD_FILE_PATH = Path(os.path.dirname(__file__)) / "net" / "hek"/ "coord_properties.json"

u.add_enabled_aliases({"steradian": u.sr, "arcseconds": u.arcsec, "degrees": u.deg, "sec": u.s})

def _freeze(obj):
    """ Create hashable representation of result dict. """
    if isinstance(obj, dict):
        return tuple((k, _freeze(v)) for k, v in obj.items())
    if isinstance(obj, list):
        return tuple(_freeze(elem) for elem in obj)
    return obj


class HEKClient(BaseClient):
    """
    Provides access to the Heliophysics Event Knowledgebase (HEK).

    The HEK stores solar feature and event data generated by algorithms and
    human observers.
    """
    # FIXME: Expose fields in .attrs with the right types
    # that is, not all StringParamWrapper!

    default = {
        'cosec': '2',  # Return .json
        'cmd': 'search',
        'type': 'column',
        'event_type': '**',
    }
    # Default to full disk.
    attrs.walker.apply(attrs.SpatialRegion(), {}, default)

    def __init__(self, url=DEFAULT_URL):
        self.url = url

    def _download(self, data):
        """ Download all data, even if paginated. """
        page = 1
        results = []
        new_data = data.copy()
        # Override the default name of the operatorX, where X is a number.
        for key in data.keys():
            if "operator" in key:
                new_data[f"op{key.split('operator')[-1]}"] = new_data.pop(key)
        while True:
            new_data['page'] = page
            url = self.url + urllib.parse.urlencode(new_data)
            log.debug(f'Opening {url}')
            fd = urllib.request.urlopen(url)
            try:
                result = codecs.decode(fd.read(), encoding='utf-8', errors='replace')
                result = json.loads(result)
            except Exception as e:
                raise OSError("Failed to load return from the HEKClient.") from e
            finally:
                fd.close()
            results.extend(result['result'])
            if not result['overmax']:
                if len(results) > 0:
                    table = astropy.table.Table(dict_keys_same(results))
                    table = self._parse_times(table)
                    table = self._parse_values_to_quantities(table)
                    return table
                else:
                    return astropy.table.Table()
            page += 1

    @staticmethod
    def _parse_times(table):
        # All time columns from https://www.lmsal.com/hek/VOEvent_Spec.html
        time_keys = ['event_endtime', 'event_starttime', 'event_peaktime']
        for tkey in time_keys:
            if tkey in table.colnames and not any(time == "" for time in table[tkey]):
                table[tkey] = parse_time(table[tkey])
                table[tkey].format = 'iso'
        return table

    @staticmethod
    def _parse_unit(table, attribute, is_coord_prop = False):
        unit_attr=""
        if is_coord_prop:
            unit_attr = "event_coordunit"
        else:
            unit_attr = attribute["unit_prop"]
        for row in table:
            if unit_attr in table.colnames and row[unit_attr] not in ["", None] and table[attribute["name"]].unit is not None:
                table[attribute["name"]].unit = HEKClient._get_unit(attribute, row[unit_attr], is_coord_prop= is_coord_prop)
                break
        return table

    @staticmethod
    def _parse_astropy_unit(str):
        try:
            unit = u.Unit(str)
        except ValueError:
            try:
                unit = u.Unit(str.lower())
            except ValueError:
                unit = u.Unit(str.capitalize())

        return unit

    @staticmethod
    def _get_unit(attribute, str, is_coord_prop = False):
        if is_coord_prop:
            coord1_unit, coord2_unit, coord3_unit = None, None, None
            coord_units = re.split(r'[, ]', str)
            if len(coord_units) == 1: # deg
               coord1_unit = coord2_unit = HEKClient._parse_astropy_unit(coord_units[0])
            elif len(coord_units) == 2:
                coord1_unit = HEKClient._parse_astropy_unit(coord_units[0])
                coord2_unit = HEKClient._parse_astropy_unit(coord_units[1])
            else:
                coord1_unit = HEKClient._parse_astropy_unit(coord_units[0])
                coord2_unit = HEKClient._parse_astropy_unit(coord_units[1])
                coord3_unit = HEKClient._parse_astropy_unit(coord_units[2])
            return locals()[attribute["unit_prop"]]
        else:
            return HEKClient._parse_astropy_unit(str)

    @staticmethod
    def _parse_chaincode(table, attribute):
        pass

    @staticmethod
    def _parse_colums_to_table(table, attributes, is_coord_prop = False):
        for attribute in attributes:
            if attribute["is_unit_prop"]:
                pass
            elif attribute["name"] in table.colnames and "unit_prop" in attribute:
                table = HEKClient._parse_unit(table, attribute, is_coord_prop)
                unit_attr = ""
                if is_coord_prop:
                    if attribute["is_chaincode"]:
                        pass
                    unit_attr = "event_coordunit"
                else:
                    unit_attr = attribute["unit_prop"]

                new_column = []
                for idx, value in enumerate(table[attribute["name"]]):
                    if value in ["", None]:
                        new_column.append(value)
                    else:
                        new_column.append(value * HEKClient._get_unit(attribute, table[unit_attr][idx], is_coord_prop= is_coord_prop))
                table[attribute["name"]] = new_column
        for attribute in attributes:
            if attribute["is_unit_prop"] and attribute["name"] in table.colnames:
                del table[attribute["name"]]
        return table

    @staticmethod
    def _parse_values_to_quantities(table):
        with open(UNIT_FILE_PATH, 'r') as unit_file:
            unit_properties = json.load(unit_file)
        unit_attributes = unit_properties["attributes"]

        with open(COORD_FILE_PATH, 'r') as coord_file:
            coord_properties = json.load(coord_file)
        coord_attributes = coord_properties["attributes"]
        table = HEKClient._parse_colums_to_table(table, unit_attributes)
        table = HEKClient._parse_colums_to_table(table, coord_attributes, is_coord_prop= True)
        return table



    def search(self, *args, **kwargs):
        """
        Retrieves information about HEK records matching the criteria
        given in the query expression. If multiple arguments are passed,
        they are connected with AND. The result of a query is a list of
        unique HEK Response objects that fulfill the criteria.

        Examples
        -------
        >>> from sunpy.net import attrs as a, Fido
        >>> timerange = a.Time('2011/08/09 07:23:56', '2011/08/09 12:40:29')
        >>> res = Fido.search(timerange, a.hek.FL, a.hek.FRM.Name == "SWPC")  # doctest: +REMOTE_DATA
        >>> res  # doctest: +SKIP
        <sunpy.net.fido_factory.UnifiedResponse object at ...>
        Results from 1 Provider:
        <BLANKLINE>
        2 Results from the HEKClient:
                 SOL_standard          active ... skel_startc2 sum_overlap_scores
        ------------------------------ ------ ... ------------ ------------------
        SOL2011-08-09T07:19:00L227C090   true ...         None                  0
        SOL2011-08-09T07:48:00L296C073   true ...         None                  0
        <BLANKLINE>
        <BLANKLINE>
        """
        query = attr.and_(*args)
        data = attrs.walker.create(query, {})
        ndata = []
        for elem in data:
            new = self.default.copy()
            new.update(elem)
            ndata.append(new)

        # ndata = self._parse_values_to_quantities(ndata)

        if len(ndata) == 1:
            return HEKTable(self._download(ndata[0]), client=self)
        else:
            return HEKTable(self._merge(self._download(data) for data in ndata), client=self)

    def _merge(self, responses):
        """ Merge responses, removing duplicates. """
        return list(unique(chain.from_iterable(responses), _freeze))

    def fetch(self, *args, **kwargs):
        """
        This is a no operation function as this client does not download data.
        """
        return NotImplemented

    @classmethod
    def _attrs_module(cls):
        return 'hek', 'sunpy.net.hek.attrs'

    @classmethod
    def _can_handle_query(cls, *query):
        required = {core_attrs.Time}
        optional = {i[1] for i in inspect.getmembers(attrs, inspect.isclass)} - required
        qr = tuple(x for x in query if not isinstance(x, attrs.EventType))
        return cls.check_attr_types_in_query(qr, required, optional)


class HEKRow(Row):
    """
    Handles the response from the HEK. Each HEKRow object is a subclass
    of `~astropy.table.Row`. The column-row key-value pairs correspond to the
    HEK feature/event properties and their values, for that record from the
    HEK.  Each HEKRow object also has extra properties that relate HEK
    concepts to VSO concepts.
    """
    @property
    def vso_time(self):
        return core_attrs.Time(
            self['event_starttime'],
            self['event_endtime']
        )

    @property
    def vso_instrument(self):
        if self['obs_instrument'] == 'HEK':
            raise ValueError("No instrument contained.")
        return core_attrs.Instrument(self['obs_instrument'])

    @property
    def vso_all(self):
        return attr.and_(self.vso_time, self.vso_instrument)

    def get_voevent(self, as_dict=True,
                    base_url="http://www.lmsal.com/hek/her?"):
        """Retrieves the VOEvent object associated with a given event and
        returns it as either a Python dictionary or an XML string."""

        # Build URL
        params = {
            "cmd": "export-voevent",
            "cosec": 1,
            "ivorn": self['kb_archivid']
        }
        url = base_url + urllib.parse.urlencode(params)

        # Query and read response
        response = urllib.request.urlopen(url).read()

        # Return a string or dict
        if as_dict:
            return xml_to_dict(response)
        else:
            return response

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


class HEKTable(QueryResponseTable):
    """
    A container for data returned from HEK searches.
    """
    Row = HEKRow
