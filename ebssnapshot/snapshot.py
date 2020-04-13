import backoff
import boto3
import collections
import getpass
import logging
import multiprocessing
import os
import placebo
import json
import signal
import socket
import sys
import uuid

import metadata

from botocore.exceptions import ClientError
from botocore.client import Config
from datetime import datetime, timedelta
from dateutil.tz import tzutc
from multiprocessing import Process, JoinableQueue


#
# Logger
#
class Filter(logging.Filter):
    def filter(self, record):
        """
        Render as a json string
        """
        if isinstance(record.msg, collections.OrderedDict) or isinstance(record.msg, dict) or isinstance(record.msg, list):
            msg = "uuid={uuid} action={action} result={result} json='{msg}'".format(msg=json.dumps(record.msg), **record.msg)
            record.msg = msg

        allow = True
        return allow


def getLogger(name):
    """
    Logging setup
    :return:
    """
    logger = logging.getLogger(name)
    logger.addFilter(Filter())
    return logger


#
# Base classes
#

class EC2Connection:
    def __init__(self, region=None, identifier=None, retries=4, role=None, connecttimeout=5, readtimeout=3600):
        """
        :param region: AWS Region
        :type region: basestring
        :param identifier: Universally Unique Identifier. Automatically generated if not supplied.
        :type identifier: basestring
        :param retries: The number of retries. Defaults to 4
        :type identifier: int
        :param role: The IAM role ARN to assume. Ignored if not specified
        :type identifier: basestring
        :param connecttimeout: Boto3 connection timeout
        :type connecttimeout: int
        :param readtimeout: Boto3 read timeout
        :type readtimeout: int
        """
        self.connecttimeout = connecttimeout
        self.region = region
        self.readtimeout = readtimeout
        self.uuid = identifier or str(uuid.uuid1())
        self._retries = retries
        self._recorder = None
        self._ec2 = None
        self._sess = None
        self._config = None
        self._caller_identity = None
        self._config = self.config()
        self.role = role
        self.logger = getLogger('ebssnapshot.EC2Connection')

    def config(self, config=None):
        """
        AWS config
        :param config:
        :return:
        """
        if config:
            self._config = config
        elif not self._config:
            self._config = Config(connect_timeout=self.connecttimeout, read_timeout=self.readtimeout)

        return self._config

    def connection(self, conn=None):
        """
        Connect or reuse a connection

        :param conn: Set optional connection object
        :type conn: boto.core.EC2
        :return: EC2 client
        :rtype: boto3.EC2
        """
        if conn:
            self._ec2 = conn

        if not self._ec2:
            sess = self.session()
            try:
                self._ec2 = sess.client('ec2', region_name=self.region, config=self._config)

            except Exception as msg:
                self.logger.exception(msg)

        return self._ec2

    def aws_identity(self):
        """
        AWS Identity. Used mostly for logging Account number and UserId

        :rtype: dict
        :return:
        """
        if not self._caller_identity:
            self._caller_identity = self._sess.client('sts').get_caller_identity()
        return self._caller_identity

    def session(self, sess=None):
        """
        Create or reuse a session

        :param sess: Set optional session object
        :type sess: boto3.session.Session
        :return: Session
        :rtype: boto3.session.Session
        """
        if sess:
            self._sess = sess

        if not self._sess:
            try:
                if self.role is not None:
                    client = boto3.client('sts', region_name=self.region)

                    rsp = client.assume_role(
                        RoleArn=self.role,
                        RoleSessionName='EBSSnapshot-' + self.region)

                    creds = rsp['Credentials']
                    self._sess = boto3.session.Session(
                        region_name=self.region,
                        aws_access_key_id=creds['AccessKeyId'],
                        aws_secret_access_key=creds['SecretAccessKey'],
                        aws_session_token=creds['SessionToken'])

                else:
                    self._sess = boto3.session.Session()
            except Exception as msg:
                self.logger.exception(str(msg))

        self.aws_identity()
        return self._sess

    def record(self, directory):
        """
        Use Placebo to record the session

        :param directory:
        :return:
        """
        if not os.path.exists(directory):
            os.makedirs(directory)
        self._recorder = placebo.attach(self.session(), data_path=directory)
        self._recorder.record()


#
# Application
#

# Has to be declared before use in the @backoff.on_exception decorator
def giveup(client_error):
    """
    Backoff giveup utility to detect unhandled AWS error codes

    :type client_error: ClientError
    :rtype: bool
    """
    error_code = client_error.response.get('Error', {}).get('Code', 'Unknown')
    return error_code != 'RequestLimitExceeded'


class EBSSnapshot(EC2Connection):
    def __init__(self, region=None, desc=None, workers=4, identifier=None, retries=4, role=None, connecttimeout=5, readtimeout=3600):
        """
        EBS snapshot class. E.G.

        ebssnap = EBSSnapshot(region='ap-southeast-1')
        ebssnap.run()

        :param region: Name of aws region
        :param desc: Text describing function. Used for logging and creates a AWS tag against the snapshot.
        :param workers: Number of process/thread workers to initiate
        :param role: role ARN to assume
        :param connecttimeout: Connection timeout
        :type connecttimeout: int
        :param readtimeout: Read timeout
        :type readtimeout: int
        """
        EC2Connection.__init__(self, region=region, identifier=identifier, retries=retries, role=role, connecttimeout=connecttimeout, readtimeout=readtimeout)
        self.description = desc or 'EBSSnapshot script'
        self.workers = workers
        self.logger = getLogger('ebssnapshot.EBSSnapshot')

    def volumes(self, filters=None, PageSize=10000):
        """
        List volumes

        :param filters: List of AWS snapshot filters
        :type filters: list
        :param PageSize: Paginate size
        :type PageSize: int
        :rtype: generator
        """
        ec2 = self.connection()
        paginator = ec2.get_paginator('describe_volumes')

        results = None
        if filters:
            results = paginator.paginate(Filters=filters, PaginationConfig={'PageSize': PageSize})
        else:
            results = paginator.paginate(PaginationConfig={'PageSize': PageSize})

        for result in results:
            for volume in result['Volumes']:
                yield volume

    def snapshots(self, filters=None, PageSize=10000):
        """
        List snapshots

        :param filters: List of AWS snapshot filters
        :type filters: list
        :param PageSize: Paginate size
        :type PageSize: int
        :rtype: generator
        """
        ec2 = self.connection()
        paginator = ec2.get_paginator('describe_snapshots')

        results = None
        if filters:
            results = paginator.paginate(Filters=filters, PaginationConfig={'PageSize': PageSize})
        else:
            results = paginator.paginate(PaginationConfig={'PageSize': PageSize})

        for result in results:
            for snapshot in result['Snapshots']:
                yield snapshot

    def create_snapshot_boss(self, filters=None):
        """
        Run the worker pool to create snapshots across multiple processes/threads

        :param filters: List of AWS filters
        :type filters: list
        """

        def worker(workerid, jobqueue, region=None, desc=None, uuid=None, role=None, sess=None):
            """
            :param workerid: Worker ID
            :type workerid: int
            :param jobqueue: Multi Producer and Consumer Queue
            :type jobqueue: JoinableQueue
            :param region: AWS region
            :type region: basestring
            :param desc: Descriptive text used to log
            :param role: role ARN to assume
            :type desc: basestring
            """
            ebs = EBSSnapshot(desc=desc, region=region, identifier=uuid, role=role)
            ebs.session(sess)
            while ebs:
                volume = jobqueue.get()
                try:
                    ebs.create_snapshot(volume)
                except Exception as msg:
                    logging.fatal('Failed to create snapshot: {}'.format(str(msg)))
                    raise

                jobqueue.task_done()

        boss(self, worker, self.volumes(filters=filters))

    def create_snapshot(self, volume):
        """
        Create an EBS Snapshot

        :param volume: Individual record as yielded by `py:function:: EBSSnapshot.volumes`
        :type volume: dict
        """
        log = collections.OrderedDict()
        log['action'] = 'create_snapshot'
        log['uuid'] = self.uuid
        log['VolumeId'] = volume['VolumeId']
        log['AvailabilityZone'] = volume['AvailabilityZone']
        log['VolumeTags'] = taginfo(volume)

        # Add tags for identification
        tag_specifications = [
            {
                'ResourceType': 'snapshot',
                'Tags': [
                    {'Key': 'backup-desc', 'Value': self.description},
                    {'Key': 'backup-uuid', 'Value': self.uuid},
                    {'Key': 'backup-version', 'Value': metadata.__version__},
                    {'Key': 'backup-delete-protection', 'Value': 'false'},
                    {'Key': 'backup-host', 'Value': socket.getfqdn()},
                    {'Key': 'backup-user', 'Value': getpass.getuser()},
                    {'Key': 'backup-uid', 'Value': str(os.getuid())},
                    {'Key': 'backup-euid', 'Value': str(os.geteuid())},
                ]
            }
        ]
        for tag in volume.get('Tags', []):
            tag_specifications[0]['Tags'].append(tag)

        log['SnapshotTags'] = taginfo(tag_specifications[0])

        # Create Snapshot
        try:
            result = self._create_snapshot(volume, self.description, tag_specifications)

            log['StartTime'] = result['StartTime'].isoformat()
            log['SnapshotId'] = result['SnapshotId']
            log['Account'] = self.aws_identity()['Account']
            log['UserId'] = self.aws_identity()['UserId']
            log['result'] = "success"
            self.logger.info(log)
        except Exception as msg:
            log['error'] = str(msg)
            log['result'] = "error"
            self.logger.error(log)
            return

    def expire_snapshot_boss(self, filters=None, gt=None, lt=None):
        """
        Delete snapshots that have been expired.
        """

        def worker(workerid, jobqueue, region=None, desc=None, uuid=None, role=None, sess=None):
            """
            :param workerid: Worker ID
            :type workerid: int
            :param jobqueue: Multi Producer and Consumer Queue
            :type jobqueue: JoinableQueue
            :param region: AWS region
            :type region: basestring
            :param desc: Descriptive text used to create a tag and log
            :type desc: basestring
            """
            ebs = EBSSnapshot(desc=desc, region=region, identifier=uuid, role=role)
            ebs.session(sess)
            while ebs:
                snapshot = jobqueue.get()
                try:
                    # Filter out snapshots depending on tags
                    if ebs.filter_inlife_snapshot(snapshot, gt=gt, lt=lt):
                        jobqueue.task_done()
                        continue

                    ebs.expire_snapshot(snapshot)
                except Exception as msg:
                    logging.fatal('Failed to delete snapshot: {}'.format(str(msg)))
                    raise

                jobqueue.task_done()

        boss(self, worker, self.snapshots(filters=filters))

    @staticmethod
    def filter_inlife_snapshot(snapshot, gt=None, lt=None):
        """
        Filter any snapshots still considered in life

        :param snapshot: EBS snapshot metadata
        :type snapshot: dict
        :param gt: days from current date
        :type gt: int
        :param lt: days from current date
        :type lt: int
        :rtype:  bool
        """
        start_time = snapshot['StartTime']
        current_time = datetime.now(tz=tzutc())

        if gt and start_time > current_time + timedelta(days=gt):
            return True

        if lt and start_time < current_time + timedelta(days=lt):
            return True

        return False

    def expire_snapshot(self, snapshot):
        """
        :param snapshot: EBS snapshot metadata
        :type snapshot: dict
        """
        # Log Prep
        current_time = datetime.now(tzutc())
        start = snapshot['StartTime']
        age = (current_time - start).days

        log = collections.OrderedDict()
        log['action'] = 'expire_snapshot'
        log['status'] = 'incomplete'
        log['uuid'] = self.uuid
        log['region'] = self.region
        log['SnapshotId'] = snapshot['SnapshotId']
        log['Age'] = str(age)
        log['Account'] = self.aws_identity()['Account']
        log['UserId'] = self.aws_identity()['UserId']
        log['SnapshotTags'] = taginfo(snapshot)
        try:
            self._delete_snapshot(snapshot, log)

        except Exception as msg:
            log['error'] = str(msg)
            log['result'] = "error"
            self.logger.error(log)

    #
    # Retry handlers
    #
    @backoff.on_exception(backoff.expo, ClientError, max_tries=10, giveup=giveup)
    def _create_snapshot(self, volume, description, tag_specifications=None):
        ec2 = self.connection()
        return ec2.create_snapshot(Description=description, VolumeId=volume['VolumeId'], TagSpecifications=tag_specifications)

    @backoff.on_exception(backoff.expo, ClientError, max_tries=10, giveup=giveup)
    def _delete_snapshot(self, snapshot, log):
        ec2 = self.connection()
        try:
            ec2.delete_snapshot(SnapshotId=snapshot['SnapshotId'])
            log['status'] = 'completed'
            log['result'] = 'success'
            self.logger.info(log)
        except ClientError as client_error:
            error_code = client_error.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'InvalidSnapshot.InUse':
                log['status'] = 'skipped'
                log['AwsCode'] = error_code
                log['AwsMessage'] = client_error.message
                self.logger.info(log)
            else:
                raise


#
# Utilities
#
def boss(ebs, worker, iterable):
    """
    Boss Process

    :type ebs: EBSSnapshot
    :type worker: Callable
    :param iterable:
    :return:
    """
    logger = getLogger('ebssnapshot.boss')
    jobqueue = JoinableQueue(ebs.workers)
    procs = []
    for i in range(1, ebs.workers + 1):
        proc = Process(target=worker, args=[i, jobqueue, ebs.region, ebs.description, ebs.uuid, ebs.role, ebs.session()])
        proc.daemon = True
        proc.start()
        procs.append(proc)

    signal.signal(signal.SIGINT, terminate)
    signal.signal(signal.SIGTERM, terminate)

    for job in iterable:
        while True:
            running = any(p.is_alive() for p in procs)
            if not running:
                logger.fatal('No children are alive: Exiting')
                sys.exit(-1)

            if jobqueue.empty():
                jobqueue.put(job, block=True, timeout=60)
                break

    jobqueue.join()


def taginfo(dictobject):
    """
    Get tag information from AWS objects

    :param dictobject: Dictionary that has a object['Tags'] as an array of dictionaries.
    :type dictobject: dict
    :return: Key=Value pairs
    :rtype: basestring
    """
    tags = dictobject.get('Tags', [])
    tag_info = collections.OrderedDict()
    for tag in sorted(tags, key=lambda thistag: thistag['Key']):
        tag_info[tag['Key']] = tag['Value']
    return tag_info


def terminate(signal, frame):
    """
    Terminate running children
    """
    logger = getLogger('ebssnapshot.terminate_children')
    logger.info("Received signal {signal}. Terminating".format(**locals()))
    for p in multiprocessing.active_children():
        p.terminate()

    sys.exit(0)
