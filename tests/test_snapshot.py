from botocore.exceptions import ClientError
from datetime import timedelta
from dateutil.tz import tzutc
from ebssnapshot import snapshot

import boto3
import datetime
import ebssnapshot
import placebo
import faker
import multiprocessing
import os
import pytest
import random
import shortuuid


#
# Variables
#
ROOT = os.path.dirname(os.path.abspath(__file__))
PLACEBO_PATH = os.path.join(ROOT, 'fixtures', 'placebo_responses')


#
# Helper Classes
#
class Placebo:
    def __init__(self, region_name, data_path, service_name=None):
        self._session = None
        self.placebo = None
        self._client = None
        self._service_name = service_name
        self._region_name = region_name
        self._data_path = data_path
        self._recorder = None

    def start(self):
        if self._makeroot and not os.path.exists(self._data_path):
            os.makedirs(self._data_path)

        Placebo.start(self).record()
        return self._recorder

    @property
    def session(self):
        if not self._session:
            self._session = boto3.Session()

        return self._session

    @property
    def client(self):
        if not self._client and self._service_name:
            self.start()
            self._client = self.session.client(self._service_name, region_name=self._region_name)

        return self._client

    def start(self, recorderobj=None):
        if not self._recorder:
            self._recorder = recorderobj or placebo.attach(self.session, data_path=self._data_path)
        return self._recorder


class Playback(object, Placebo):
    def __init__(self, region_name, data_path, service_name=None):
        Placebo.__init__(self, region_name, data_path, service_name)

    def start(self):
        Placebo.start(self).playback()
        return self._recorder


#
# Utilities
#
def multiprocess_reaper():
    for p in multiprocessing.active_children():
        p.terminate()


#
# Fake classes
#


class FakePagenator():
    def __init__(self, group):
        """
        :param group: Volumes | Snapshots
        :type group: basestring
        """
        self.group = group

    def paginate(self, *args, **kwargs):
        sets = range(0, random.randrange(3, 5))

        results = []
        for _ in sets:
            pageobject = []
            for i in range(1, random.randrange(3, 5)):
                obj = None
                if self.group == 'Volumes':
                    pageobject.append(fixture_vol())
                elif self.group == 'Snapshots':
                    pageobject.append(fixture_snap())
            results.append({self.group: pageobject})

        return results


class FakeConnection():
    def __init__(self, paginatorobj):
        self.paginatorobj = paginatorobj or None

    def get_paginator(self, paginator):
        return self.paginatorobj


#
# Fixtures
#
fake = faker.Faker()


def fixture_tags():
    tags = [
        {'Key': 'OS', 'Value': fake.linux_platform_token()},
        {'Key': 'UserAgent', 'Value': fake.user_agent()},
        {'Key': 'CreatedBy', 'Value': fake.name()}
    ]
    return tags


def fixture_snap(Description=None, Encrypted=False, OwnerId=None, Progress=None, SnapshotId=None, StartTime=None,
                 Tags=None, VolumeId=None):
    snap = {
        'Description': Description if Description else 'Created by ebssnapshot-1.1.0',
        'Encrypted': Encrypted if Encrypted else False,
        'OwnerId': OwnerId if OwnerId else str(random.randint(100000000, 900000000)),
        'Progress': Progress if Progress else str(random.randint(0, 100)) + '%',
        'SnapshotId': SnapshotId if SnapshotId else 'snap-' + str(shortuuid.uuid()),
        'StartTime': StartTime if StartTime else datetime.datetime.now(tz=tzutc()),
        'VolumeId': VolumeId if VolumeId else 'vol-' + str(shortuuid.uuid())
    }

    if Tags:
        snap['Tags'] = Tags

    return snap


def fixture_attachment(AttachTime=None, Device=None, InstanceId=None, State=None, VolumeId=None,
                       DeleteOnTermination=False):
    attachment = {
        'AttachTime': AttachTime if AttachTime else datetime.datetime.now(tz=tzutc()),
        'Device': Device if Device else fake.unix_partition(),
        'InstanceId': InstanceId if InstanceId else 'i-' + str(shortuuid.uuid()),
        'State': State if State else random.choice(['attached']),
        'VolumeId': VolumeId if VolumeId else 'vol-' + str(shortuuid.uuid()),
        'DeleteOnTermination': DeleteOnTermination if DeleteOnTermination else fake.pybool()
    }
    return attachment


def fixture_vol(Attachments=None, AvailabilityZone=None, CreateTime=None, Encrypted=None, Size=None, SnapshotId=None,
                State=None, VolumeId=None, VolumeType=None, Tags=None):
    vol = {
        'AvailabilityZone': AvailabilityZone if AvailabilityZone else fixture_azs(),
        'Attachments': Attachments if Attachments else [fixture_attachment()],
        'CreateTime': CreateTime if CreateTime else datetime.datetime.now(tz=tzutc()),
        'Encrypted': Encrypted if Encrypted else fake.pybool(),
        'Size': Size if Size else str(random.randint(1, 1000)),
        'SnapshotId': SnapshotId if SnapshotId else 'snap-' + str(shortuuid.uuid()),
        'State': State if State else random.choice(['in-use']),
        'VolumeId': VolumeId if VolumeId else 'vol-' + str(shortuuid.uuid()),
        'VolumeType': VolumeType if VolumeType else 'standard'
    }

    if Tags:
        vol['Tags'] = Tags

    return vol


def fixture_regions():
    regions = [
        'ap-northeast-1', 'ap-northeast-2', 'ap-south-1', 'ap-southeast-1', 'ap-southeast-2', 'cn-north-1',
        'eu-central-1', 'eu-west-1', 'sa-east-1', 'us-east-1', 'us-west-1', 'us-west-2'
    ]

    return random.choice(regions)


def fixture_azs():
    regions = [
        'ap-northeast-1a', 'ap-northeast-1c', 'ap-south-1a', 'ap-south-1b', 'ap-southeast-1a', 'ap-southeast-1b',
        'ap-southeast-2a', 'ap-southeast-2b', 'ap-southeast-2c', 'eu-central-1a', 'eu-central-1b', 'eu-west-1a',
        'eu-west-1b', 'eu-west-1c', 'sa-east-1a', 'sa-east-1b', 'sa-east-1c', 'us-east-1a', 'us-east-1b', 'us-east-1c',
        'us-east-1d', 'us-west-1a', 'us-west-1b', 'us-west-2a', 'us-west-2b', 'us-west-2c'
    ]

    return random.choice(regions)


#
# Tests
#

def test_config():
    snap = snapshot.EBSSnapshot('no-region-1')
    obj = snap.config()

    assert (str(obj).startswith('<botocore.config.Config'))


def test_config_arg():
    class Fake():
        pass

    snap = snapshot.EBSSnapshot('no-region-1')
    obj = snap.config(config=Fake())
    assert (isinstance(obj, Fake))


def test_session(caplog):
    playback = Playback(region_name='no-region-1', data_path=PLACEBO_PATH + '/session')
    sess = playback.session
    playback.start()

    snap = snapshot.EBSSnapshot(role='arn:aws:iam::123456789:role/EBSSnapshot', region='no-region-1')
    obj = snap.session(sess)
    for record in caplog.records:
        assert record.levelname != 'ERROR'


def test_connection():

    snap = snapshot.EBSSnapshot(region='no-region-1')
    playback = Playback(region_name='no-region-1', data_path=os.path.join(PLACEBO_PATH, 'session'))
    playback.start()

    snap.session(playback.session)
    obj = snap.connection()
    assert (str(obj).startswith('<botocore.client.EC2'))


def test_connection_exception():
    playback = Playback(region_name='no-region-1', data_path=os.path.join(PLACEBO_PATH, 'session'))
    playback.start()

    snap = snapshot.EBSSnapshot(region='no-region-1')
    snap.session(playback.session)

    try:
        snap.connection()
    except Exception:
        pytest.fail("Unhandled exception")


def test_connection_arg():
    class Fake:
        def __init__(self):
            pass

    snap = snapshot.EBSSnapshot(region='no-region-1')
    obj = snap.connection(conn=Fake())
    assert (isinstance(obj, Fake))


def test_create_snapshot(caplog):
    playback = Playback(region_name='no-region-1', data_path=PLACEBO_PATH + '/create_snapshot')
    sess = playback.session
    playback.start()
    try:
        obj = snapshot.EBSSnapshot(region='no-region-1')
        obj.session(sess)
        obj.create_snapshot(fixture_vol(Tags=fixture_tags()))
    except Exception as ex:
        pytest.fail('Unhandle exception')

    for record in caplog.records:
        assert record.levelname != 'ERROR'


def test_create_snapshot_boss():
    playback = Playback(region_name='no-region-1', data_path=PLACEBO_PATH + '/create_snapshots')
    sess = playback.session
    playback.start()

    ebs = ebssnapshot.EBSSnapshot(region='no-region-1', identifier=shortuuid.uuid())
    ebs.session(sess)
    ebs.create_snapshot_boss()
    multiprocess_reaper()


def test_expire_snapshot_boss():
    playback = Playback(region_name='no-region-1', data_path=PLACEBO_PATH + '/expire_snapshots')
    sess = playback.session
    playback.start()

    ebs = ebssnapshot.EBSSnapshot(region='no-region-1', identifier=shortuuid.uuid())
    ebs.session(sess)
    ebs.expire_snapshot_boss()
    multiprocess_reaper()


def test_expire_snapshot_boss_lt():
    playback = Playback(region_name='no-region-1', data_path=PLACEBO_PATH + '/expire_snapshots')
    sess = playback.session
    playback.start()

    ebs = ebssnapshot.EBSSnapshot(region='no-region-1', identifier=shortuuid.uuid())
    ebs.session(sess)
    ebs.expire_snapshot_boss(lt=0)
    multiprocess_reaper()


def test_expire_snapshot_boss_gt():
    playback = Playback(region_name='no-region-1', data_path=PLACEBO_PATH + '/expire_snapshots')
    sess = playback.session
    playback.start()

    ebs = ebssnapshot.EBSSnapshot(region='no-region-1', identifier=shortuuid.uuid())
    ebs.session(sess)
    ebs.expire_snapshot_boss(gt=0)
    multiprocess_reaper()


def test_snapshots_list():
    fakepaginator = FakePagenator(group='Snapshots')
    fakeconnection = FakeConnection(paginatorobj=fakepaginator)

    ec2 = snapshot.EBSSnapshot(region='no-region-1')
    ec2.connection(fakeconnection)
    try:
        for snap in ec2.snapshots():
            print(snap)
    except Exception:
        pytest.fail()


def test_filter_inlife_snapshot_gt():
    date = datetime.datetime.now(tz=tzutc())
    date = date + timedelta(days=-2)
    snap = fixture_snap(StartTime=date, Tags=fixture_tags())
    ec2 = snapshot.EBSSnapshot(region='no-region-1')
    assert ec2.filter_inlife_snapshot(snap, gt=-3)


def test_filter_inlife_snapshot_gt_fail():
    date = datetime.datetime.now(tz=tzutc())
    date = date + timedelta(days=-2)
    snap = fixture_snap(StartTime=date, Tags=fixture_tags())
    ec2 = snapshot.EBSSnapshot('no-region-1')
    assert not ec2.filter_inlife_snapshot(snap, gt=-1)


def test_filter_inlife_snapshot_lt():
    date = datetime.datetime.now(tz=tzutc())
    date = date + timedelta(days=-2)
    snap = fixture_snap(StartTime=date)
    ec2 = snapshot.EBSSnapshot('no-region-1')
    assert ec2.filter_inlife_snapshot(snap, lt=-1)


def test_filter_inlife_snapshot_lt_fail():
    date = datetime.datetime.now(tz=tzutc())
    date = date + timedelta(days=-2)
    snap = fixture_snap(StartTime=date)
    ec2 = snapshot.EBSSnapshot('no-region-1')
    assert not ec2.filter_inlife_snapshot(snap, lt=-3)


def test_snapshots_list_filters():
    fakepaginator = FakePagenator(group='Snapshots')
    fakeconnection = FakeConnection(paginatorobj=fakepaginator)

    ec2 = snapshot.EBSSnapshot('no-region-1')
    ec2.connection(fakeconnection)
    try:
        for snap in ec2.snapshots(filters={'Tag': 'blah'}):
            print(snap)
    except Exception:
        pytest.fail()


def test_volumes_list():
    fakepaginator = FakePagenator(group='Volumes')
    fakeconnection = FakeConnection(paginatorobj=fakepaginator)

    ec2 = snapshot.EBSSnapshot('no-region-1')
    ec2.connection(fakeconnection)
    try:
        for vol in ec2.volumes():
            print(vol)
    except Exception:
        pytest.fail()


def test_volumes_list_filters():
    fakepaginator = FakePagenator(group='Volumes')
    fakeconnection = FakeConnection(paginatorobj=fakepaginator)

    ec2 = snapshot.EBSSnapshot('no-region-1')
    ec2.connection(fakeconnection)
    try:
        for vol in ec2.volumes(filters={'Tag': 'blah'}):
            print(vol)
    except Exception:
        pytest.fail()


def test_giveup_limit_exceeded():
    code = 'RequestLimitExceeded'
    operation_name = 'DeleteSnapshot'
    client_error = ClientError(error_response={'Error': {'Code': code}}, operation_name=operation_name)
    assert not snapshot.giveup(client_error)


def test_taginfo():
    obj = {'Tags': [
        {'Key': 'Name', 'Value': 'stack - host'},
        {'Key': 'Device', 'Value': '/dev/sdf'}
    ]}

    hashost = False
    hasstack = False
    for value in snapshot.taginfo(obj).values():
        if '/dev/sdf' in value:
            hashost = True

        if 'stack - host' in value:
            hasstack = True

    if not hasstack:
        pytest.fail('Missing stack information from tag')

    if not hashost:
        pytest.fail('Missing host information from tag')
