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

from teslapy import Tesla
tesla = Tesla('rapa@mit.edu')
vehicles = tesla.vehicle_list()
tesla1 = vehicles[0]
data = tesla1.get_vehicle_data()
print(data)
charge_history = tesla1.get_charge_history()

charge_history['total_charged_breakdown']

# import json
# help(json.dump)
# fp = open('test.json','w')
# json.dump(vv.get_charge_history(),fp)
# fp.close()
# help(json.load)
# ff = open('test.json')
# data = json.load(ff)
# ff.close()
