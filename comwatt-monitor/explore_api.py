#!/usr/bin/env python3
"""
explore_api.py
--------------
Script à lancer UNE FOIS, en local, pour découvrir le format exact renvoyé
par ton compte Comwatt (les noms de champs peuvent légèrement varier selon
la config de ta box). Ça évite de deviner à l'aveugle dans comwatt_monitor.py.

Usage :
    export COMWATT_USERNAME="ton_email"
    export COMWATT_PASSWORD="ton_mot_de_passe"
    python explore_api.py
"""

import json
import os

from comwatt_client import ComwattClient

client = ComwattClient()
client.authenticate(os.environ["COMWATT_USERNAME"], os.environ["COMWATT_PASSWORD"])

sites = client.get_sites()
print("=== SITES ===")
print(json.dumps(sites, indent=2, ensure_ascii=False)[:1000])

site_id = sites[0]["id"]

print("\n=== DEVICES ===")
devices = client.get_devices(site_id)
print(json.dumps(devices, indent=2, ensure_ascii=False)[:1500])

print("\n=== SITE TIME SERIES (FLOW, dernière heure) ===")
data = client.get_site_time_series(
    site_id,
    measure_kind="FLOW",
    aggregation_level="NONE",
    time_ago_unit="HOUR",
    time_ago_value=1,
)
print("Clés de premier niveau :", list(data.keys()))
print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])

print(
    "\n--> Repère ici les clés qui correspondent à la production solaire et "
    "à la consommation, puis mets-les à jour dans PRODUCTION_KEYS / "
    "CONSUMPTION_KEYS en haut de comwatt_monitor.py si besoin."
)
