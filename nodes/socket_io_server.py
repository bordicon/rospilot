#!/usr/bin/env python
'''
Copyright 2012 Christopher Berner

This file is part of Rospilot.

Rospilot is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Rospilot is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Rospilot.  If not, see <http://www.gnu.org/licenses/>.
'''

import roslib; roslib.load_manifest('rospilot')
import rospilot
import rospy
import rospilot.msg
import json
import threading
import os

from pymavlink import mavutil
from gevent import monkey; monkey.patch_all()
from socketio import socketio_manage
from socketio.server import SocketIOServer
from socketio.namespace import BaseNamespace
from socketio.mixins import RoomsMixin, BroadcastMixin
from optparse import OptionParser

class RosPilotNamespace(BaseNamespace, RoomsMixin, BroadcastMixin):
    '''
    NOTE: Don't know if we actually want to case this data.
    QUESTION: Can we request data?
    '''
    def __init__(self):
        self.lock         = threading.Lock()
        self.armed        = 'false'
        self.gps          = {}
        self.pub_set_mode = rospy.Publisher('set_mode', rospilot.msg.BasicMode)
        rospy.Subscriber(
            "basic_status", rospilot.msg.BasicMode, self.handle_status)
        rospy.Subscriber("gpsraw", rospilot.msg.GPSRaw, self.handle_gps)

    def handle_status(self, data):
        with self.lock:
            self.armed = data.armed
            self.broadcast_event('armed_status', data.armed)

    def handle_gps(self, data):
        with self.lock:
            self.gps = data
            self.broadcast_event('gps', data)

    def send_arm(self, arm):
        self.pub_set_mode.publish(arm)

    def on_translation(self, msg):
        '''
          Debugging helper
        '''
        with self.lock:
            self.gps['lat'] = msg['lat']
            self.gps['lon'] = msg['lon']
            self.broadcast_event('gps', data)

    def on_arm(self, arm_reason):
        self.drone.send_arm('true')
        self.broadcast_event('announcement', 'armed')

    def on_disarm(self, arm_reason):
        self.drone.send_arm('false')
        self.broadcast_event('announcement', 'disarmed')

    def recv_disconnect(self):
        self.broadcast_event('announcement', 'client has disconnected')
        self.disconnect(silent=True)

class RosPilotIO(object):
    def __init__(self):
        # NOTE don't know who uses this buffer. It was included from example.
        self.buffer   = []
        self.env_vars = {}

    def __call__(self, environ, start_response):
        path = environ['PATH_INFO'].strip('/')

        # Assets are served by web_ui cherrypy process
        # This node is only responsible for socket communication
        # For additional namespaces parse request.
        # NOTE: create drone singleton or node
        if path.startswith("socket.io"):
            socketio_manage(environ, {'': RosPilotNamespace}, self.env_vars)
        else:
            return not_found(start_response)


def not_found(start_response):
    start_response('404 Not Found', [])
    return [json.dumps({'message': 'Not Found'})]


if __name__ == '__main__':
    parser = OptionParser("rospilot.py <options>")
    parser.add_option(
        "--server_port",
        dest="server_port",
        type='int',
        help="Please specify a port from 1-65535",
        default=8080)
    parser.add_option(
        "--policy_port",
        dest="policy_port",
        type='int',
        default=10843,
        help="Policy Listener")
    (opts, args) = parser.parse_args()

    SocketIOServer(
        ('0.0.0.0', opts.server_port),
        RosPilotIO(),
        resource="socket.io",
        policy_server=True,
        policy_listener=('0.0.0.0', opts.policy_port)).serve_forever()
