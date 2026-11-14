# WS1 · Robot et données

**Responsable :** _à inscrire_ · **Couloir :** `src/makai/robot/`, `scripts/`, `docs/SETUP.md`

## Mission

Faire du robot un outil fiable pour les quatre autres : il démarre en une commande, se
téléopère sans à-coups, enregistre des datasets propres. Tu tiens aussi le planning du robot.

## Ce que les autres attendent de toi

- `LeKiwiRobot` respecte le contrat `Robot` (`src/makai/contracts.py`).
- Le montage physique ne bouge plus après la porte G2.
- Des images et vidéos de la caméra avant pour WS2, le plus tôt possible.
- Les datasets sur le Hub, listés dans `docs/REGISTRY.md`.

## Tâches

### Samedi, avant 18:00 (porte G1)
- [ ] Checklist H0 de `docs/PLAN.md` : leader présent ? Pi, réseau, batterie, caméras
- [ ] Installer LeRobot sur la Pi (`docs/SETUP.md`, section 2)
- [ ] Identifiants moteurs si besoin, calibration du bras et du leader
- [ ] Host lancé dans `tmux`, `make teleop` fonctionne, 2 caméras dans Rerun
- [ ] Vérifier les couleurs (RGB) et l'orientation des images ; corriger dans `robot/lekiwi.py`
- [ ] Enregistrer 2 minutes de vidéo de la caméra avant en roulant dans la zone, pour WS2

### Samedi 18:00–22:00 (porte G2)
- [ ] Fixer les caméras, photos dans `assets/`, repères au marqueur
- [ ] Mesurer et remplir `perception.camera_model`
- [ ] Capturer `home`, `drop_reach`, `drop_open`, et les poses `pick_*` avec WS4
- [ ] Valider en téléop : quels objets se saisissent bien, quelle hauteur de bac est atteignable
- [ ] Avec WS2 : calibration du sol
- [ ] Avec WS3 : premier `robot.drive()` réel, vérifier les signes et les vitesses
- [ ] Mesurer l'autonomie de la batterie

### Samedi soir et dimanche
- [ ] Collecte v1, v2, corrections (`docs/DATA_COLLECTION.md`)
- [ ] Tenir le planning du robot (`docs/WORKFLOW.md`, section 3)
- [ ] Script de démarrage du host sur la Pi (`tmux`, relance automatique)
- [ ] Dimanche soir : robot prêt pour la démo, batterie, câbles fixés, rien qui dépasse

## Terminé quand

Un coéquipier qui n'a jamais touché le robot le démarre et le téléopère en moins de 5
minutes en suivant `docs/SETUP.md`.

## Pièges connus

- Le host s'arrête après 30 s sans `--host.connection_time_s`.
- Les noms et résolutions des caméras doivent être identiques côté host et côté config.
- La calibration du leader est locale à un laptop.
- Les servos chauffent : pose `home` reposante, pauses pendant la collecte.

## État

_Mis à jour avant chaque point d'équipe : ce qui marche (chiffres), ce qui bloque, besoins._
