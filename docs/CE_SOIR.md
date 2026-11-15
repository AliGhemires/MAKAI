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

**C'est fait : le HPC de DTU est installé et testé** (14 nov., 21 h 10). Un job d'essai a démarré
12 secondes après sa soumission, s'est entraîné à 0,21 s par pas sur une V100, et son modèle
est revenu sur le laptop en 47 secondes. Aucun compte Hugging Face n'est nécessaire.

Reste à faire avant d'enregistrer :

- [ ] Ouvrir une connexion partagée au cluster, pour ne taper le mot de passe qu'une fois :
      `ssh -o ControlMaster=yes -o ControlPath=~/.ssh/cm-dtu -o ControlPersist=8h -fN dtu`
- [ ] Débit vers l'extérieur correct depuis le laptop qui enverra les données (partage de
      connexion : 0,6 à 4 Mo/s mesurés ; le WiFi de la salle est inutilisable)
- [ ] Solutions de repli prêtes, au cas où : chaque Mac qui entraînerait en local a fait
      `make setup`, a son chargeur, et possède `resnet18-f37072fd.pth` (45 Mo) dans
      `~/.cache/torch/hub/checkpoints/`

### Porte D · Répétition et contrôle

```bash
uv run python scripts/record.py --name repetition --object sock --episodes 2 --dry-run   # sans robot : apprendre les touches
uv run python scripts/preflight.py                                                       # avec le robot : tout doit être « ok »
```

## 2. Enregistrer

**Une seule commande par objet**, sur le laptop relié au leader :

```bash
uv run python scripts/collect.py sock --try     # d'abord : 2 épisodes d'essai, à regarder
uv run python scripts/collect.py sock           # 30 épisodes de chaussette (relancer pour 30 de plus)
uv run python scripts/collect.py can            # puis la canette
```

Elle contrôle le robot, les deux caméras et le leader ; si le robot ne répond pas, elle affiche
la commande exacte à lancer sur la Pi. Puis elle enregistre, et à la fin elle dépose sur le
Bureau un zip du dataset (`makai_pick_sock_v1.zip`) à transmettre à celui qui lance
l'entraînement.

### Le guide du pilote

**Le principe.** Le bras du robot copie en permanence le leader que tu tiens. L'enregistreur
ne garde que les moments marqués RECORDING. Un épisode, c'est une saisie complète : du repos
au repos. Entre deux épisodes rien n'est enregistré : tu as tout ton temps pour replacer
l'objet, souffler, ou régler la scène.

**La pose `home`.** C'est la pose du bras quand le leader est posé sur son support. Chaque
épisode en part et y revient.

- **Elle se définit au lancement** : leader sur son support, mains écartées, Entrée.
  L'enregistreur mesure la pose du bras pendant une seconde et l'affiche (`Home pose: ...`).
  Il n'y a rien d'autre à régler.
- **Laquelle choisir** : bras replié, pince ouverte, hors du champ de la caméra avant. Le
  robot roule, cherche les objets et transporte sa prise dans cette pose.
- **Elle ne doit plus bouger** : fixer le support du leader (scotch) et le laisser là. La
  première session d'un dataset garde sa pose dans le dossier du dataset (`makai_home.yaml`).
  Une session suivante qui part de plus de 10° ailleurs affiche HOME POSE DIFFERS : remettre le
  support en place et relancer.
- **Pour la mission** : le robot se met dans cette pose avant chaque saisie, et le modèle
  doit partir de la pose de ses démonstrations. Elle est dans `configs/arm_poses.yaml` depuis
  le 15 nov. (tirée de `pick_sock_v1`), pince comprise : notre leader repose pince fermée,
  donc revenir en `home` continue de serrer l'objet après une saisie.

**Où regarder.** Une seule ligne dit quoi faire : la dernière ligne du terminal, qui se met
à jour sur place. Le panneau « prediction.status » de la fenêtre Rerun affiche exactement les
mêmes mots, à côté des deux caméras. Au-dessus, le terminal garde une ligne par épisode
(sauvegardé, ou non et pourquoi), qui commence par `[sauvegardés / demandés]`.

```text
[ 7/30] SAVED          6.2 s. The dataset now holds 38 episodes
[ 7/30] RECORDING 9 s: AT HOME: hold still 0.4 / 1.0 s   [max 30 s, RIGHT ARROW = save now, LEFT ARROW = drop]
```

**Un épisode, pas à pas.** Commande : `uv run python scripts/collect.py sock`

| Ce que la ligne affiche | Ce que fait le pilote |
|---|---|
| `PRESS RIGHT ARROW` | poser l'objet, leader sur son support, puis flèche droite |
| `PUT THE LEADER ON ITS REST` | le bras n'est pas en `home` : la ligne dit quelle articulation, et de combien |
| `GO` | rien n'est encore enregistré : l'enregistrement part au premier mouvement du leader |
| `RECORDING 6 s` … `arm NOT at home` | saisir l'objet, puis ramener le leader sur son support |
| `AT HOME: hold still 0.4 / 1.0 s` | le bras est vu en `home` : ne plus bouger, le compteur monte jusqu'à 1 s |
| `SAVED` | l'épisode est sauvegardé : replacer l'objet, puis flèche droite pour le suivant |

Rien ne démarre sans la flèche droite, et rien n'est enregistré en dehors de RECORDING.
Chaque épisode part de `home`, sans temps mort au début, et finit par la même seconde immobile.

**Les touches.**

| Touche | Effet |
|---|---|
| Flèche droite | prépare un épisode (GO) ; pendant un épisode, le sauvegarde tout de suite |
| Flèche gauche | annule un GO ; pendant un épisode, le jette ; juste après une sauvegarde, marque cet épisode comme mauvais (la commande pour le supprimer s'affiche en fin de session) |
| Échap | termine la session ; un épisode en cours est jeté |

Si les touches ne font rien, cliquer une fois dans le terminal.

**Mode manuel** : `uv run python scripts/collect.py sock --manual`. L'enregistrement part à la
flèche droite elle-même, et seule la flèche droite sauvegarde. Appuyer juste avant de bouger et
dès le retour au repos : les secondes immobiles sont enregistrées avec le reste.

**Quand un épisode n'est pas sauvegardé**, la ligne `NOT SAVED` dit pourquoi : plus de
30 secondes (`--episode-time 60` pour élargir), flèche gauche, arrêt à la touche en moins
d'une seconde (un double appui), ou retour au repos en moins de 3 secondes.

**Si `AT HOME` ne vient pas au retour**, la ligne dit quelle articulation est trop loin, et de
combien. Reposer le leader comme au départ, ou sauvegarder à la flèche droite. Si l'écart
revient à chaque épisode, relancer avec une tolérance plus large : `--home-tol 15` (10 par
défaut).

Les lignes techniques de l'encodeur vidéo ne s'affichent plus : elles vont dans
`outputs/recordings/<nom>.log`.

**Épisodes enregistrés avant le 15 nov. à 2 h** : ouvrir `outputs/recordings/<nom>.csv` et
supprimer ceux qui durent moins d'une seconde (dernière colonne). Deux défauts, corrigés
depuis : une flèche pressée entre deux épisodes faisait sauvegarder le suivant presque vide ;
et sur le vrai robot, dont le bras suit le leader avec un léger retard, l'enregistreur se
réarmait tout seul et affichait des messages en rafale.

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

### Plan A · Sur le HPC de DTU

Testé de bout en bout le 14 nov., y compris les six essais lancés d'un coup. Une seule personne
a accès au cluster : c'est son laptop qui envoie les données et lance les entraînements.

**1. Celui qui a enregistré : transmettre les zips**

`scripts/collect.py` a déposé `makai_pick_sock_v1.zip` (et `makai_pick_can_v1.zip`) sur son
Bureau : les envoyer par AirDrop ou clé USB (100 à 300 Mo par objet).

**2. Sur le laptop qui a l'accès : tout lancer en une commande**

Déposer les zips dans `~/Downloads` ou sur le Bureau, puis :

```bash
ssh -o ControlMaster=yes -o ControlPath=~/.ssh/cm-dtu -o ControlPersist=8h -fN dtu    # mot de passe, une fois
scripts/hpc/tonight.sh
```

`tonight.sh` dézippe les datasets, les envoie au cluster, crée la copie « poignet seul », met
le code à jour là-bas et soumet les six essais dans l'ordre de priorité. Un dataset absent est
sauté avec ses essais : avec la chaussette seule, il lance les quatre essais de la chaussette.
Ne pas le relancer quand la canette arrive (les essais de la chaussette seraient soumis une
seconde fois) : lancer alors ceux de la canette à la main, sur le cluster (`ssh dtu`, puis
`cd ~/MAKAI`) :

```bash
scripts/hpc/submit.sh pick_can_v1 act_can_v1 STEPS=100000
scripts/hpc/submit.sh pick_can_v1 act_can_v1_aug STEPS=40000 AUGMENT=1
```

(après `scripts/hpc/push_dataset.sh pick_can_v1` depuis le laptop.)

Suivre les jobs : `ssh dtu bstat` (PEND = attend un GPU, RUN = s'entraîne), `ssh dtu bpeek <numéro>`.

**3. Dimanche matin, depuis le même laptop : rapatrier un modèle**

```bash
scripts/hpc/fetch_model.sh act_sock_v1 list       # quels checkpoints existent
scripts/hpc/fetch_model.sh act_sock_v1            # le dernier (200 Mo, moins d'une minute)
scripts/hpc/fetch_model.sh act_sock_v1 020000     # ou un pas précis
```

La commande affiche ensuite la ligne `try_pick.py` à lancer. Si l'essai se fait sur un autre
laptop, lui transmettre le dossier `outputs/train/<run>/checkpoints/<pas>/pretrained_model`.

**Le budget est de 8 heures, pas un nombre de pas.** À 0,21 s par pas (mesuré sur des images
de synthèse ; compter un peu plus avec de vraies images), 100 000 pas prennent 6 à 8 heures et
40 000 pas 2 h 30 à 3 h 30. Les jobs sont coupés à 8 heures ; un checkpoint est gardé tous les
5 000 pas, donc un entraînement coupé est simplement plus court.

À savoir sur ce cluster :
- la file `gpuv100` démarre vite ce soir : 12 secondes pour un job seul, quatre minutes pour
  que six jobs soumis ensemble aient tous démarré ; `gpul40s` a mis 15 minutes, et
  `gpua100`, `gpua10`, `gpua40` n'avaient pas démarré après 20 minutes. Rester sur `gpuv100` ;
- si un job reste en attente (`PEND`) plus de 20 minutes, le nombre de GPU par utilisateur est
  sans doute atteint : les suivants partiront quand les premiers finiront ;
- tout ce qui est lourd est dans l'espace de travail `$BLACKHOLE`, jamais dans le dossier
  personnel (quota de 30 Go) ;
- les variables d'environnement ne sont pas transmises aux jobs : toujours passer par
  `scripts/hpc/submit.sh`.

Repli si le cluster devient indisponible : **Hugging Face Jobs** (`scripts/train.sh <dataset>
<run> --job.target=a10g-large --job.timeout=8h`, compte et paiement requis, non testé), ou le
plan B.

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

Vérifié le 14 nov. sur le HPC de DTU, avec un vrai job : installation, soumission, entraînement
sur GPU, puis rapatriement du modèle et exécution sur le laptop.

Pas vérifié : tout ce qui touche au vrai matériel (liaison avec la Pi, caméras, leader),
l'envoi sur le Hub, et HF Jobs. La première session réelle est donc aussi un test : faire
2 épisodes, vérifier le dataset, puis seulement enchaîner les 30.
