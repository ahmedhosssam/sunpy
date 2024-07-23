import copy
import json

import numpy as np
import pytest
from regions import SkyRegion

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time

from sunpy.net import Fido, attr, attrs, hek
from sunpy.net.hek.utils import COORD_FILE_PATH, UNIT_FILE_PATH


@pytest.fixture
def foostrwrap(request):
    return hek.attrs._StringParamAttrWrapper("foo")

@pytest.fixture
def read_unit_attributes():
    with open(UNIT_FILE_PATH) as unit_file:
        unit_properties = json.load(unit_file)
    return unit_properties

@pytest.fixture
def read_coord_attributes():
    with open(COORD_FILE_PATH) as coord_file:
        coord_properties = json.load(coord_file)

    return coord_properties

class HEKResult:
    """
    Basic caching class to run the remote query once and return the result many times.
    """

    def __init__(self):
        self._result = None

    def get_result(self):
        if self._result is None:
            startTime = '2011/08/09 07:23:56'
            endTime = '2011/08/09 12:40:29'
            eventType = 'FL'
            hekTime = attrs.Time(startTime, endTime)
            hekEvent = attrs.hek.EventType(eventType)
            h = hek.HEKClient()
            hek_query = h.search(hekTime, hekEvent)
            self._result = hek_query

        return copy.deepcopy(self._result)


_hek_result = HEKResult()


@pytest.fixture
def hek_result():
    return _hek_result.get_result()


def test_eventtype_collide():
    with pytest.raises(TypeError):
        attrs.hek.AR & attrs.hek.CE
    with pytest.raises(TypeError):
        (attrs.hek.AR & attrs.Time((2011, 1, 1),
                                   (2011, 1, 2))) & attrs.hek.CE
    with pytest.raises(TypeError):
        (attrs.hek.AR | attrs.Time((2011, 1, 1),
                                   (2011, 1, 2))) & attrs.hek.CE


def test_eventtype_or():
    assert (attrs.hek.AR | attrs.hek.CE).item == "ar,ce"


def test_HEKAttr():
    res = hek.attrs.walker.create(hek.attrs.HEKAttr("foo", "=", "bar"), {})
    assert len(res) == 1
    assert res[0] == {'value0': 'bar', 'operator0': '=', 'param0': 'foo'}


def test_stringwrapper_eq(foostrwrap):
    res = hek.attrs.walker.create(foostrwrap == "bar", {})
    assert len(res) == 1
    assert res[0] == {'value0': 'bar', 'operator0': '=', 'param0': 'foo'}


def test_stringwrapper_lt(foostrwrap):
    res = hek.attrs.walker.create(foostrwrap < "bar", {})
    assert len(res) == 1
    assert res[0] == {'value0': 'bar', 'operator0': '<', 'param0': 'foo'}


def test_stringwrapper_gt(foostrwrap):
    res = hek.attrs.walker.create(foostrwrap > "bar", {})
    assert len(res) == 1
    assert res[0] == {'value0': 'bar', 'operator0': '>', 'param0': 'foo'}


def test_stringwrapper_le(foostrwrap):
    res = hek.attrs.walker.create(foostrwrap <= "bar", {})
    assert len(res) == 1
    assert res[0] == {'value0': 'bar', 'operator0': '<=', 'param0': 'foo'}


def test_stringwrapper_ge(foostrwrap):
    res = hek.attrs.walker.create(foostrwrap >= "bar", {})
    assert len(res) == 1
    assert res[0] == {'value0': 'bar', 'operator0': '>=', 'param0': 'foo'}


def test_stringwrapper_ne(foostrwrap):
    res = hek.attrs.walker.create(foostrwrap != "bar", {})
    assert len(res) == 1
    assert res[0] == {'value0': 'bar', 'operator0': '!=', 'param0': 'foo'}


def test_stringwrapper_like(foostrwrap):
    res = hek.attrs.walker.create(foostrwrap.like("bar"), {})
    assert len(res) == 1
    assert res[0] == {'value0': 'bar', 'operator0': 'like', 'param0': 'foo'}


def test_err_dummyattr_create():
    with pytest.raises(TypeError):
        hek.attrs.walker.create(attr.DummyAttr(), {})


def test_err_dummyattr_apply():
    with pytest.raises(TypeError):
        hek.attrs.walker.apply(attr.DummyAttr(), {})


@pytest.mark.remote_data
def test_hek_client(hek_result):
    assert isinstance(hek_result, hek.hek.HEKTable)


@pytest.mark.remote_data
def test_hek_empty_search_result():
    startTime = '1985-05-04 00:00:00'
    endTime = '1985-05-04 00:00:00'
    eventType = 'FL'

    hekTime = attrs.Time(startTime, endTime)
    hekEvent = attrs.hek.EventType(eventType)

    h = hek.HEKClient()
    hek_query = h.search(hekTime, hekEvent)
    assert isinstance(hek_query, hek.hek.HEKTable)
    assert len(hek_query) == 0


@pytest.mark.remote_data
def test_getitem(hek_result):
    assert hek_result.__getitem__(0) == hek_result[0]


@pytest.mark.remote_data
def test_get_voevent(hek_result):
    ve = hek_result[0].get_voevent()
    assert len(ve['voe:VOEvent']) == 7


@pytest.mark.remote_data
def test_hek_time_col(hek_result):
    assert isinstance(hek_result[0]['event_starttime'], Time)
    assert isinstance(hek_result[0]['event_endtime'], Time)


@pytest.mark.remote_data
def test_vso_time(hek_result):
    ve = hek_result[0].vso_time
    assert isinstance(ve, attrs.Time)


@pytest.mark.remote_data
def test_vso_instrument(hek_result):
    vc = hek_result[1].vso_instrument
    assert isinstance(vc, attrs.Instrument)


@pytest.mark.remote_data
def test_HEKRow_get(hek_result):
    assert hek_result[0]['event_peaktime'] == hek_result[0].get('event_peaktime')
    assert hek_result[0].get('') is None


@pytest.mark.remote_data
def test_mixed_results_get():
    # To check that the following bug is fixed:
    # https://github.com/sunpy/sunpy/issues/3238
    client = hek.HEKClient()
    result = client.search(attrs.Time('2013/02/01 00:00:00', '2013/02/01 23:30:00'),
                           attrs.hek.FRM.Name == 'SPoCA')
    assert isinstance(result, hek.hek.HEKTable)
    assert len(result) == 89
    assert result[0]["SOL_standard"] == 'SOL2013-01-31T20:13:31L253C063'


@pytest.mark.remote_data
def test_mixed_results_get_2():
    # To check that the following bug is fixed:
    # # https://github.com/sunpy/sunpy/issues/3898
    client = hek.HEKClient()
    result = client.search(attrs.Time('2011/08/09 07:23:56', '2011/08/09 12:40:29'),
                           attrs.hek.EventType("FL"))
    assert isinstance(result, hek.hek.HEKTable)
    assert len(result) == 19
    assert result[0]["SOL_standard"] == 'SOL2011-08-08T01:30:04L247C075'


@pytest.mark.remote_data
def test_mixed_results_get_angstrom():
    # To check that the following bug is fixed:
    # https://github.com/sunpy/sunpy/issues/4087
    client = hek.HEKClient()
    tstart = '2014/10/24 20:50'
    tend = '2014/10/25 00:14'
    event_type = 'FL'
    result = client.search(attrs.Time(tstart, tend), attrs.hek.EventType(event_type))
    assert len(result) == 13
    assert result[0]["SOL_standard"] == 'SOL2014-10-24T20:53:46L247C106'


@pytest.mark.remote_data
def test_query_multiple_operators():
    event_type = "FL"
    tstart = "2013/10/28"
    tend = "2013/10/29"
    client = hek.HEKClient()
    results = client.search(attrs.Time(tstart, tend),
                            attrs.hek.EventType(event_type),
                            attrs.hek.FL.GOESCls > "M1.0",
                            attrs.hek.OBS.Observatory == "GOES")
    assert len(results) == 7

@pytest.mark.remote_data
def test_astropy_unit_parsing(read_unit_attributes, read_coord_attributes):
    client = hek.HEKClient()
    tstart = '2014/10/24 20:50'
    tend = '2014/10/25 00:14'
    event_type = 'FL'
    result = client.search(attrs.Time(tstart, tend), attrs.hek.EventType(event_type))
    unit_properties = read_unit_attributes
    coord_properties = read_coord_attributes
    unit_attributes_with_unit = [ prop for prop in unit_properties["attributes"] if prop.get("unit_prop",None) is not None]
    coord_attributes_with_unit = [prop for prop in coord_properties["attributes"] if not prop.get("is_chaincode", False) and not prop.get("is_unit_prop",False)]

    for attribute in unit_attributes_with_unit + coord_attributes_with_unit:
        if attribute["name"] in result.colnames:
            assert all([value in ['', None] or isinstance(value, u.Quantity) for value in result[attribute['name']]])


@pytest.mark.remote_data
def test_chaincode_parsing(read_coord_attributes):
    client = hek.HEKClient()
    tstart = '2014/10/24 20:50'
    tend = '2014/10/25 00:14'
    event_type = 'FL'
    result = client.search(attrs.Time(tstart, tend), attrs.hek.EventType(event_type))
    coord_properties = read_coord_attributes
    chaincode_properties = [prop for prop in coord_properties["attributes"] if prop.get("is_chaincode", False)]

    for attribute in chaincode_properties:
        if attribute["name"] in result.colnames:
            assert all([value in ['', None] or isinstance(value, SkyRegion) for value in result[attribute['name']]])

@pytest.mark.remote_data
def test_missing_times():
    # Check for https://github.com/sunpy/sunpy/pull/7627#issuecomment-2113451964
    client = hek.HEKClient()
    results = client.search(attrs.Time('2024-05-10', '2024-05-12'), attrs.hek.AR.NOAANum == 13664)
    assert isinstance(results["event_peaktime"][0], np.ma.core.MaskedConstant)
    assert results["event_peaktime"][6].isot == "2024-05-10T16:08:00.000"

@pytest.mark.remote_data
def test_merging_event_coords():
    tstart = '2011/08/09 07:23:56'
    tend = '2011/08/09 12:40:29'
    client = hek.HEKClient()
    result = client.search(attrs.Time(tstart,tend), attrs.hek.EventType('CH'))

    coord1 = -2.91584*u.arcsec
    coord2 = 940.667*u.arcsec
    time='2011-08-09 06:00:08.000'
    frame='helioprojective'
    event_coord = SkyCoord(coord1, coord2, obstime=time, frame=frame)

    assert result['event_coord'][0] == event_coord

@pytest.mark.remote_data
def test_obs_meanwavel():
    tstart = '2011/08/09 07:23:56'
    tend = '2011/08/09 12:40:29'
    client = hek.HEKClient()
    result = client.search(attrs.Time(tstart,tend), attrs.hek.EventType('CH'))

    value = 193.0*u.angstrom
    assert result['obs_meanwavel'][0] == value

@pytest.mark.remote_data
def test_parse_times():
    tstart = '2011/08/09 07:23:56'
    tend = '2011/08/09 12:40:29'
    client = hek.HEKClient()
    result = client.search(attrs.Time(tstart,tend), attrs.hek.EventType('CH'))

    for idx in range(len(result)):
        assert isinstance(result['event_starttime'][idx], Time)
        assert isinstance(result['event_endtime'][idx], Time)

@pytest.mark.remote_data
def test_ssw_latest_events_flares():
    tstart = '2011/08/09 07:23:56'
    tend = '2011/08/09 12:40:29'
    event_type = 'FL'
    result = Fido.search(attrs.Time(tstart,tend), attrs.hek.EventType(event_type), attrs.hek.FRM.Name == 'SSW Latest Events')
    assert len(result[0]) == 2

@pytest.mark.remote_data
def test_not_ssw_latest_events_flares():
    tstart = '2011/08/09 07:23:56'
    tend = '2011/08/09 12:40:29'
    event_type = 'FL'
    result = Fido.search(attrs.Time(tstart,tend), attrs.hek.EventType(event_type), attrs.hek.FRM.Name != 'SSW Latest Events')
    assert len(result[0]) == 19

@pytest.mark.remote_data
def test_flares_peak_flux():
    tstart = '2011/08/09 07:23:56'
    tend = '2011/08/09 12:40:29'
    event_type = 'FL'
    result = Fido.search(attrs.Time(tstart,tend), attrs.hek.EventType(event_type), attrs.hek.FL.PeakFlux > 4000.0)
    assert len(result[0]) == 1

@pytest.mark.remote_data
def test_flares_peak_flux_and_position():
    tstart = '2011/08/09 07:23:56'
    tend = '2011/08/09 12:40:29'
    event_type = 'FL'
    result = Fido.search(attrs.Time(tstart,tend), attrs.hek.EventType(event_type), attrs.hek.Event.Coord1 > 800, attrs.hek.FL.PeakFlux > 1000)
    assert len(result[0]) == 7

@pytest.mark.remote_data
def test_flares_python_logical_ops():
    tstart = '2011/08/09 07:23:56'
    tend = '2011/08/09 12:40:29'
    event_type = 'FL'
    result = Fido.search(attrs.Time(tstart,tend), attrs.hek.EventType(event_type), (attrs.hek.Event.Coord1 > 50) and (attrs.hek.FL.PeakFlux > 1000))
    assert len(result[0]) == 7
