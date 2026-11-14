# Ce soir : collecte et entraînement de nuit

Samedi 14 novembre. Objectif : **dimanche à 8 h, un modèle qui saisit la chaussette, et si
possible un second qui saisit la canette.** Tout ce qui suit sert cet objectif ; le reste
attend demain.

Objets de la démo : **une chaussette noire roulée et une canette écrasée** (à confirmer en
équipe). Un dataset et un modèle par objet : chaque modèle a un seul geste à apprendre, et
le détecteur dit déjà lequel utiliser.

## 1. Avant d'enregistrer : quatre portes

Dans l'ordre. On n'enregistre rien tant qu'une porte n'est pas passée.

### Porte A · Le robot est complet (WS1)

- [ ] Bras monté sur la base, caméra de poignet fixée sur la pince
- [ ] Bras du robot calibré **sur la Pi** : `lerobot-calibrate --robot.type=lekiwi --robot.id=makai_kiwi`
- [ ] Host lancé sur la Pi avec les **deux** caméras et `--host.connection_time_s=36000` (`docs/SETUP.md`, section 4)
- [ ] `configs/makai.yaml` : `robot.remote_ip` (172.20.10.3 sur le partage de connexion) et `robot.cameras` identiques à la commande du host
- [ ] Sur le laptop qui enregistre : `cp -R calibration/. ~/.cache/huggingface/lerobot/calibration/` (calibration du leader)
- [ ] `make teleop` : le bras suit le leader sans à-coups, les deux images sont nettes dans Rerun

Vérifié le 14 nov. : le code de liaison est identique entre LeRobot 0.7.0 (laptops) et la
version installée sur la Pi. Pas de conflit de version à craindre.

### Porte B · Le montage est figé

À partir d'ici, plus personne ne touche aux caméras ni à la pose de départ.

- [ ] Caméras serrées, photographiées sous deux angles (photos dans `assets/`), repères au marqueur
- [ ] **Pose `home`** choisie, capturée (`p` pendant la téléop) et copiée dans `configs/arm_poses.yaml`
- [ ] **Un support fixe pour le leader** (cale en carton, ruban) qui le remet toujours dans cette
      pose quand on le lâche. Indispensable : l'enregistrement démarre et s'arrête d'après cette pose
- [ ] **Zone de pré-saisie** : un rectangle de ruban de 6 × 6 cm là où le bras saisit le mieux
- [ ] **Gabarit en carton** qui s'appuie contre l'avant du robot et montre où est la zone : si le
      robot bouge, on retrouve la zone sans mesurer
- [ ] **Tapis de démo** posé et scotché à plat, si on en fait un (voir « Tenir dans une autre
      salle » plus bas) : on enregistre dessus, on fait la démo dessus
- [ ] 10 saisies d'essai par objet, non enregistrées. **Si la canette ne se saisit pas
      proprement 8 fois sur 10 à la main, on ne l'enregistre pas ce soir**

### Porte C · Le chemin d'entraînement existe

À faire pendant que WS1 finit le robot. C'est ce qui décide si on a un modèle demain.

- [ ] Débit mesuré depuis le laptop qui enverra les données (viser plus de 500 ko/s) :
      `curl -o /dev/null -m 15 -w "%{speed_download} octets/s\n" -L https://download.pytorch.org/models/resnet50-0676ba61.pth`
- [ ] `uv run hf auth login`, puis `hub.namespace` dans `configs/local.yaml`
- [ ] **Un GPU, à choisir parmi trois, et à tester maintenant :**
  - **DTU HPC** : se connecter (`ssh <identifiant>@login1.hpc.dtu.dk`, VPN de DTU depuis ici),
    puis faire l'installation décrite en tête de `scripts/hpc/train_act.lsf`. Gratuit, mais
    l'accès depuis l'extérieur et l'attente dans la file sont à vérifier ce soir, pas à minuit ;
  - **Hugging Face Jobs** : `uv run hf jobs hardware` dit si le compte y a accès. Payant, zéro installation ;
  - **GPU loué** (RunPod, Lambda) : payant, 15 minutes d'installation.
- [ ] Chaque Mac qui entraînera en local : `make setup` fait, chargeur branché, et le fichier
      `resnet18-f37072fd.pth` (45 Mo) présent dans `~/.cache/torch/hub/checkpoints/` (le
      télécharger maintenant, ou se le passer par AirDrop)

### Porte D · Répétition et contrôle

```bash
uv run python scripts/record.py --name repetition --object sock --episodes 2 --dry-run   # sans robot : apprendre les touches
uv run python scripts/preflight.py                                                       # avec le robot : tout doit être « ok »
```

## 2. Enregistrer

L'enregistrement est **mains libres** : aucune touche pendant les épisodes.

1. Au lancement : leader posé sur son support, mains écartées, Entrée. Cette pose devient `home`.
2. Le laptop dit « Ready » quand le bras est revenu en `home` et ne bouge plus : poser l'objet.
3. Dès que tu bouges le leader, l'épisode commence. Descendre, saisir, remonter, reposer le
   leader sur son support en tenant l'objet.
4. Après une seconde d'immobilité, l'épisode est sauvegardé et son numéro est annoncé.
   Lâcher l'objet, le replacer ailleurs dans la zone, et recommencer.

Chaque épisode part donc de la même pose, sans temps mort au début, et finit par la même
seconde immobile, sans que personne ait à y penser.

- **Flèche gauche** pendant un épisode : on le jette. Juste après une sauvegarde : il est marqué
  mauvais, et la commande pour le supprimer s'affiche en fin de session.
- Un épisode qui ne revient pas en `home` en 15 secondes est jeté tout seul (« Too long »).
- Si « Ready » ne vient jamais : le bras ne se stabilise pas assez près de `home`. Relancer avec
  `--home-tol 10`, ou revenir au mode classique avec `--manual` (flèche droite pour finir).

Le reste du protocole (`docs/DATA_COLLECTION.md`) ne change pas :

- un seul opérateur par objet, le même geste à chaque fois, sans hésitation ;
- l'objet change de place et d'orientation à chaque épisode, en **couvrant la zone
  régulièrement** : centre, quatre coins, quatre milieux de bord, et on recommence en tournant
  l'objet. Ni tout au centre, ni au hasard ;
- **ne pas toucher w a s d z x r f q** : ces touches font rouler la base ;
- les mains hors du champ des caméras dès que le leader bouge.

```bash
uv run python scripts/record.py --name pick_sock_v1 --object sock --episodes 30
uv run python scripts/record.py --name pick_sock_v1 --object sock --episodes 30    # la même commande ajoute 30 épisodes
uv run python scripts/record.py --name pick_can_v1  --object can  --episodes 30
uv run python scripts/record.py --name pick_can_v1  --object can  --episodes 30
```

Relancer la même commande **ajoute** des épisodes : rien n'est écrasé, et un plantage ne fait
perdre que l'épisode en cours. Les données sont sur le disque avant tout envoi ; si l'envoi
échoue, la commande pour réessayer s'affiche.

| Créneau | Quoi | Durée |
|---|---|---|
| 1 | Chaussette, 2 sessions de 30 | 45 min |
| 2 | Canette, 2 sessions de 30 | 45 min |
| 3 | Images pour le détecteur (voir plus bas) | 10 min |

Pause de 5 minutes entre deux sessions : les servos chauffent, l'opérateur aussi.

**Si le temps manque : la chaussette seule, 60 épisodes.** Un modèle qui marche sur un objet
vaut mieux que deux datasets à moitié faits. Dernier départ raisonnable : 23 h 30.

Avant de passer à l'entraînement, regarder 5 épisodes au hasard de chaque dataset
(`uv run lerobot-dataset-viz --help`, ou le visualiseur en ligne si le dataset est envoyé) :
images nettes, pas de main dans le champ, geste régulier.

### Images pour réentraîner le détecteur

Le détecteur actuel a appris sur des images de téléphone. Avec la caméra du robot :

```bash
uv run python scripts/teleop.py --save-front data/robot_frames/sock     # rouler 30 s autour de la chaussette
uv run python scripts/teleop.py --save-front data/robot_frames/can      # pareil pour la canette
uv run python scripts/teleop.py --save-front data/robot_frames/empty    # et pour le sol vide
```

Le réentraînement lui-même attend demain matin (10 minutes sur un Mac).

### Tenir dans une autre salle

La démo de lundi a lieu dans une autre salle, et on n'a pas de lampe. Ce qui change, ce n'est
pas seulement la lumière : **le sol et le décor aussi**, pour le détecteur comme pour la saisie.
Par ordre d'efficacité :

1. **Savoir ce soir** : quelle salle, quel sol, et quand on peut y entrer (dimanche ? lundi
   matin ?). Demander aux organisateurs maintenant : toute la suite en dépend.
2. **Enregistrer dans cette salle dès qu'on y a accès** : 20 à 30 épisodes par objet, ajoutés
   aux mêmes datasets (la même commande), puis un réentraînement. Rien ne vaut des données du
   lieu de la démo.
3. **Emporter notre sol : un tapis de démo.** Des cartons dépliés, scotchés bord à bord et au
   sol, environ 1,5 × 1,5 m, mats et sans plis (les roues doivent rouler dessus). On enregistre
   dessus ce soir et on le pose dans la salle de démo : la caméra de poignet voit alors le même
   sol partout. À défaut d'accès à la salle, c'est la parade la plus sûre.
4. **Varier plutôt que répéter.** Sans tapis ni accès : enregistrer en deux endroits et sous deux
   lumières (ce soir, puis dimanche matin près d'une fenêtre), 30 épisodes par condition. Un
   modèle qui a vu plusieurs sols apprend à ne pas s'y fier.
5. **Un modèle qui ne regarde que la caméra de poignet** (essai 6). La caméra avant voit les
   murs et les gens, qui changeront ; celle du poignet ne voit presque que l'objet et la pince.
   ```bash
   scripts/wrist_only.sh pick_sock_v1        # crée le dataset pick_sock_v1_wrist
   ```
   puis l'entraîner comme les autres. Aucun changement côté robot.
6. **La variante `AUGMENT=1`** : luminosité de ×0,5 à ×1,5, contraste et couleurs au hasard.
7. **Réentraîner le détecteur dans la salle** : trois vidéos de 30 secondes avec la caméra du
   robot (`teleop.py --save-front`), dix minutes d'entraînement. Prévu pour ça.
8. **Répéter dans la salle** aussitôt que possible, à l'heure de la démo si on peut.

Une lampe (frontale, lampe USB, vélo) fixée sur le robot aiderait encore : si une autre équipe
ou les organisateurs en ont une, la prendre, et l'allumer pour toute la collecte.

## 3. Lancer l'entraînement avant de dormir

Mesures du 14 nov. : sur un Mac M5, ACT avance à **2 secondes par pas** (batch 8). Un GPU
loué va environ 10 fois plus vite.

### Plan A · Sur un GPU distant (si la porte C est passée)

Dans tous les cas le dataset doit d'abord être sur le Hub (`record.py` l'envoie en fin de
session), et les checkpoints y reviennent tous les 5 000 pas. **Six essais, par ordre de
priorité** ; le pourquoi de chacun est dans `docs/TRAINING.md`, section « Protocole ».

Sur le **HPC de DTU**, depuis le dossier `MAKAI` d'un nœud de connexion :

```bash
export HUB_NAMESPACE=<namespace> STEPS=100000
DATASET=pick_sock_v1 RUN=act_sock_v1 bsub < scripts/hpc/train_act.lsf                    # 1
DATASET=pick_can_v1  RUN=act_can_v1  bsub < scripts/hpc/train_act.lsf                    # 2
export STEPS=40000                                                                       # les variantes
AUGMENT=1 DATASET=pick_sock_v1 RUN=act_sock_v1_aug bsub < scripts/hpc/train_act.lsf      # 3
AUGMENT=1 DATASET=pick_can_v1  RUN=act_can_v1_aug  bsub < scripts/hpc/train_act.lsf      # 4
EXTRA="--policy.chunk_size=50 --policy.n_action_steps=50" DATASET=pick_sock_v1 RUN=act_sock_v1_c50 bsub < scripts/hpc/train_act.lsf   # 5
DATASET=pick_sock_v1_wrist RUN=act_sock_v1_wrist bsub < scripts/hpc/train_act.lsf        # 6 (après scripts/wrist_only.sh pick_sock_v1)
bstat          # en attente ou en cours ?
```

**Le budget est de 8 heures, pas un nombre de pas.** Les deux essais de référence visent
100 000 pas et sont coupés à 8 heures : on prend le dernier checkpoint disponible au réveil
(il y en a un sur le Hub tous les 5 000 pas). Les variantes s'arrêtent à 40 000 pas pour
libérer les GPU. S'il n'y a qu'un ou deux GPU libres, mettre 40 000 partout, dans l'ordre 1 à 6.

Le script de soumission n'a pas pu être testé d'ici : si un job reste en attente plus de 20
minutes ou échoue au démarrage, basculer sans insister sur l'une des deux autres voies.

Avec **Hugging Face Jobs**, depuis un laptop :

```bash
export STEPS=100000
scripts/train.sh pick_sock_v1 act_sock_v1 --job.target=a10g-large --job.timeout=8h       # 1
scripts/train.sh pick_can_v1  act_can_v1  --job.target=a10g-large --job.timeout=8h       # 2
export STEPS=40000                                                                       # les variantes
AUGMENT=1 scripts/train.sh pick_sock_v1 act_sock_v1_aug --job.target=a10g-large          # 3
AUGMENT=1 scripts/train.sh pick_can_v1  act_can_v1_aug  --job.target=a10g-large          # 4
scripts/train.sh pick_sock_v1 act_sock_v1_c50 --job.target=a10g-large --policy.chunk_size=50 --policy.n_action_steps=50   # 5
scripts/train.sh pick_sock_v1_wrist act_sock_v1_wrist --job.target=a10g-large            # 6 (après scripts/wrist_only.sh pick_sock_v1)
```

Sur une **machine louée** : la même commande avec `--policy.device=cuda` à la place de `--job.target`.

### Plan B · Sur nos Mac, sans réseau

Un Mac par objet, dataset copié dessus (AirDrop du dossier
`~/.cache/huggingface/lerobot/<namespace>/makai_pick_sock_v1`, à remettre au même endroit).

```bash
STEPS=15000 SAVE_FREQ=2500 scripts/train.sh pick_sock_v1 act_sock_v1 --policy.device=mps
```

15 000 pas prennent 8 heures (1,9 s par pas, mesuré) et font environ 8 passages sur 60 épisodes
de 8 secondes. Le script empêche le Mac de se mettre en veille ; **laisser le chargeur branché
et l'écran ouvert.** Inutile de changer la taille de batch (16 ne va pas plus vite) ni
d'activer la précision mixte (elle plante sur Mac).

### Dans les deux cas

- [ ] Attendre les 200 premiers pas : la perte (`loss`) doit baisser. Sinon, arrêter et chercher pourquoi
- [ ] Noter dans `docs/REGISTRY.md` : datasets, commandes lancées, heure
- [ ] Batterie du robot en charge, robot éteint
- [ ] Dormir. Au moins 5 heures

## 4. Dimanche à 8 h

```bash
uv run python scripts/try_pick.py --policy outputs/train/act_sock_v1/checkpoints/last/pretrained_model --trials 10
```

(ou `--policy <namespace>/makai_act_sock_v1 --revision 020000` pour un checkpoint sur le Hub.)

Ordre des essais, toujours sur la même grille de 10 positions (centre et quatre coins de la
zone, deux orientations) :

1. le modèle de référence de la chaussette, checkpoint final ;
2. ses checkpoints 10 000 et 20 000 : parfois meilleurs que le dernier ;
3. le meilleur des trois avec `--n-action-steps 50` puis `25` ;
4. la variante augmentée, puis l'horizon court ;
5. la canette, de la même façon.

Chaque résultat dans `docs/REGISTRY.md`, avec la façon dont ça échoue.

- 7 sur 10 ou plus : on intègre ce modèle dans la mission.
- Entre 4 et 6 : 20 épisodes de plus sur les cas ratés, puis réentraînement.
- Moins de 4 à 10 h : la démo passe en saisie scriptée (`pick.kind: scripted`), et la policy
  continue en parallèle.

Première exécution d'un nouveau modèle : bras dégagé, une main près de l'interrupteur.

## Ce qui est vérifié, et ce qui ne l'est pas

Vérifié le 14 nov. sans robot, avec un robot et un leader simulés :
- `record.py` crée un dataset, y ajoute une seconde session, encode les vidéos ;
- `train.sh` entraîne ACT sur ce dataset et sauvegarde un checkpoint ;
- `try_pick.py` et la mission chargent ce checkpoint et commandent le bras à 29 Hz.

Pas vérifié : tout ce qui touche au vrai matériel (liaison avec la Pi, caméras, leader),
l'envoi sur le Hub, et HF Jobs. La première session réelle est donc aussi un test : faire
2 épisodes, vérifier le dataset, puis seulement enchaîner les 30.
