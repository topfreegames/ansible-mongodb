#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2014, George Miroshnykov <george.miroshnykov@gmail.com>
# (c) 2014, Olivier Perbellini <olivier.perbellini@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
module: mongodb_replica_set
version_added: "1.5"
short_description: Initiate, configure, add and remove members from MongoDB replica set
description:
   - 'Initiate, configure, add and remove members from MongoDB replica set.
     See: http://docs.mongodb.org/manual/reference/replica-configuration/'
options:
    login_user:
        description:
            - The username used to authenticate with
        required: false
        default: null
    login_password:
        description:
            - The password used to authenticate with
        required: false
        default: null
    login_host:
        description:
            - The host running the database
        required: false
        default: localhost
    login_port:
        description:
            - The port to connect to
        required: false
        default: 6379
    member:
        description:
            - The host[:port] to add/remove from a replica set.
        required: false
        default: null
    arbiter_only:
        description:
            - Should a new member be added as arbiter.
        required: false
        default: false
    build_indexes:
        description:
            - Determines whether the mongod builds indexes on this member.
              Do not set to false for instances that receive queries from clients.
        required: false
        default: true
    hidden:
        description:
            - When this value is true, the replica set hides this instance,
              and does not include the member in the output of db.isMaster()
              or isMaster.
              This prevents read operations (i.e. queries) from ever reaching
              this host by way of secondary read preference.
        required: false
        default: false
    priority:
        description:
            - Specify higher values to make a member more eligible to become
              primary, and lower values to make the member less eligible to
              become primary.
              Priorities are only used in comparison to each other.
              Members of the set will veto election requests from members
              when another eligible member has a higher priority value.
              Changing the balance of priority in a replica set will trigger
              an election.
        required: false
        default: 1.0
    slave_delay:
        description:
            - Describes the number of seconds "behind" the primary that this
              replica set member should "lag."
              Use this option to create delayed members, that maintain a copy
              of the data that reflects the state of the data set at some
              amount of time in the past, specified in seconds.
              Typically such delayed members help protect against human error,
              and provide some measure of insurance against the unforeseen
              consequences of changes and updates.
        required: false
        default: 0
    votes:
        description:
            - Controls the number of votes a server will cast in a
              replica set election.
              The number of votes each member has can be any non-negative integer,
              but it is highly recommended each member has 1 or 0 votes.
        required: false
        default: 1
    chainingAllowed:
        description:
            - When chainingAllowed is true, the replica set allows secondary
              members to replicate from other secondary members.
              When chainingAllowed is false, secondaries can replicate only
              from the primary.
        required: false
        default: true
    woption:
        description:
            - Provides the ability to disable write concern entirely as well as
              specify the write concern for replica sets.
        required: false
        default: 1
    joption:
        description:
            - Confirms that the mongod instance has written the data to the
              on-disk journal. This ensures that data is not lost if the mongod
              instance shuts down unexpectedly. Set to true to enable.
        required: false
        default: false
    wtimeout:
        description:
            - This option specifies a time limit, in milliseconds, for the write
            concern. wtimeout is only applicable for woption values greater than 1.
        required: false
        default: 0
    heartbeat:
        description:
            - Number of seconds that the replica set members wait for a successful
              heartbeat from each other. If a member does not respond in time,
              other members mark the delinquent member as inaccessible.
        required: false
        default: 10
    state:
        description:
            - The desired state of the replica set
        required: true
        default: null
        choices: [ "initiated", "reconf" "present", "absent" ]
notes:
    - See also M(mongodb_user)
requirements: [ pymongo ]
author: George Miroshnykov <george.miroshnykov@gmail.com>
'''

EXAMPLES = '''
# initiate a replica set
- mongodb_replica_set: state=initiated

# Reconfigure the settings of a replica set
- mongodb_replica_set: state=reconf woption:2 wtimeout:100 joption:true

# add a replica set member
- mongodb_replica_set: member=secondary.example.com state=present

# add an arbiter on custom port
- mongodb_replica_set: member=arbiter.example.com:30000 arbiter_only=yes state=present

# remove a replica set member
- mongodb_replica_set: member=secondary.example.com state=absent

# use all possible parameters when adding a member (please don't do that in production):
- mongodb_replica_set: >
    member=secondary.example.com
    state=present
    arbiter_only=yes
    build_indexes=no
    hidden=yes
    priority=0
    slave_delay=3600
    votes=42
'''

DEFAULT_PORT = 27017

import time
import random

pymongo_found = False
try:
    from pymongo.errors import ConnectionFailure
    from pymongo.errors import OperationFailure
    from pymongo.errors import AutoReconnect
    from pymongo import MongoClient
    pymongo_found = True
except ImportError:
    try:  # for older PyMongo 2.2
        from pymongo import Connection as MongoClient
        pymongo_found = True
    except ImportError:
        pass

def normalize_member_host(member_host):
    if ':' not in member_host:
        member_host = member_host + ':' + str(DEFAULT_PORT)
    return member_host

def create_member(host, **kwargs):
    member = dict(host = host)

    if kwargs['arbiter_only']:
        member['arbiterOnly'] = True

    if not kwargs['build_indexes']:
        member['buildIndexes'] = False

    if kwargs['hidden']:
        member['hidden'] = True

    if kwargs['priority'] != 1.0:
        member['priority'] = kwargs['priority']

    if kwargs['slave_delay'] != 0:
        member['slaveDelay'] = kwargs['slave_delay']

    if kwargs['votes'] != 1:
        member['votes'] = kwargs['votes']

    return member

def create_settings(**kwargs):
    settings = {}
    getLastErrorDefaults = {}

    if kwargs['chainingAllowed']:
        settings['chainingAllowed'] = kwargs['chainingAllowed']
    else:
        settings['chainingAllowed'] = True

    if kwargs['heartbeat']:
        settings['heartbeat'] = kwargs['heartbeat']
    else:
        settings['heartbeat'] = 10

    if kwargs['woption']:
        try:
            getLastErrorDefaults['w'] = int(kwargs['woption'])
        except ValueError:
            getLastErrorDefaults['w'] = kwargs['woption']
    else:
        getLastErrorDefaults['w'] = 1

    if kwargs['joption']:
        getLastErrorDefaults['j'] = kwargs['joption']
    else:
        getLastErrorDefaults['w'] = False

    if kwargs['wtimeout']:
        getLastErrorDefaults['wtimeout'] = kwargs['wtimeout']
    else:
        getLastErrorDefaults['wtimeout'] = 0

    settings['getLastErrorDefaults'] = getLastErrorDefaults

    return settings

def authenticate(client, login_user, login_password):
    # check if we should skip auth
    skip_auth = True
    try:
        client.database_names()
    except OperationFailure as e:
        skip_auth = False

    if (not skip_auth and login_user and login_password):
        client.admin.authenticate(login_user, login_password)

def rs_is_master(client):
    return client.local.command('isMaster')

def rs_get_config(client):
    return client.local.system.replset.find_one()

def rs_initiate(client, rs_config = None):
    if rs_config is None:
        client.admin.command('replSetInitiate')
    else:
        client.admin.command('replSetInitiate', rs_config)

def rs_get_member(rs_config, member):
    a = filter(lambda x: x['host'] == member, rs_config['members'])
    return a[0] if a else None

def rs_get_next_member_id(rs_config):
    if rs_config is None or rs_config['members'] is None:
        return 0

    def compare_max_id(max_id, current_member):
        id = int(current_member['_id'])
        return id if id > max_id else max_id

    max_id = reduce(compare_max_id, rs_config['members'], 0)
    return max_id + 1

def rs_add_member(rs_config, member):
    rs_config['members'].append(member)
    rs_config['version'] = rs_config['version'] + 1
    return rs_config

def rs_remove_member(rs_config, member):
    for i, candidate in enumerate(rs_config['members']):
        if candidate['host'] == member['host']:
            del rs_config['members'][i]
            break

    rs_config['version'] = rs_config['version'] + 1
    return rs_config

def rs_reconfigure(client, rs_config):
    try:
        client.admin.command('replSetReconfig', rs_config)
    except AutoReconnect:
        pass

def rs_wait_for_ok_and_primary(client, timeout = 60):
    while True:
        status = client.admin.command('replSetGetStatus', check=False)
        if status['ok'] == 1 and status['myState'] == 1:
            return

        timeout = timeout - 1
        if timeout == 0:
            raise Exception('reached timeout while waiting for rs.status() to become ok=1')

        time.sleep(1)

def rs_alter(client, member, state, tries):
    try:
        # get replica set config
        rs_config = rs_get_config(client)
        member['_id'] = rs_get_next_member_id(rs_config)

        if state == 'present':
            # check if given host is currently a member of replica set
            current_member = rs_get_member(rs_config, member['host'])
            if current_member is None:
                rs_config = rs_add_member(rs_config, member)
                rs_reconfigure(client, rs_config)
                return True
            else:
                return False
        elif state == 'absent':
            # check if given host is currently a member of replica set
            current_member = rs_get_member(rs_config, member['host'])
            if current_member:
                rs_config = rs_remove_member(rs_config, member)
                rs_reconfigure(client, rs_config)
                return True
            else:
                return False
    except OperationFailure as error:
        if error.code == 109:
            time.sleep(random.randint(2, 8))
        elif error.code == 103:
            pass
        else:
            raise OperationError(error)
        return rs_alter(client, member, state, tries+1)

def main():
    module = AnsibleModule(
        argument_spec = dict(
            login_host      = dict(default='localhost'),
            login_port      = dict(type='int', default=DEFAULT_PORT),
            login_user      = dict(default=None),
            login_password  = dict(default=None, no_log=True),
            replset         = dict(default=None),
            member          = dict(default=None),
            arbiter_only    = dict(type='bool', default='no'),
            build_indexes   = dict(type='bool', default='yes'),
            hidden          = dict(type='bool', default='no'),
            priority        = dict(default='1.0'),
            slave_delay     = dict(type='int', default='0'),
            votes           = dict(type='int', default='1'),
            state           = dict(required=True, choices=['initiated', 'reconf', 'present', 'absent']),
        )
    )

    if not pymongo_found:
        module.fail_json(msg='the python pymongo module is required')

    login_host      = module.params['login_host']
    login_port      = module.params['login_port']
    login_user      = module.params['login_user']
    login_password  = module.params['login_password']
    replset         = module.params['replset']
    member_host     = module.params['member']
    state           = module.params['state']

    if member_host is not None:
        member_host = normalize_member_host(member_host)

    member = create_member(
        host            = member_host,
        arbiter_only    = module.params['arbiter_only'],
        build_indexes   = module.params['build_indexes'],
        hidden          = module.params['hidden'],
        priority        = float(module.params['priority']),
        slave_delay     = module.params['slave_delay'],
        votes           = module.params['votes']
    )

    result = dict(changed=False)

    # connect
    client = None
    try:
        client = MongoClient(login_host, login_port)
    except ConnectionFailure as e:
        module.fail_json(msg='unable to connect to database: %s' % e)

    # authenticate
    if login_user and login_password:
        authenticate(client, login_user, login_password)

    if state == 'initiated':
        # initiate only if not configured yet
        is_master = rs_is_master(client)
        if 'setName' not in is_master:
            if member_host is None:
                rs_initiate(client)
            else:
                if replset is None:
                    module.fail_json(msg='replset must be specified when host is specified on state=initiated')
                rs_config = {
                    "_id": replset,
                    "members": [member]
                }
                rs_config['members'][0]['_id'] = 0
                rs_initiate(client, rs_config)
            rs_wait_for_ok_and_primary(client)
            result['changed'] = True
    else:
            result['changed'] = rs_alter(client, member, state, 0)

    module.exit_json(**result)

from ansible.module_utils.basic import *
main()
