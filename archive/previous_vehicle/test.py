#!/usr/bin/env python3

class EV:
    """Documentation for EV

    """
    def nominal_consumption():
        
        return _nominal_data['']

    def __init__(self, nominal_data):
        self._nominal_data = nominal_data
        
        

# basic nominal data
# from the internet
import yaml
with open("Model_Y.yaml") as f: modelY_nominal_data = yaml.safe_load(f)

modelY = EV(modelY_nominal_data)

import time
import os
beep = lambda x: os.system("beep -f 500 -l 100")


from teslapy import Tesla

# this is a Slack app in the rrgroup workspace I created at
# https://api.slack.com/apps?new_app=1
import requests
import json
slack_webhook = "https://hooks.slack.com/services/XXXX/YYYY/ZZZZ"  # redacted

tesla = Tesla('rapa@mit.edu')
vehicles = tesla.vehicle_list()
tesla1 = vehicles[0]
while True:
    data = tesla1.get_vehicle_data()
    speed = data["drive_state"]["speed"]
    if speed:
        beep(2)
        message = f"Speed: {speed}"
        print(message)
        jsoned = { "text" : message}
        requests.post(slack_webhook, json.dumps(jsoned))
    time.sleep(5)

# import json
# help(json.dump)
# fp = open('test.json','w')
# json.dump(vv.get_charge_history(),fp)
# fp.close()
# help(json.load)
# ff = open('test.json')
# data = json.load(ff)
# ff.close()
