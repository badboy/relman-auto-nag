# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re

from auto_nag import logger, utils

RANGE_PAT = re.compile(r"\[([0-9]+)[ \t]*;[ \t]*([0-9]*|\+∞)\[", re.UNICODE)
NPLUS_PAT = re.compile(r"n\+([0-9]+)")


class Range(object):
    def __init__(self, m, M):
        super(Range, self).__init__()
        self.m = m
        self.M = M

    def is_in(self, x):
        if self.M is None:
            return x >= self.m
        return self.m <= x < self.M

    @staticmethod
    def from_string(s):
        mat = RANGE_PAT.match(s)
        if mat:
            m = int(mat.group(1))
            M = mat.group(2)
            M = int(M) if M.isdigit() else None
            return Range(m, M)

    def __lt__(self, other):
        return self.m < other.m

    def __str__(self):
        if self.M is None:
            return "[{};+∞[".format(self.m)
        return "[{};{}[".format(self.m, self.M)

    def __repr__(self):
        return self.__str__()


class Supervisor(object):
    def __init__(self, who, people):
        super(Supervisor, self).__init__()
        self.who = who
        self.people = people

    def get(self, person, skiplist, **kwargs):
        m = NPLUS_PAT.match(self.who)
        if m:
            sup = self.people.get_nth_manager_mail(person, int(m.group(1)))
        elif self.who == "director":
            sup = self.people.get_director_mail(person)
        elif self.who == "vp":
            sup = self.people.get_vp_mail(person)
        elif self.who == "self":
            sup = self.people.get_moz_mail(person)
        else:
            assert self.who in kwargs, "{} required as keyword argument in add".format(
                self.who
            )
            sup = self.people.get_moz_mail(kwargs[self.who])

        if not sup or sup in skiplist:
            sup = self.people.get_nth_manager_mail(person, 1)

        if not sup:
            # we don't have any supervisor so nag self
            logger.info("No supervisor for {}: {}".format(self, person))
            sup = self.people.get_moz_mail(person)

        return sup

    def is_hierarchical_supervisor(self) -> bool:
        """Identify if the supervisor is a superior in the management chain"""
        return bool(
            NPLUS_PAT.match(self.who)
            or self.who
            in (
                "director",
                "vp",
                "self",
            )
        )

    def __str__(self):
        return self.who

    def __repr__(self):
        return self.__str__()


class Step(object):
    def __init__(self, rang, supervisor, days):
        super(Step, self).__init__()
        self.rang = rang
        self.supervisor = supervisor
        self.days = days

    def get_supervisor(self, days, person, skiplist, **kwargs):
        if self.rang.is_in(days):
            return self.supervisor.get(person, skiplist, **kwargs)
        return None

    def filter(self, days, weekday):
        if self.rang.is_in(days):
            return weekday in self.days
        return None

    def __lt__(self, other):
        return self.rang < other.rang

    def __str__(self):
        alldays = [
            k for k, _ in sorted(utils.get_weekdays().items(), key=lambda p: p[1])
        ]
        days = [alldays[x] for x in sorted(self.days)]
        return "{} => supervisor: {}, days: {}".format(self.rang, self.supervisor, days)

    def __repr__(self):
        return self.__str__()


class Escalation(object):
    def __init__(self, people, data=None, skiplist=[]):
        super(Escalation, self).__init__()
        self.people = people
        self.skiplist = skiplist
        self.data = {
            "high": Escalation._get_steps("high", people, data),
            "normal": Escalation._get_steps("normal", people, data),
            "default": Escalation._get_steps("default", people, data),
        }

    def is_hierarchical_escalation_only(self) -> bool:
        """Identify if all escalation steps are pointing to a superior in the
        management chain.
        """
        return all(
            step.supervisor.is_hierarchical_supervisor()
            for steps in self.data.values()
            for step in steps
        )

    def get_supervisor(self, priority, days, person, **kwargs):
        steps = self.data[priority]
        for step in steps:
            s = step.get_supervisor(days, person, self.skiplist, **kwargs)
            if s is not None:
                return s

    def filter(self, priority, days, weekday):
        steps = self.data[priority]
        for step in steps:
            ok = step.filter(days, weekday)
            if ok is not None:
                return ok

    def as_string(self, priority):
        return "\n".join(str(s) for s in self.data[priority])

    @staticmethod
    def _get_steps(priority, people, data):
        res = []
        data = (
            utils.get_config("escalation", priority)
            if data is None
            else data.get(priority, {})
        )
        week = utils.get_weekdays()
        for r, sd in data.items():
            res.append(
                Step(
                    Range.from_string(r),
                    Supervisor(sd["supervisor"], people),
                    {week[d] for d in sd["days"]},
                )
            )
        return sorted(res)


class NoActivityDays(object):
    def __init__(self, name, data=None):
        super(NoActivityDays, self).__init__()
        self.data = NoActivityDays._get(data, name)

    def get(self, ndays):
        for x in self.data:
            rng, n = x
            if rng.is_in(ndays):
                return n

    @staticmethod
    def _get(data, name):
        res = []
        data = utils.get_config(name, "ndays") if data is None else data["ndays"]
        for r, n in data.items():
            res.append((Range.from_string(r), n))
        return sorted(res)
