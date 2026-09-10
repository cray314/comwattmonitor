#!/usr/bin/env python3
"""
comwatt_monitor.py
-------------------
Interroge une box Comwatt gen4, vérifie deux critères :
  1. Pic de consommation anormal (> seuil configurable, en kW)
  2. Chute brutale de production solaire (panne probable) pendant la journée

Envoie un email d'alerte quand un critère est déclenché, et écrit un fichier
docs/status.json utilisé par l'app mobile (docs/index.html).

Toute la config sensible (identifiants Comwatt, SMTP) passe par des variables
d'environnement — jamais en dur dans ce fichier. Voir README.md.
"""

import json
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

from comwatt_client import ComwattClient, ComwattAuthError, ComwattAPIError

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "state.json"
STATUS_PATH = ROOT / "docs" / "status.json"

# Mots-clés possibles dans la réponse de l'API pour chaque grandeur.
# L'API Comwatt n'a pas de schéma public figé : on essaie plusieurs noms
# de champs connus. Lance explore_api.py une fois pour vérifier les tiens.
PRODUCTION_KEYS = ["productions", "production", "injections", "injection"]
CONSUMPTION_KEYS = ["consumptions", "consumption", "withdrawals", "withdrawal"]


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_state():
    if STATE_PATH.exists():
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"last_alert_consumption": None, "last_alert_production": None}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def env(name, required=True, default=None):
    value = os.environ.get(name, default)
    if required and not value:
        sys.exit(f"Variable d'environnement manquante : {name}")
    return value


def find_series(payload: dict, key_candidates):
    """Cherche la première clé connue (insensible à la casse) dans la réponse."""
    lowered = {k.lower(): k for k in payload.keys()}
    for candidate in key_candidates:
        if candidate in lowered:
            return payload[lowered[candidate]]
    return None


def point_value(point):
    """Extrait (timestamp, valeur) d'un point de série temporelle, quel que
    soit le nom exact des champs utilisés par l'API."""
    ts = point.get("date") or point.get("timestamp") or point.get("time")
    val = point.get("value")
    if val is None:
        val = point.get("y")
    return ts, float(val) if val is not None else None


def latest_and_previous(series, minutes_back=15):
    """Renvoie (valeur_actuelle_kW, valeur_il_y_a_N_min_kW) à partir d'une
    liste de points triée chronologiquement."""
    if not series:
        return None, None
    points = [point_value(p) for p in series if point_value(p)[1] is not None]
    if not points:
        return None, None
    points.sort(key=lambda p: p[0])
    latest_val = points[-1][1]

    # Cherche un point ~minutes_back plus tôt ; à défaut, prend le premier
    # point disponible dans la fenêtre récupérée.
    previous_val = points[0][1]
    if len(points) > 1:
        target_index = max(0, len(points) - 1 - minutes_back)
        previous_val = points[target_index][1]

    # Heuristique d'unité : l'API Comwatt renvoie généralement des Watts.
    def to_kw(v):
        return v / 1000 if abs(v) > 50 else v

    return to_kw(latest_val), to_kw(previous_val)


def send_email(subject, body, cfg):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = cfg["smtp_from"]
    msg["To"] = cfg["smtp_to"]

    with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
        server.starttls()
        server.login(cfg["smtp_user"], cfg["smtp_password"])
        server.sendmail(cfg["smtp_from"], [cfg["smtp_to"]], msg.as_string())


def is_daytime(hour, cfg):
    return cfg["production_check_start_hour"] <= hour < cfg["production_check_end_hour"]


def main():
    config = load_config()
    state = load_state()
    now = datetime.now(timezone.utc)
    local_hour = datetime.now().hour  # heure locale du runner

    smtp_cfg = {
        "smtp_host": env("SMTP_HOST"),
        "smtp_port": int(env("SMTP_PORT", default="587")),
        "smtp_user": env("SMTP_USER"),
        "smtp_password": env("SMTP_PASSWORD"),
        "smtp_from": env("ALERT_EMAIL_FROM"),
        "smtp_to": env("ALERT_EMAIL_TO"),
    }

    client = ComwattClient()
    try:
        client.authenticate(env("COMWATT_USERNAME"), env("COMWATT_PASSWORD"))
        sites = client.get_sites()
        if not sites:
            sys.exit("Aucun site Comwatt trouvé pour ce compte.")
        site_id = config.get("site_id") or sites[0]["id"]

        data = client.get_site_time_series(
            site_id,
            measure_kind="FLOW",
            aggregation_level="NONE",
            time_ago_unit="HOUR",
            time_ago_value=1,
        )
    except ComwattAuthError:
        sys.exit("Authentification Comwatt refusée : vérifie identifiants/mot de passe.")
    except ComwattAPIError as e:
        sys.exit(f"Erreur API Comwatt : {e.status_code} {e.detail}")

    production_series = find_series(data, PRODUCTION_KEYS)
    consumption_series = find_series(data, CONSUMPTION_KEYS)

    if production_series is None or consumption_series is None:
        sys.exit(
            "Impossible de trouver les séries production/consommation dans la "
            "réponse de l'API. Lance explore_api.py pour inspecter les clés "
            "réellement renvoyées et ajuste PRODUCTION_KEYS / CONSUMPTION_KEYS."
        )

    prod_now, prod_before = latest_and_previous(production_series, minutes_back=config["production_drop_window_minutes"])
    cons_now, _ = latest_and_previous(consumption_series, minutes_back=15)

    alerts = []

    # --- Critère 1 : pic de consommation ---
    if cons_now is not None and cons_now >= config["consumption_threshold_kw"]:
        alerts.append(
            f"⚡ Pic de consommation : {cons_now:.2f} kW (seuil {config['consumption_threshold_kw']} kW)."
        )

    # --- Critère 2 : chute brutale de production en journée ---
    if (
        prod_now is not None
        and prod_before is not None
        and is_daytime(local_hour, config)
        and prod_before >= config["production_min_before_drop_kw"]
    ):
        drop_ratio = (prod_before - prod_now) / prod_before if prod_before > 0 else 0
        if drop_ratio >= config["production_drop_ratio"]:
            alerts.append(
                f"☀️ Chute de production : {prod_before:.2f} kW → {prod_now:.2f} kW "
                f"(-{drop_ratio*100:.0f}%) en {config['production_drop_window_minutes']} min. Panne possible."
            )

    # --- Envoi des emails avec cooldown pour éviter le spam ---
    cooldown = config.get("alert_cooldown_minutes", 60)

    def should_alert(key):
        last = state.get(key)
        if not last:
            return True
        last_dt = datetime.fromisoformat(last)
        return (now - last_dt).total_seconds() >= cooldown * 60

    if alerts:
        to_send = []
        if any("consommation" in a for a in alerts) and should_alert("last_alert_consumption"):
            to_send.append(next(a for a in alerts if "consommation" in a))
            state["last_alert_consumption"] = now.isoformat()
        if any("production" in a for a in alerts) and should_alert("last_alert_production"):
            to_send.append(next(a for a in alerts if "production" in a))
            state["last_alert_production"] = now.isoformat()

        if to_send:
            body = "\n".join(to_send) + f"\n\nVérifié à {now.strftime('%d/%m/%Y %H:%M UTC')}."
            send_email("⚠️ Alerte Comwatt", body, smtp_cfg)

    save_state(state)

    # --- Statut pour l'app mobile ---
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "updated_at": now.isoformat(),
                "production_kw": prod_now,
                "consumption_kw": cons_now,
                "active_alerts": alerts,
                "thresholds": {
                    "consumption_threshold_kw": config["consumption_threshold_kw"],
                    "production_drop_ratio": config["production_drop_ratio"],
                },
            },
            f,
            indent=2,
        )

    print(f"OK — production={prod_now} kW, consommation={cons_now} kW, alertes={alerts}")


if __name__ == "__main__":
    main()
