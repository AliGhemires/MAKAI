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
- [x] Identifiants moteurs si besoin, calibration du bras et du leader
- [ ] Host lancé dans `tmux`, `make teleop` fonctionne, 2 caméras dans Rerun (téléop OK, 1 caméra, pas de `tmux`)
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
- Calibrer le bras comme `lekiwi` sur la Pi, pas comme `so_follower` sur un laptop.
- La webcam avant met 1,2 s à démarrer : `warmup_s: 3`, sinon le host échoue.
- Le clavier de la téléop est lu dans toutes les fenêtres : ne rien taper ailleurs.
- Hotspot iPhone : 2 sauts Wi-Fi en 2,4 GHz saturé, latence 50 à 140 ms et pics de 1 s ;
  le bras saute. Wi-Fi de la Pi en économie d'énergie : pics de 1 s (désactivé).
- La Pi a redémarré seule une fois (vers 18:05) et a disparu du réseau une autre fois :
  alimentation à surveiller.

## État

_Mis à jour avant chaque point d'équipe : ce qui marche (chiffres), ce qui bloque, besoins._

**Sam. 14, soir**
- Marche : 9 moteurs répondent (bras 1–6, roues 7–9), batterie 12,8 V ; bras calibré
  sur la Pi (`makai_kiwi`) ; leader calibré et dans le dépôt ; téléop bras + base depuis un
  laptop Windows, caméra avant dans Rerun.
- Côté laptop, la boucle de téléop tient 27,6 Hz (leader 1,2 ms, Rerun 1,8 ms) : ce n'est
  pas elle qui limite.
- Le bras saute encore un peu. Cause mesurée : le réseau (7 trous de plus de 200 ms en 12 s
  sur le flux). Atténué par `scripts/lekiwi_host.py` (accélération du bras réduite à 50).
- Réseau réglé : la Pi en point d'accès « makai-kiwi » (option A, `docs/SETUP.md`) donne
  6 ms d'aller-retour et un flux régulier à 29,9 images/s sans aucun trou de plus de
  100 ms (hotspot iPhone : 143 ms, pics de 1,2 s). Pas encore actif au démarrage de la Pi.
- La Pi a perdu son alimentation au moins deux fois (redémarrages, fichier réseau vide) :
  vérifier l'alimentation USB-C avant la collecte.
- À faire : copier `makai_kiwi.json` de la Pi dans `calibration/robots/lekiwi/` ; brancher
  la caméra de poignet (vue dans `lsusb`, pas de `/dev/video`) ; installer `tmux`.
