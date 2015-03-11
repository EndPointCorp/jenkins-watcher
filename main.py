# -*- coding: utf-8 -*-
"""
Google App Engine Jenkins CI server watcher application.

Main application file.

Uses jenkinsapi library (wrapper around Jenkins CI server REST calls).
https://pypi.python.org/pypi/jenkinsapi


NOTES:
    the number of HTTP connection to jenkins server is very high (jenkinsapi lib)
    very often:

    ConnectionError: HTTPConnectionPool(host='XXXXX', port=8080):
    Max retries exceeded with url: XXXXX
    (Caused by <class 'gae_override.httplib.HTTPException'>:
    Deadline exceeded while waiting for HTTP response from URL: XXXXX
    solved by patching jenkinsappi and requests lib (libs/README.md)

    The server works in CET/CEST times, talk the same (convert to this timezome
        times as retrieved from the server or datetime timestamps which are UTC).

    NDB can only store DataTimeProperty in UTC but timezone unaware (naive),
        otherwise .put() throws an exception


REFERENCE:
    self.request.body


TODO:
    experiment with sms alerts

"""


import os
import json
import sys
import pprint
import logging

import webapp2
from google.appengine.ext import deferred

from config import egg_files
for egg_file in egg_files:
    sys.path.append(os.path.join(os.path.dirname(__file__), "libs", egg_file))

from jenkins import JenkinsInterface, get_jenkins_instance
from jenkins import ActivitySummary, BuildsStatistics
from utils import get_current_timestamp_str, access_restriction, send_email
from utils import exception_catcher


class RequestHandler(webapp2.RequestHandler):
    @access_restriction
    @exception_catcher
    def index(self):
        # there is no timezone info there, maybe it's deeper
        # log.info("Received request, headers:\n%s" % self.request.headers.items())
        # returns Python dictionary
        resp = JenkinsInterface.get_overview_data()
        resp["current_time"] = get_current_timestamp_str()
        self.response.headers["Content-Type"] = "application/json"
        self.response.out.write(json.dumps(resp))

    @exception_catcher
    def update_overview_check_builds(self):
        msg = "Running task at %s ..." % get_current_timestamp_str()
        logging.info(msg)
        deferred.defer(get_jenkins_instance().update_overview_check_builds)
        self.response.out.write(msg)

    @exception_catcher
    def update_builds_stats(self):
        msg = "Running task at %s ..." % get_current_timestamp_str()
        logging.info(msg)
        deferred.defer(get_jenkins_instance().update_builds_stats)
        self.response.out.write(msg)

    def init(self):
        msg = "Initialization run at %s ..." % get_current_timestamp_str()
        logging.info(msg)
        if ActivitySummary.get_by_id(ActivitySummary.summary_id_key) is None:
            logging.debug("ActivitySummary initialization ...")
            activity = ActivitySummary(id=ActivitySummary.summary_id_key)
            activity.put()
            logging.debug("Finished ActivitySummary initialization.")
        else:
            logging.debug("ActivitySummary is already initialized.")
        if len(BuildsStatistics.query().fetch()) == 0:
            deferred.defer(get_jenkins_instance().builds_stats_init)
            logging.debug("Finished BuildsStatistics initialization.")
        else:
            logging.debug("BuildStatistics is already initialized.")
        self.response.out.write(msg)

    def send_summary(self):
        logging.info("Sending activity summary email at %s ..." % get_current_timestamp_str())
        formatted_data = pprint.pformat(ActivitySummary.get_data())
        send_email(subject="activity summary",
                   body="activity summary: " + "\n\n" + formatted_data)
        ActivitySummary.reset()
        logging.info("Finished sending activity summary.")


# adjust logging
LOG_FORMAT = "[%(module)s::%(funcName)s:%(lineno)s] %(message)s"
logging.getLogger().handlers[0].setFormatter(logging.Formatter(fmt=LOG_FORMAT))
# jenkinsapi makes incredible amount of calls to jenkins and log output
# is crowded with each HTTP call and its result debug messages, limit this
log = logging.getLogger("requests.packages.urllib3")
log.setLevel(logging.WARNING)



routes = [
    webapp2.Route(r"/",
                  handler="main.RequestHandler:index",
                  name="index",
                  methods=["GET", ]),
    webapp2.Route(r"/update_overview_check_builds",
                  handler="main.RequestHandler:update_overview_check_builds",
                  name="update_overview_check_builds",
                  methods=["GET", ]),
    webapp2.Route(r"/update_builds_stats",
                  handler="main.RequestHandler:update_builds_stats",
                  name="update_builds_stats",
                  methods=["GET", ]),
    webapp2.Route(r"/init",
                  handler="main.RequestHandler:init",
                  name="init",
                  methods=["GET", ]),
    webapp2.Route(r"/send_summary",
                  handler="main.RequestHandler:send_summary",
                  name="send_summary",
                  methods=["GET", ]),
]


# application instance
app = webapp2.WSGIApplication(routes=routes, debug=True)