# Architecture

Un seul processus Python, sur un laptop, pilote le robot. Pas de ROS : pour trois jours,
un processus et des contrats clairs vont plus vite.

## Vue d'ensemble

```
laptop « cerveau »                                        Raspberry Pi 5 (sur le robot)
┌───────────────────────────────────────────────┐         ┌──────────────────────────┐
│ makai.app  →  Mission (machine à états)       │  ZMQ    │ lerobot lekiwi_host      │
│   ├─ Perception   (détecteur, sol, marqueurs) │ ◄─────► │  ├─ 9 servos Feetech     │
│   ├─ ApproachController, Odometry             │  WiFi   │  ├─ caméra avant (C270)  │
│   ├─ PickSkill    (policy ACT ou scripté)     │         │  └─ caméra poignet       │
│   └─ DropSkill    (poses scriptées)           │         └──────────────────────────┘
│ LeKiwiRobot  →  lerobot.LeKiwiClient          │
└───────────────────────────────────────────────┘
```

La Pi ne fait que relayer : elle lit les moteurs et les caméras et applique les commandes.
Toute l'intelligence (détection, policy) tourne sur le laptop.

## Modules et responsables

| Module | Rôle | WS |
|---|---|---|
| `makai/contracts.py` | Types et interfaces partagés | tous (fichier protégé) |
| `makai/robot/lekiwi.py` | Adaptateur vers LeRobot | WS1 |
| `makai/perception/` | Image → objets et stations en mètres | WS2 |
| `makai/navigation/` | Approche, odométrie | WS3 |
| `makai/sim/` | Simulateur 2D pour tester sans robot | WS3 |
| `makai/manipulation/skills.py` | Saisie et dépôt | WS4 |
| `makai/orchestrator/mission.py` | Machine à états | WS5 |
| `makai/app.py` | Point d'entrée `makai-mission` | WS5 |

## Les contrats

Tout passe par `makai/contracts.py`. Tant que ces signatures ne bougent pas, chacun peut
réécrire son module sans gêner les autres.

```python
Robot.get_observation() -> Observation      # images, angles du bras, vitesse de la base
Robot.drive(BaseVelocity)                   # commande la base, le bras tient sa position
Robot.move_arm({"arm_gripper.pos": 40.0})   # commande le bras, la base s'arrête
Robot.stop()

Perception.perceive(Observation) -> Scene   # Scene.targets, Scene.stations
PickSkill.run(robot, target) -> bool        # bloquant ; True si l'objet est tenu
DropSkill.run(robot, category) -> bool      # bloquant
```

Chaque contrat a deux implémentations : la vraie et celle du simulateur.

| Contrat | Réel | Simulation |
|---|---|---|
| `Robot` | `LeKiwiRobot` | `SimRobot` |
| `Perception` | `CameraPerception` | `SimPerception` |
| `PickSkill` | `PolicyPick`, `ScriptedPick` | `SimPick` |
| `DropSkill` | `ScriptedDrop` | `SimDrop` |

## Repères et unités

- **Repère base** : origine au centre de la base, au sol. `x` vers l'avant, `y` vers la
  gauche, angles positifs dans le sens anti-horaire.
- Distances en **mètres**, vitesses en **m/s**, rotations en **rad/s** dans notre code.
- LeRobot utilise des **degrés** pour le bras et des **deg/s** pour `theta.vel` : la
  conversion se fait dans `makai/robot/lekiwi.py` et nulle part ailleurs.
- Images : `HxWx3`, `uint8`, **RGB**.
- Clés du bras, telles que LeRobot les nomme : `arm_shoulder_pan.pos`, `arm_shoulder_lift.pos`,
  `arm_elbow_flex.pos`, `arm_wrist_flex.pos`, `arm_wrist_roll.pos`, `arm_gripper.pos`.

## La machine à états

```
              ┌──────────────────────────────────────────────────────────────┐
              ▼                                                              │
          SEARCH ──objet vu──► APPROACH ──arrivé──► PICK ──tenu──► FIND_STATION
            │  ▲                  │                  │                  │
   rien vu  │  │ perdu / timeout ─┘     échec ──► APPROACH (≤ 3 fois)   │ station vue
            ▼  │                                     │                  ▼
   loin du départ ? ──oui──► RETURN_HOME             └─abandon─► BACK_OFF ◄── DROP ◄── GO_TO_STATION
            │ non
            ▼
          DONE                         FAILED : station introuvable, trop d'échecs, durée dépassée
```

Comportements à connaître :

- **Suivi de l'objet** : pendant l'approche, la position de l'objet est recalée à chaque
  détection et propagée par l'odométrie entre deux détections.
- **Zone aveugle** : en dessous de `blind_below_x_m`, l'objet peut sortir du champ de la
  caméra ; la mission continue sur la position propagée pendant `blind_timeout_s` au plus.
- **Retour au départ** : si rien n'est visible et que le robot est loin de son point de
  départ, il y revient avant de conclure que la pièce est propre.
- **Objets près d'une station** : ignorés, ils sont considérés comme déjà rangés.
- Tous les seuils sont dans `MissionConfig`, réglables depuis `configs/makai.yaml`
  (`navigation.mission`).

Limite assumée : il n'y a **pas d'évitement d'obstacles**. La scène de démo est disposée
pour que le robot n'ait pas à contourner quoi que ce soit.

## Estimer la distance avec une seule caméra

Un objet posé au sol, vu par une caméra fixée au robot : le pixel du bas de sa boîte
englobante correspond à un seul point du sol. Une homographie donne ce point en mètres.

- Au départ : `CameraModel` (hauteur, inclinaison, champ de vision mesurés à la règle)
  donne une homographie approchée.
- Pour la démo : `makai-calibrate-ground` l'ajuste sur une feuille de marqueurs posée au
  sol, sans cliquer. Viser une erreur moyenne sous 5 mm.

### Le compromis de la caméra avant (à trancher samedi, porte G2)

La C270 a un champ étroit : 55° en diagonale, soit environ 46° en horizontal et 35° en
vertical. Avec un champ si étroit, on ne peut pas voir à la fois loin et tout près :

| Montage (objectif à 20 cm du sol) | Sol visible devant la caméra | Conséquence |
|---|---|---|
| Inclinée de 35° vers le bas | de 15 cm à 63 cm | Voit la zone de saisie, mais presque rien de la pièce |
| Inclinée de 20° vers le bas | de 26 cm à plus de 4 m | Voit la pièce et les marqueurs, pas la zone de saisie |

Choix recommandé : **inclinaison d'environ 20°, caméra basse**, et la fin de l'approche à
l'odométrie (c'est déjà codé et testé en simulation). Les marqueurs des stations doivent
être collés **au ras du sol**, sinon ils sortent du haut de l'image dès qu'on s'approche.

Si la caméra de poignet a un grand angle, une option plus précise existe : bras en pose
`home`, elle regarde la zone de saisie et sert à l'alignement final. À n'envisager que si
l'odométrie ne suffit pas (mesure : 9 arrivées sur 10 à ±2 cm).

## La pose de pré-saisie

C'est le point du repère base où l'objet doit se trouver avant de lancer la saisie
(`navigation.approach.goal_x_m`, `goal_y_m`). Elle doit être :

- atteignable confortablement par le bras, pince verticale ;
- identique pendant la collecte et pendant la démo ;
- choisie une fois, samedi, puis figée (décision à noter dans `docs/DECISIONS.md`).

## Faits vérifiés sur LeRobot 0.7.0

Vérifiés dans le code installé, le 14 novembre :

- Le client attend le host sur la Pi : `python -m lerobot.robots.lekiwi.lekiwi_host`.
  Par défaut **le host s'arrête au bout de 30 secondes** : toujours passer
  `--host.connection_time_s=36000`.
- Le host exige les trois clés `x.vel`, `y.vel`, `theta.vel` dans chaque commande ; les
  articulations du bras absentes de la commande gardent leur consigne.
- Sans commande pendant 0,5 s, le host arrête la base tout seul. Un calcul lent côté
  laptop immobilise donc le robot au lieu de le laisser filer.
- Signes : `x.vel` positif avance, `y.vel` positif va à gauche, `theta.vel` positif tourne
  à gauche.
- `lerobot-rollout` remplace l'ancien script d'évaluation ; `--strategy.type=dagger`
  permet de corriger la policy à la main pendant qu'elle tourne.
- `lerobot-train --job.target=<gpu>` lance l'entraînement sur Hugging Face Jobs.

Non vérifié sur le matériel (aucun robot branché au moment d'écrire) : tout ce qui est
dans `makai/robot/lekiwi.py`, `PolicyPick` et `scripts/`. Les imports et signatures sont
contrôlés, le comportement réel est à valider par WS1 et WS4 à la première connexion.
