"""For parsing stats from The Atlantic's daily health auth rona stats."""
from __future__ import absolute_import

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
import requests
import sys


URL = "https://docs.google.com/spreadsheets/u/2/d/e/2PACX-1vRwAqp96T9sYYq2-i7Tj0pvTf6XVHjDSMIKBdZHXiCGGdNC0ypEU9NbngS8mxea55JuCFuua1MUeOj5/pubhtml#"
OUTDIR = "./data"
OUTFILE = "%s/backup.html" % OUTDIR
OUTJSON = "%s/dates.json" % OUTDIR
STATEJSON = "%s/states.json" % OUTDIR
RATEJSON = "%s/rates.json" % OUTDIR
USJSON = "%s/us.json" % OUTDIR
NUM_COLS = 20

# Date
# State
# Positive
# Negative
# Pending	Hospitalized  Currently
# Hospitalized  Cumulative
# In ICU  Currently
# In ICU  Cumulative
# On Ventilator  Currently
# On Ventilator  Cumulative
# Recovered
# Deaths
# Data Quality Grade
# Last Update ET
# Total Tests (PCR)
# Positive Tests (PCR)
# Negative Tests (PCR)
# Positive Cases (PCR)
# Total Tests (People)

WANT_FIELDS = [
    "positive", "deaths", "negative", "pending", "hospitalized_current"]
MORE_FIELDS = ["hospitalized_total", "icu_current", "icu_total",
               "vent_current", "vent_total", "recovered"]

class Parser():
    def __init__(self, debug=None):
        self.data_types = self.get_data_types()
        self.results = {}
        self.state_results = {}
        self.rates = {}
        self.us = {}
        self.debug = debug

    def get_data_types(self):
        return ["deaths", "positive", "negative", "total"]

    def parse(self):
        self.get_data_from_url()
        self.parse_soup()
        self.compute_rates()
        self.sum_fields()
        self.write_files()

    def get_data_from_url(self):
        if self.debug:
            return

        text = requests.get(URL).text
        with open(OUTFILE, "w") as fh:
            fh.write(text.encode("utf-8", "replace"))

    def get_backup_file(self):
        with open(OUTFILE) as fh:
            return fh.read()

    def soupify(self, text):
        return BeautifulSoup(text, 'html.parser')

    # compute % change for each data type from one day to another
    def compute_rates(self):
        def format_date(entry):
            string = "%s-%s-%s" % (
                entry["month"]+1, entry["day"], entry["year"])

            return str(datetime.strptime(string, "%m-%d-%Y").date())

        for state in self.state_results:
            self.rates[state] = {}
            for dtype, data in self.state_results[state].iteritems():
                if dtype not in self.data_types:
                    continue

                self.rates[state][dtype] = []
                yesterday = None
                data.reverse()

                for idx, entry in enumerate(data):
                    if (dtype == "positive") and entry["y"] < 100:
                        continue

                    # if (dtype == "deaths") and entry["y"] < 1:
                    #     continue

                    if yesterday is None:
                        yesterday = entry["y"]
                        continue

                    rate = self.compute_rate(
                        float(yesterday), float(entry["y"]))

                    result = {
                        "dtype": dtype,
                        "y": rate,
                        "change": "%d%%" % rate,
                        "x": idx,
                        "day": idx,
                        "date": format_date(entry),
                        "today": entry["y"],
                        "num": rate,
                        "yesterday": yesterday,
                    }

                    self.rates[state][dtype].append(result)
                    yesterday = entry["y"]

    def compute_rate(self, yesterday, today):
        try:
            return int((today-yesterday)/yesterday*100)
        except ZeroDivisionError:
            return 0

    # parse stats from html data from Atlantic site
    def parse_soup(self):
        soup = self.soupify(self.get_backup_file())
        table = soup.find_all('tbody')[3]

        for idx, row in enumerate(table.find_all('tr')):
            result = {}
            columns = row.find_all("td")

            if len(columns) != NUM_COLS:
                print "not enough cols"
                exit

            result, date_str = self.parse_result(columns)
            if not result and not date_str:
                continue

            if date_str not in self.results:
                self.results[date_str] = {}

            state = result['state']
            if state not in self.state_results:
                self.state_results[state] = {}

            self.results[date_str][result['state']] = result
            self.state_results[state] = self.parse_state(
                result, self.state_results[state], idx)

    def parse_result(self, columns):
        def parse_col(idx):
            item = columns[idx].get_text()
            if not item:
                return 0
            try:
                return int(item.replace(",", ""))
            except ValueError:
                return 0

        result = {}
        result['date'] = str(columns[0].get_text())
        if result['date'] == u'Date' or result['date'] == "":
            return None, None

        date = datetime.strptime(result['date'], '%Y%m%d')
        date_str = "%d/%d" % (date.month, date.day)
        date_str = str(date.date())

        result['year'] = date.year
        result['month'] = date.month - 1
        result['day'] = date.day
        result['date'] = date_str
        result['state'] = columns[1].get_text()

        idx = 2
        for dtype in ["positive", "negative", "pending",
                      "hospitalized_current", "hospitalized_total",
                      "icu_current", "icu_total", "vent_current",
                      "vent_total", "recovered", "deaths"]:
            result[dtype] = parse_col(idx)
            idx += 1

        return (result, date_str)

    def parse_state(self, result, state, idx):
        state = self.parse_item(result, state, "positive", idx)
        state = self.parse_item(result, state, "deaths", idx)
        state = self.parse_item(result, state, "negative", idx)
        state = self.parse_item(result, state, "pending", idx)
        state = self.parse_item(result, state, "hospitalized_current", idx)

        return state

    def parse_item(self, result, state, item, idx):
        # if (item == "positive") and result[item] < 100:
        #     return

        if item not in state:
            state[item] = []

        state[item].append({
            "num": int(result[item]),
            "year": result['year'],
            "month": result['month'],
            "day": result['day'],
            "y": int(result[item]),
            "x": idx,
        })

        return state

    def write_files(self):
        self.write_file(OUTJSON, self.results)
        self.write_file(STATEJSON, self.state_results)
        self.write_file(RATEJSON, self.rates)
        self.write_file(USJSON, self.us)

    def write_file(self, name, results):
        with open(name, 'w') as fh:
            fh.write(json.dumps(results, indent=2))

    def sum_fields(self):
        def sum_field(day):
            self.us[day] = {}
            for state, data in results.iteritems():
                for dtype in WANT_FIELDS:
                    if dtype in self.us[day]:
                        self.us[day][dtype] += results[state][dtype]
                    else:
                        self.us[day][dtype] = results[state][dtype]

        today = datetime.today().strftime('%Y-%m-%d')
        results = self.results[today]
        sum_field(today)

        yesterday = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        results = self.results[yesterday]
        sum_field(yesterday)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        print "Running in debug mode"
        p = Parser(True)
    else:
        p = Parser()
    p.parse()
