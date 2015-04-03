"""
Data model classes.

"""

import copy
import datetime
import logging as log

from google.appengine.ext import ndb
from google.appengine.api import memcache

from contrib.utils import get_localized_timestamp_str, get_current_timestamp_str


OVERVIEW_MODEL_ID_KEY = 1
MEMCACHE_OVERVIEW_KEY = "MEMCACHE_OVERVIEW_KEY"
MEMCACHE_BUILDS_KEY_BASE = "MEMCACHE_BUILDS_KEY_BASE"
ACTIVITY_SUMMARY_MODEL_ID_KEY = 1


class OverviewModel(ndb.Model):
    data = ndb.JsonProperty(required=True)

    @staticmethod
    @ndb.transactional()
    def get_overview_data():
        overview = memcache.get(MEMCACHE_OVERVIEW_KEY)
        if overview:
            overview["current_time"] = get_current_timestamp_str()
            return overview
        log.debug("OverviewModel not present in memcache, getting from datastore ...")
        overview = OverviewModel.get_by_id(OVERVIEW_MODEL_ID_KEY)
        # is already a Python object
        if overview is None:
            overview = OverviewModel()
            overview.data = {}
        d = overview.data
        d["current_time"] = get_current_timestamp_str()
        return d

    @staticmethod
    @ndb.transactional()
    def update_overview_data(data):
        overview = OverviewModel(id=OVERVIEW_MODEL_ID_KEY, data=data)
        overview.put()
        memcache.set(MEMCACHE_OVERVIEW_KEY, data)


class ActivitySummaryModel(ndb.Model):
    # since last summary email
    overview_update_counter = ndb.IntegerProperty(default=0)
    sent_emails_counter = ndb.IntegerProperty(default=0)
    stopped_builds_counter = ndb.IntegerProperty(default=0)
    builds_stats_update_counter = ndb.IntegerProperty(default=0)
    # total
    overview_update_counter_total = ndb.IntegerProperty(default=0)
    sent_emails_counter_total = ndb.IntegerProperty(default=0)
    stopped_builds_counter_total = ndb.IntegerProperty(default=0)
    builds_stats_update_counter_total = ndb.IntegerProperty(default=0)

    @staticmethod
    @ndb.transactional()
    def reset():
        data = ActivitySummaryModel.get_by_id(ACTIVITY_SUMMARY_MODEL_ID_KEY)
        fields = ["overview_update_counter",
                  "sent_emails_counter",
                  "stopped_builds_counter",
                  "builds_stats_update_counter"]
        [setattr(data, counter, 0) for counter in fields]
        data.put()

    @staticmethod
    @ndb.transactional()
    def increase_counters(which_counters=[]):
        # do also _total counter names
        which_counters.extend(["%s_total" % counter for counter in which_counters])
        data = ActivitySummaryModel.get_by_id(ACTIVITY_SUMMARY_MODEL_ID_KEY)
        for counter_name in which_counters:
            counter = getattr(data, counter_name)
            counter += 1
            setattr(data, counter_name, counter)
        data.put()

    @staticmethod
    @ndb.transactional()
    def get_data():
        data = ActivitySummaryModel.get_by_id(ACTIVITY_SUMMARY_MODEL_ID_KEY)
        if data is None:
            return None
        r = dict(overview_update_counter_total=data.overview_update_counter_total,
                 overview_update_counter=data.overview_update_counter,
                 sent_emails_counter_total=data.sent_emails_counter_total,
                 sent_emails_counter=data.sent_emails_counter,
                 stopped_builds_counter=data.stopped_builds_counter,
                 stopped_builds_counter_total=data.stopped_builds_counter_total)
        r["current_time"] = get_current_timestamp_str()
        return r


class BuildsStatisticsModel(ndb.Model):
    # key id will be job name (i.e. jenkins project name) + build id: 'build_name-build_id'
    name = ndb.StringProperty(default="")
    bid = ndb.IntegerProperty(default=0)
    status = ndb.StringProperty(default="")
    # time stamp of start of the build
    # DatetimeProperty ts can only support UTC.
    # NDB can only store UTC but no timezone specified (naive)
    ts = ndb.DateTimeProperty()
    duration = ndb.StringProperty(default="")
    # test cases counters
    passed = ndb.IntegerProperty(default=0)
    failed = ndb.IntegerProperty(default=0)
    skipped = ndb.IntegerProperty(default=0)
    error = ndb.IntegerProperty(default=0)

    def to_dict(self):
        r = dict(job_name=self.name,
                 build_id=self.bid,
                 status=self.status,
                 timestamp=get_localized_timestamp_str(self.ts),
                 duration=self.duration,
                 passed=self.passed,
                 failed=self.failed,
                 skipped=self.skipped,
                 error=self.error)
        return r

    @staticmethod
    # raise _ToDatastoreError(err) BadRequestError: queries inside transactions must have ancestors
    #@ndb.transactional()
    def get_builds_data(days_limit=1):
        cond = datetime.datetime.utcnow() - datetime.timedelta(days=days_limit)
        # order should be the same as BuildsStatistics.name, BuildsStatistics.ts
        # this will already be ordered by job name and then by build id (since keys are such)
        query = BuildsStatisticsModel.query().order(BuildsStatisticsModel.key)
        builds = query.fetch()  # returns list of builds, of BuildsStatistics objects

        # BadRequestError: The first sort property must be the same as the property to which the
        # inequality filter is applied.
        # In your query the first sort property is name but the inequality filter is on ts
        # -> do the timestamp filtering on my own ... (can't combine ordering and filtering
        # arbitrarily)

        data = dict(days_limit=days_limit,
                    num_builds=0,
                    builds={})
        # builds - dict keys - job names ; values: lists of all builds under that job name
        res_builds = {}
        for b in builds:
            # check if the build is not before days_limit days
            if b.ts < cond:
                continue
            res_build = copy.deepcopy(b.to_dict())
            del res_build["job_name"]
            try:
                res_builds[b.name].append(res_build)
            except KeyError:
                res_builds[b.name] = [res_build]
            finally:
                data["num_builds"] += 1
        data["builds"] = res_builds
        data["current_time"] = get_current_timestamp_str()
        return data