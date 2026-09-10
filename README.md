# Comwatt monitor — alertes email + app mobile

Surveille ta box Comwatt gen4 et t'envoie un email si :
- la **consommation** dépasse un seuil (pic anormal) ;
- la **production solaire** chute brutalement en pleine journée (panne probable).

Une petite app mobile (installable sur l'écran d'accueil) affiche l'état en direct.

Aucun serveur à gérer : tout tourne gratuitement via **GitHub Actions**, qui
exécute le contrôle toutes les 10 minutes.

## 1. Vérifier l'accès à l'API (une seule fois, en local)

```bash
pip install -r requirements.txt
export COMWATT_USERNAME="ton_email_comwatt"
export COMWATT_PASSWORD="ton_mot_de_passe"
python explore_api.py
```

Ce script affiche la structure exacte renvoyée par ton compte. Repère les
noms des champs pour la production et la consommation : ils sont déjà gérés
par défaut (`productions`, `consumptions`, etc.) mais si ton compte utilise
d'autres noms, ajuste `PRODUCTION_KEYS` / `CONSUMPTION_KEYS` en haut de
`comwatt_monitor.py`.

## 2. Créer le dépôt GitHub

1. Crée un nouveau dépôt GitHub (public ou privé) et pousse-y ce dossier.
2. Va dans **Settings → Pages** et active GitHub Pages sur la branche
   `main`, dossier `/docs`. C'est ce qui sert l'app mobile.

## 3. Ajouter les secrets (Settings → Secrets and variables → Actions)

| Secret | Valeur |
|---|---|
| `COMWATT_USERNAME` | ton identifiant Comwatt |
| `COMWATT_PASSWORD` | ton mot de passe Comwatt |
| `SMTP_HOST` | ex: `smtp.gmail.com` |
| `SMTP_PORT` | ex: `587` |
| `SMTP_USER` | ton adresse email d'envoi |
| `SMTP_PASSWORD` | mot de passe / **mot de passe d'application** (pas ton mot de passe principal si tu utilises Gmail) |
| `ALERT_EMAIL_FROM` | adresse d'expéditeur |
| `ALERT_EMAIL_TO` | adresse qui reçoit les alertes (peut être la même) |

Avec Gmail : active la validation en deux étapes puis génère un
**mot de passe d'application** dédié — ton mot de passe normal ne
fonctionnera pas avec SMTP.

## 4. Ajuster les seuils

Modifie `config.json` directement dans le dépôt :

```json
{
  "consumption_threshold_kw": 5.0,          // alerte si conso ≥ 5 kW
  "production_drop_ratio": 0.6,             // alerte si la prod chute de 60%+
  "production_drop_window_minutes": 15,     // sur une fenêtre de 15 min
  "production_min_before_drop_kw": 0.5,     // ignore les chutes si prod déjà < 0.5 kW
  "production_check_start_hour": 8,         // ne vérifie la prod qu'entre 8h...
  "production_check_end_hour": 20,          // ...et 20h (évite les fausses alertes au coucher du soleil)
  "alert_cooldown_minutes": 60              // n'envoie pas plus d'un email par critère et par heure
}
```

## 5. Lancer et vérifier

Le workflow (`.github/workflows/monitor.yml`) se déclenche automatiquement
toutes les 10 minutes. Pour le tester tout de suite : onglet **Actions** du
dépôt → `Comwatt monitor` → **Run workflow**.

## 6. Installer l'app sur ton téléphone

Une fois GitHub Pages activé, ton app est visible à :
`https://<ton-utilisateur>.github.io/<nom-du-dépôt>/`

- **iPhone (Safari)** : ouvre le lien → bouton Partager → *Sur l'écran d'accueil*.
- **Android (Chrome)** : ouvre le lien → menu ⋮ → *Ajouter à l'écran d'accueil*.

Elle se met à jour toute seule après chaque passage du contrôle automatique.

## Fichiers

| Fichier | Rôle |
|---|---|
| `comwatt_monitor.py` | Script principal : vérifie les critères, envoie l'email |
| `explore_api.py` | À lancer une fois pour inspecter le format réel de l'API |
| `config.json` | Seuils modifiables |
| `state.json` | Mémorise la dernière alerte envoyée (anti-spam) — géré automatiquement |
| `.github/workflows/monitor.yml` | Planifie l'exécution toutes les 10 min |
| `docs/` | L'app mobile (page web installable), servie par GitHub Pages |

## Limites à connaître

- Les identifiants Comwatt sont utilisés directement (pas d'OAuth public) :
  garde le dépôt privé si ça te dérange qu'un secret GitHub les contienne.
- Le format exact des séries temporelles Comwatt peut légèrement varier
  selon la config de ta box — `explore_api.py` est là pour lever le doute.
- GitHub Actions "schedule" peut avoir quelques minutes de retard aux heures
  de forte charge ; ce n'est pas du temps réel à la seconde près.
