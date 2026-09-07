#!/usr/bin/env python3
"""Tesla monitor app for the 2026 Model Y.

A single, config-driven tool that connects to the Tesla Owner API via TeslaPy,
selects the vehicle by VIN, and provides a few commands:

    info      show a one-line status summary of the vehicle
    monitor   poll the vehicle and post to Slack when it starts moving
    history   fetch and save the charging history

Configuration lives in config.yaml (see config.example.yaml). Authentication
tokens are cached by TeslaPy in cache.json.

Usage:
    python app.py info
    python app.py monitor
    python app.py history [--out charge_history.json]
"""

import argparse
import json
import os
import sys
import time

import yaml
import requests
import teslapy
from geopy.distance import geodesic


# --------------------------------------------------------------------------- #
# Vehicle nominal-data model
# --------------------------------------------------------------------------- #
class EV:
    """Holds static/nominal spec data for an electric vehicle.

    The data is loaded from a YAML file (e.g. Model_Y.yaml) and describes
    range estimates, battery capacity and charging characteristics.
    """

    def __init__(self, nominal_data):
        self._nominal_data = nominal_data or {}

    @property
    def data(self):
        return self._nominal_data

    def nominal_capacity(self):
        """Nominal battery capacity as [value, unit], or None if unknown."""
        return self._nominal_data.get("battery", {}).get("nominal_capacity")

    def useable_capacity(self):
        """Useable battery capacity as [value, unit], or None if unknown."""
        return self._nominal_data.get("battery", {}).get("useable_capacity")


# --------------------------------------------------------------------------- #
# Config + connection helpers
# --------------------------------------------------------------------------- #
def load_config(path="config.yaml"):
    if not os.path.exists(path):
        sys.exit(
            f"Config file '{path}' not found. "
            f"Copy config.example.yaml to {path} and edit it."
        )
    with open(path) as f:
        return yaml.safe_load(f)


def select_vehicle(tesla, vin):
    """Return the Vehicle whose VIN matches, or exit with a helpful message."""
    vehicles = tesla.vehicle_list()
    if not vehicles:
        sys.exit("No vehicles found on this Tesla account.")
    for v in vehicles:
        if v.get("vin") == vin:
            return v
    available = ", ".join(f"{v.get('vin')} ({v.get('display_name') or 'unnamed'})"
                          for v in vehicles)
    sys.exit(f"VIN {vin} not found on this account. Available: {available}")


def notify_slack(webhook, message):
    """Post a simple text message to a Slack incoming webhook."""
    if not webhook:
        return
    try:
        requests.post(webhook, data=json.dumps({"text": message}),
                      headers={"Content-Type": "application/json"}, timeout=10)
    except requests.RequestException as e:
        print(f"[warn] Slack notification failed: {e}", file=sys.stderr)


def beep():
    """Best-effort audible beep; silently ignored if unavailable."""
    os.system("beep -f 500 -l 100 >/dev/null 2>&1")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_info(cfg, ev):
    with teslapy.Tesla(cfg["email"]) as tesla:
        vehicle = select_vehicle(tesla, cfg["vin"])
        name = vehicle.get("display_name") or "(unnamed)"
        print(f"{name}  VIN {vehicle['vin']}  state={vehicle.get('state')}")
        print(f"last seen: {vehicle.last_seen()}")
        try:
            level = vehicle["charge_state"]["battery_level"]
            rng = vehicle["charge_state"]["battery_range"]
            print(f"battery: {level}% SoC, ~{rng} mi rated range")
        except (KeyError, teslapy.HTTPError) as e:
            print(f"(battery data unavailable: {e})")
        cap = ev.nominal_capacity()
        if cap:
            print(f"nominal battery capacity: {cap[0]} {cap[1]}")


def cmd_monitor(cfg, ev):
    mon = cfg.get("monitor", {})
    interval = mon.get("poll_interval_sec", 5)
    do_beep = mon.get("beep_on_motion", True)
    webhook = cfg.get("slack_webhook")
    proximity_km = mon.get("proximity_km", 1.0)
    homes = mon.get("homes", []) or []

    print(f"Monitoring VIN {cfg['vin']} every {interval}s. Ctrl-C to stop.")
    if homes:
        names = ", ".join(h.get("name", "?") for h in homes)
        print(f"Proximity alert: within {proximity_km} km of {names}")

    # Edge-tracking state
    was_moving = False
    # Per-home flag: True while the car is currently inside the geofence,
    # so we only alert once per arrival and re-arm after it leaves.
    inside = {h.get("name", f"home{i}"): False for i, h in enumerate(homes)}

    with teslapy.Tesla(cfg["email"]) as tesla:
        vehicle = select_vehicle(tesla, cfg["vin"])
        try:
            while True:
                try:
                    data = vehicle.get_vehicle_location_data()
                    drive = data["drive_state"]
                    speed = drive.get("speed")
                    lat = drive.get("latitude")
                    lon = drive.get("longitude")
                except teslapy.HTTPError as e:
                    print(f"[warn] fetch failed: {e}", file=sys.stderr)
                    time.sleep(interval)
                    continue

                moving = bool(speed)

                # Started-moving alert (edge: stopped -> moving)
                if moving and not was_moving:
                    if do_beep:
                        beep()
                    message = f"{cfg['vin']} started moving (speed {speed})"
                    print(message)
                    notify_slack(webhook, message)
                was_moving = moving

                # Proximity alerts (edge: outside -> inside geofence)
                if lat is not None and lon is not None:
                    for i, h in enumerate(homes):
                        name = h.get("name", f"home{i}")
                        try:
                            dist_km = geodesic((lat, lon),
                                               (h["lat"], h["lon"])).km
                        except (KeyError, ValueError):
                            continue
                        if dist_km <= proximity_km and not inside[name]:
                            inside[name] = True
                            if do_beep:
                                beep()
                            message = (f"{cfg['vin']} is within {proximity_km} km "
                                       f"of {name} ({dist_km:.2f} km away)")
                            print(message)
                            notify_slack(webhook, message)
                        elif dist_km > proximity_km and inside[name]:
                            # Re-arm once it leaves, so the next arrival alerts
                            inside[name] = False

                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nStopped.")


def cmd_history(cfg, ev, out_path):
    with teslapy.Tesla(cfg["email"]) as tesla:
        vehicle = select_vehicle(tesla, cfg["vin"])
        history = vehicle.get_charge_history()
        with open(out_path, "w") as f:
            json.dump(history, f, indent=2)
        print(f"Wrote charge history to {out_path}")
        breakdown = history.get("total_charged_breakdown")
        if breakdown:
            print("Charged breakdown:")
            for k, v in breakdown.items():
                print(f"  {v.get('sub_title', k)}: {v.get('value')}"
                      f"{v.get('after_adornment', '')}")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="Tesla Model Y monitor app")
    parser.add_argument("-c", "--config", default="config.yaml",
                        help="path to config file (default: config.yaml)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="show a status summary of the vehicle")
    sub.add_parser("monitor", help="poll and notify Slack when the car moves")
    p_hist = sub.add_parser("history", help="fetch and save charging history")
    p_hist.add_argument("--out", default="charge_history.json",
                        help="output file (default: charge_history.json)")

    args = parser.parse_args()
    cfg = load_config(args.config)

    nominal_path = cfg.get("nominal_data", "Model_Y.yaml")
    nominal_data = {}
    if os.path.exists(nominal_path):
        with open(nominal_path) as f:
            nominal_data = yaml.safe_load(f)
    ev = EV(nominal_data)

    if args.command == "info":
        cmd_info(cfg, ev)
    elif args.command == "monitor":
        cmd_monitor(cfg, ev)
    elif args.command == "history":
        cmd_history(cfg, ev, args.out)


if __name__ == "__main__":
    main()
