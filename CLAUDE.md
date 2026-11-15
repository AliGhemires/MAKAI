# MAKAI — contexte pour Claude

Hackathon Leukerbad Robotics Carnival 2026, Track 1. Équipe de 5, chacun avec son Claude.
**Deadline : lundi 16 novembre 2026, 12:00.** Checkpoint dimanche 15 à 17:00.

Robot mobile LeKiwi + bras SO-101 qui ramasse ce qui traîne au sol, trie linge et déchets,
et les dépose dans la bonne station. Stack : Python 3.12, `uv`, LeRobot 0.7.0, Ultralytics.

## À lire avant d'agir

1. `docs/PLAN.md` : périmètre, calendrier, niveaux L0 à L5, plans de repli.
2. `docs/WORKFLOW.md` : qui possède quoi, règles git.
3. La fiche du workstream de la personne : `docs/workstreams/WS<N>_*.md`.
4. `docs/ARCHITECTURE.md` avant de toucher au code.

Si la personne n'a pas dit quel est son workstream, le lui demander.

## Règles de travail

- **Pas de relecture, pas d'attente.** L'équipe a deux jours : les branches et `main` servent
  à s'organiser. Quand la personne demande un changement, va jusqu'au merge sur `main` dès
  que les tests passent, sans redemander ni attendre une approbation.
- **`main` doit toujours passer `make check` et `make sim`** : c'est la seule règle stricte.
  Lancer `make check` avant tout push. Du code : branche `ws<N>/<sujet>`, PR mergée en squash
  dès que ses tests sont verts. Docs, fiches, config, petits correctifs : directement sur `main`.
- **Reste dans le couloir de la personne.** Dossiers par workstream : tableau de
  `docs/PLAN.md`, section 6. Si la tâche oblige à toucher le code d'un autre couloir, fais-le
  et dis-le à la personne, pour qu'elle prévienne le responsable dans le chat.
- **Fichiers partagés** : `src/makai/contracts.py`, `configs/makai.yaml`,
  `configs/arm_poses.yaml`, `configs/ground_plane.yaml`, `docs/PLAN.md`, ce fichier. Tu peux
  les modifier quand la tâche le demande ; signale-le à la personne, qui l'annonce dans le chat.
- **Jamais dans git** : données, vidéos, poids de modèles, tokens. Ils vont sur le Hub
  Hugging Face. Seule exception : les petits poids du détecteur, `models/detector_*.pt`
  (quelques Mo). Les valeurs propres à un laptop vont dans `configs/local.yaml` (ignoré).
- **En fin de session**, proposer de mettre à jour la fiche du workstream : tâches
  cochées, section « État » avec des chiffres, pièges rencontrés. Une décision qui engage
  les autres va dans `docs/DECISIONS.md`.
- Docs en français, code, commentaires et messages de commit en anglais.

## Priorités quand il faut trancher

1. Une boucle complète fiable passe avant toute amélioration d'une brique.
2. Ne pas commencer un niveau tant que le précédent n'a pas réussi son test chiffré.
3. Si une porte du calendrier est manquée, passer au plan de repli plutôt qu'insister.
4. Préférer la solution la plus simple qui marche lundi midi. Pas d'abstraction pour plus tard.
5. Après dimanche 22:00 : corrections et réglages uniquement.

## Faits techniques à ne pas réinventer

- Les contrats entre modules sont dans `src/makai/contracts.py`. Chaque contrat a une
  implémentation réelle et une implémentation simulée (`src/makai/sim/`).
- Repère base : `x` avant, `y` gauche, angles anti-horaires, mètres, rad/s. LeRobot parle
  en degrés et deg/s : la conversion est dans `src/makai/robot/lekiwi.py` uniquement.
- La distance aux objets vient d'une homographie du sol (`perception/geometry.py`), pas
  d'un modèle de profondeur.
- Mission qui balaie : le repère de la carte est celui de l'odométrie, origine à la pose de
  départ, **devant la poubelle, dos à elle, face à la pièce** ; les stations sont placées
  dans ce repère (`navigation.sweep.stations`). Détail : `docs/NAVIGATION.md`.
- Elle a deux usages, choisis dans la console ou avec `--use` (`orchestrator/sweep.py`,
  `for_use`). **Vacuum & collect** (chambre d'hôtel) : le robot passe sur tout le sol en
  rangées sans jamais tourner, perpendiculaire au mur de la poubelle (`pattern: rows`), et ne
  ramasse que ce qui est sur son passage (`pickup_range_m`). **Scan & collect** (rue) : il
  suit de larges couloirs en regardant à gauche et à droite (`pattern: scan`) et va chercher
  tout ce qu'il repère. Dans les deux, il dépose l'objet puis revient où il était.
  `pattern: lanes` rend l'ancien parcours de Vacuum, en couloirs, où le robot tourne.
- La zone à balayer est un rectangle imaginaire, sans mur. Elle se trace en conduisant le
  robot (console, onglet Mission, « Trace zone ») ; elle est gardée dans `configs/zone.yaml`
  (hors git) et remplace alors `navigation.sweep.room` (`navigation/zone.py`).
- Les objets sont trouvés et classés par notre propre détecteur (`LearnedDetector`,
  `models/detector_v2.pt`), entraîné sans annotation manuelle par `scripts/train_detector.py`.
  Mesures et limites : `docs/workstreams/WS2_perception.md`.
- LeRobot 0.7.0 a beaucoup changé par rapport aux versions antérieures : **vérifier dans
  le code installé** (`.venv/lib/python3.12/site-packages/lerobot/`) ou avec `--help`
  avant d'écrire une commande ou un import. Points déjà vérifiés : `docs/ARCHITECTURE.md`,
  dernière section. Doc : https://huggingface.co/docs/lerobot
- Inférence et déploiement : `lerobot-rollout` (stratégies `base`, `dagger`...).
  Entraînement cloud : `lerobot-train --job.target=<gpu>`.
- Le host LeKiwi s'arrête après 30 s sans `--host.connection_time_s`.
- **Se connecter au robot** : `docs/ROBOT_NETWORK.md` (choix du réseau selon l'OS et la
  préférence : iPhone, option A ou B, commandes pas à pas), puis `docs/SETUP.md` section 4
  pour le host et la téléop ; état dans `docs/workstreams/WS1_robot_data.md`. Mots de
  passe dans le chat d'équipe, jamais dans le dépôt. Mesurer le réseau avec
  `scripts/net_check.py` avant d'accuser le code.
- **Odométrie du robot réel** : lignes droites bonnes, **rotations non reproductibles** (10 à
  32° d'erreur sur 360° selon l'essai, 15 nov.). Avant de toucher à la navigation ou aux
  facteurs `robot.odometry`, lire `docs/DEBUG_ODOMETRY.md` (essais, journaux, hypothèses).
- Entraînement sur le HPC de DTU : `scripts/hpc/` (testé de bout en bout le 14 nov.). Tout ce
  qui est lourd va dans `$BLACKHOLE`, jamais dans le dossier personnel (quota de 30 Go : une
  installation de PyTorch le remplit). Les variables d'environnement ne passent pas aux jobs :
  utiliser `scripts/hpc/submit.sh`. La file `gpuv100` exige un PyTorch en CUDA 12.6 (les
  versions CUDA 13 ne gèrent plus ces cartes) : c'est ce qu'installe `submit.sh --setup`.
- Pas de `cv2.imshow` (OpenCV sans interface graphique) : visualiser avec Rerun.

## Ce qui n'a pas encore tourné sur le vrai robot

Jamais exécuté sur le matériel : `LeKiwiRobot` dans `src/makai/robot/lekiwi.py`
(`make_client` marche, via la téléop), `scripts/preflight.py`, `build_real` dans
`src/makai/app.py`.

Jamais exécuté sur le matériel non plus, validé en simulation seulement (dim. 15) : la
mission qui balaie (`orchestrator/sweep.py`, `makai-mission --sweep`), ses deux usages
(Vacuum en rangées : la base n'a jamais glissé de côté sur une longue distance ; Scan : elle
n'a jamais avancé en faisant osciller son cap), le tracé de la
zone en conduisant le robot, la mission lancée
depuis la console (`robot/autopilot.py`, onglet Mission de `scripts/drive.py --link host`),
le recalage sur le marqueur d'une station, le choix du modèle selon l'objet
(`PickByCategory`), le détecteur v2 pendant un balayage. Mode d'emploi : `docs/NAVIGATION.md`.

Validé sur le robot le 14 novembre au soir, en mode filaire sur la Pi (`WiredBase`,
`robot.link: wired`) : la page de contrôle `scripts/drive.py` (conduite, caméras avant et
poignet, lecture du bras avec la calibration de la Pi, mesures des 9 moteurs). Pas encore sur
le robot : l'onglet Measure (déplacements précis, `src/makai/robot/moves.py`).

Validé de bout en bout avec un robot et un leader simulés (`--dry-run`,
`src/makai/robot/fake.py`), mais pas sur le matériel : `scripts/record.py` (création, ajout
d'une session, vidéos), `scripts/train.sh` (ACT en local), `PolicyPick` et
`scripts/try_pick.py` (chargement d'un checkpoint, commande à 29 Hz).

Validés sur le robot le sam. 14 : `scripts/teleop.py` (laptop Windows, leader en `COM8`),
`scripts/lekiwi_host.py` (sur la Pi).

Première exécution réelle prudente : vitesses réduites, bras dégagé. Retirer un élément de
cette liste une fois validé.

## Commandes

```bash
make setup | setup-lite     # installer tout | le cœur seulement
make check                  # lint + tests (ce que fait la CI)
make sim                    # les missions simulées : recherche sur place, Vacuum & collect, Scan & collect
uv run python scripts/drive.py --sim        # la console (Mission, Drive, Cameras, Data) avec un robot simulé
uv run python scripts/drive.py --link host  # la console sur le vrai robot (host lancé sur la Pi)
uv run python scripts/mission_check.py      # avant le robot : la mission démarre-t-elle avec cette config ?
make teleop | mission       # sur le robot (host lancé sur la Pi, voir docs/SETUP.md)
make markers | calibrate-ground
uv run python scripts/collect.py sock                   # LA commande de collecte : contrôle, enregistre, zippe
uv run python scripts/preflight.py                      # avant d'enregistrer (--dry-run sans robot)
uv run python scripts/record.py --name pick_sock_v1 --object sock --episodes 30    # relancer = ajouter
scripts/train.sh pick_sock_v1 act_sock_v1 --job.target=a10g-large                   # ou --policy.device=mps
uv run python scripts/try_pick.py --policy outputs/train/act_sock_v1/checkpoints/last/pretrained_model --trials 10
uv run python scripts/replay_check.py --policy <dossier pretrained_model>      # vérifier un modèle sans robot
uv run python scripts/hpc/run_logs.py                   # courbes et tableau des essais du cluster (docs/figures, docs/EXPLORATIONS.md)
```
