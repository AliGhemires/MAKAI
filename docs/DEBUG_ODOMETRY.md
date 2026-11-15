# Débogage navigation : odométrie, rotations, flux du robot (15 nov.)

Pour une analyse logicielle et matérielle en profondeur. Écrit à partir des journaux du laptop
d'Amine (Windows) et de la Pi, et des mesures faites au mètre par l'équipe le 15 nov. entre
16 h et 17 h 40. Tous les fichiers cités sont dans `docs/logs/odometry/`.

> **Mise à jour du 15 nov., 19 h 40 : résultats sur le robot à la section 11.** Avec les
> codeurs de roues, la rotation est reproductible : une échelle stable de 0,947 (9 tours,
> 0,944 à 0,953), corrigée dans `robot.odometry.angular_scale` ; après correction, 1° d'écart
> par tour. Trouvé en route : la caméra du robot ne voit pas les bandes de scotch des
> cartons (§11.3), ce qui touche la disposition « poubelle en face ».

> **Mise à jour du 15 nov., 18 h : analyse en profondeur à la section 10.** Deux défauts du
> logiciel trouvés et corrigés (odométrie comptée sur les codeurs de roues, saut de cap après
> chaque saisie), `angular_scale` remis à 1.0, et un test automatique à la caméra
> (`scripts/turn_check.py`) qui remplace le mètre. À faire sur le robot : la section 10.4.

## 1. En bref

- **Le problème ouvert : les rotations ne sont pas reproductibles.** Quatre quarts de tour à
  gauche (360°) finissent à moins de 1,5° de leur cible selon l'odométrie, mais le robot réel
  se trompe de **10° à 32° selon l'essai**, avec les mêmes réglages. Aucun facteur d'échelle ne
  colle à tous les essais (§4.3).
- **Les lignes droites vont bien** : 2 cm d'écart latéral sur 90 cm ; distance réelle 2,2 %
  sous l'odométrie (corrigé, `linear_scale: 0.978`).
- **Corrigé en route** : retard des images de 2,5 s et odométrie qui comptait les virages deux
  fois (la console lisait le flux à 10 Hz), bras pas en position home au départ d'une mission,
  dépassements des déplacements précis (§3).
- **Non validé, à revoir** : `robot.odometry.angular_scale: 1.039` dans `configs/makai.yaml`. Il
  vient de mesures incohérentes entre elles (§4.3). Le remettre à 1.0 tant que la cause des
  rotations n'est pas trouvée est une option défendable.
- **Exclu** : erreurs de lecture sur le bus moteur, alimentation de la Pi, réseau, file
  d'attente du flux (§5).

## 2. Configuration au moment des tests

| Élément | Valeur |
|---|---|
| Pi | Raspberry Pi 5, Debian 13 (trixie), noyau 6.18.50+rpt-rpi-2712, Python 3.12.16 |
| LeRobot sur la Pi | 0.7.1 (dépôt `~/lerobot`, commit fe1c5459 du 13 nov.), env conda `lerobot` |
| Host | `~/makai_host.py` = `scripts/lekiwi_host.py` (accélération du bras 50), 2 caméras 640×480 MJPG 30 fps, `connection_time_s=36000`, dans tmux `host` |
| Bus moteurs | `/dev/ttyACM0`, QinHeng 1a86:55d3 ; bras 1–6, roues 7 (gauche), 8 (arrière), 9 (droite), STS3215 12 V |
| Caméras | avant `/dev/video0` (« GENERAL WEBCAM » 1b3f:2247, caméra d'origine du LeKiwi), poignet `/dev/video2` (« Generic USB HD Camera » 1e45:8022) |
| Réseau | option A : la Pi est le point d'accès « makai-kiwi » (5 GHz, canal 36), laptop en Wi-Fi dessus, Internet par USB ; aller-retour 6 ms, flux 30 obs/s (`docs/ROBOT_NETWORK.md`) |
| Laptop | Windows 11, CPU (PyTorch CPU, RTX 4060 non utilisée), console `scripts/drive.py --link host` |
| Odométrie (mode host) | source « measured speed » : vitesses `x.vel`, `y.vel`, `theta.vel` calculées par LeRobot sur la Pi à partir de `Present_Velocity` des roues, avec ses valeurs intégrées (roue 0,05 m, base 0,125 m) ; intégrées sur le laptop (`navigation/odometry.py`) avec l'heure d'arrivée (`time.monotonic()` du laptop) |
| Sol | revêtement granuleux (caoutchouc/liège), voir les photos `docs/figures/camera_calibration_*.jpg` |
| Batterie | 9,7 V après la collecte (nuit), 10,8 V après une heure de charge, **10,6–10,8 V à 16 h 20** ; pas remesurée pendant les essais (§6, H2) |

État complet de la Pi au moment de l'écriture : `pi_state_and_host_log.txt`. Configuration du
laptop (hors git) : `laptop_local_config.yaml`.

## 3. Ce qui a été trouvé et corrigé dans la journée

| Heure | Symptôme | Cause mesurée | Correction (commit) |
|---|---|---|---|
| 16 h 05 | Images 2,5 s en retard ; zone tracée en triangle ; cap affiché 762° après un tour | Le host envoie 30 obs/s, la console n'en lisait que 10 (2 au plus par lecture) : **2,7 Mo en attente sur la Pi**. Les vitesses des roues, prises dans ce flux en retard, étaient intégrées sur le temps du laptop : une seconde de mouvement comptée 2 à 3 fois | Console lit le flux à chaque tour de boucle (50 Hz) : file 0–200 ko, 29 images/s (`9a4666b`) |
| 16 h 20 | Bras tendu pendant la navigation | La mission ne mettait jamais le bras en home au départ ; après un redémarrage du host, il restait où il était tombé | Bras en home (2 s) au premier pas de chaque mission (`1b27686`) |
| 16 h 40 | Zone 100 × 200 cm tracée avec l'onglet Measure : 22,5 cm devant et 12,5 cm à côté du départ | Les déplacements précis ne reculent jamais (exprès) : chaque virage de 90° a dépassé de 2,6° en moyenne (+10,5° sur la boucle), chaque ligne de ~1 cm. Rejoué depuis `move_trials_measure_tab.csv` : 19 cm et 9 cm de l'erreur viennent de là | Déplacements « exacts » fermés dans les deux sens (`GoTo`, `/api/goto`), quarts de tour sur un cap absolu (`5970d3e`) |
| 17 h 10–17 h 23 | Rotations fausses de 10 à 32° | Voir §4 : non résolu | Facteurs d'odométrie (`e164a5f`, `ebf6e80`), rampe d'accélération en rotation (`7e69025`) |

## 4. Les essais de rotation et de distance

### 4.1 Mesures au mètre (rapportées par l'équipe)

| # | Heure | Réglages | Essai | Mesure au sol | Angle réel déduit | Côté |
|---|---|---|---|---|---|---|
| L1 | 16:57 | onglet Measure, `linear_scale` 1.0 | 100 cm tout droit | 98,5 cm (odométrie 100,89) | — | — |
| L2 | 17:00 | idem | 100 cm tout droit | 99,0 cm (odométrie 100,96) | — | — |
| R1 | 17:04 | `GoTo`, `angular_scale` 1.0 | 4 × ⟲ 90° puis 3 × 30 cm le long d'une ligne de scotch | 25 cm de la ligne à 90 cm | 15,5° | « à droite », sens ambigu |
| R2 | 17:12 | `angular_scale` 0.961 | idem | 48 cm à 90 cm | 28,1° | non dit |
| R3 | 17:15 | `angular_scale` 1.039 | idem | 17 cm à 90 cm | 10,7° | non dit |
| B | 17:19 | idem | 90 cm tout droit, sans rotation | 2 cm de la ligne | 1,3° | non dit |
| A | 17:20 | idem | 4 × ⟲ 90°, sans avancer ; règle contre l'avant, mesure à 50 cm | 8,7 cm | 9,9° | non dit |
| R4 | 17:27 | idem + rampe de rotation (`7e69025`) | 4 × ⟲ 90° puis 50 cm (onglet Measure) | 32,5 cm de côté, 52,5 cm devant | ~32° | non dit |

Le côté n'a été donné qu'une fois, et lu à l'envers la première fois (« à droite » vu de face,
pas dans le sens du robot) : d'où le facteur 0.961, qui a doublé l'erreur (R2).

### 4.2 Ce que dit l'odométrie pour les mêmes essais (`goto_log_exact_moves.csv`)

Chaque quart de tour finit à 1,0–1,3° **en deçà** de sa cible (tolérance de `GoTo` 1,5°), toujours
du même côté : 88,9 / 178,7 / 268,7 / 358,7° pour R1, et des valeurs à 0,3° près pour R3, A, R4.
Les lignes droites tiennent le cap à ±1°. **Selon l'odométrie, les essais sont identiques ; sur le
sol, ils ne le sont pas.** Le journal du 17:25 contient aussi un tour complet dans le sens horaire
(−90 à −360°) dont le résultat au sol n'a pas été noté.

### 4.3 Pourquoi aucun facteur ne marche

Si l'erreur venait d'une échelle fixe k (robot réel = k × odométrie brute), la console visant
360° corrigés, l'angle réel vaudrait 360 × (k / s − 1) pour un réglage s. En supposant que
l'erreur est toujours du même côté :

| Essai | s | k déduit |
|---|---|---|
| R1 | 1.0 | 1,045 |
| R2 | 0.961 | 1,032 |
| R3 | 1.039 | 1,070 |
| A | 1.039 | 1,068 |
| R4 | 1.039 + rampe | ~1,13 |

L'écart (1,03 à 1,13) est bien plus grand que l'incertitude de lecture (±2 cm, soit ±1,5°). Si
certains essais étaient de l'autre côté, les k changent mais restent incohérents (R1 donnerait
0,958, A 1,010). **Conclusion : l'erreur de rotation n'est pas (seulement) une échelle ; elle varie
d'un essai à l'autre.**

## 5. Ce qui est exclu, et comment

| Hypothèse | Preuve |
|---|---|
| Erreurs de lecture sur le bus moteur (paquets perdus, vitesses manquantes) | `host.log` : 45 862 lignes, uniquement « No command available » et le chien de garde ; aucune erreur, aucun « status packet », aucune relecture (`pi_state_and_host_log.txt`) |
| Alimentation de la Pi | `throttled=0x0`, 5,09 V en entrée, 2 h 17 sans redémarrage pendant les essais |
| File d'attente du flux | Corrigée à 16 h 18 ; mesurée ensuite : 0–200 ko en attente, 29–30 obs/s |
| Réseau | Option A : 6 ms d'aller-retour, aucun trou de plus de 53 ms en 20 s |
| Commande des déplacements | `GoTo` atteint ses cibles selon l'odométrie (§4.2), en simulation la boucle 1 × 2 m se referme à 1,8 cm / 1,1° avec retard moteur et mesure en retard de 60 ms (`tests/test_bases.py`) |

## 6. Hypothèses ouvertes, et l'essai qui tranche

| # | Hypothèse | Pour | Contre | Essai qui tranche |
|---|---|---|---|---|
| H1 | **Glissement des roues en rotation**, variable selon le sol, la vitesse, l'accélération | Lignes droites bonnes, rotations mauvaises ; erreur variable ; sol granuleux, roues omni | La rampe (R4) n'a pas aidé | Même essai sur un sol lisse ; rotation plus lente (`GoToTuning.max_ang_rad_s` 0,6 → 0,3) |
| H2 | **Batterie basse** : couple plus faible, roues qui ne répondent pas pareil | ~10,7 V ou moins, robot qui a beaucoup roulé ; arrêts de la Pi les jours précédents | Aucune erreur de bus | Recharger, mesurer (procédure batterie, `docs/SETUP.md`), refaire A trois fois |
| H3 | **Mesure au sol** : côté ambigu, règle contre l'avant (le robot se décale en tournant), dérive de la ligne droite mêlée à la rotation | Méthodes différentes d'un essai à l'autre ; côté souvent non noté | B et A donnent des ordres de grandeur proches | Téléphone posé sur le robot, appli boussole ou gyroscope : cap avant et après 360°, trois fois, signe compris |
| H4 | **Odométrie par la vitesse mesurée** (mode host) : vitesses à 30 Hz, horodatées à l'arrivée sur le laptop, intégrées en « bloqueur d'ordre zéro » ; `Present_Velocity` des STS3215 peu précise aux basses vitesses | Erreur aléatoire possible si les mesures arrivent en paquets | Flux régulier depuis 16 h 18 | Même essai **en mode filaire** sur la Pi (`python scripts/drive.py --link wired`, odométrie par les codeurs, `WheelOdometry`) avec l'onglet Measure : si les rotations y sont reproductibles, c'est le chemin « vitesse mesurée » qui pèche |
| H5 | **Centre de rotation décalé, galets usés ou roue mal alignée** : le robot se translate en tournant | R4 : 52,5 cm « devant » pour 50 demandés, 32,5 cm de côté | — | Marquer le sol sous le centre de la base, tourner 360° sur place, mesurer de combien le centre a bougé ; inspecter les galets des trois roues |
| H6 | **Constantes de LeRobot** (rayon de roue, de base, angles) fausses pour ce robot | Expliquerait une échelle fixe | N'explique pas la variation | Mesurer au pied à coulisse ; onglet Measure en filaire, qui propose `wheel_radius_m` et `base_radius_m` |
| H7 | **Chien de garde du host** : 226 arrêts « Command not received for more than 500 ms » pendant la session, sans heure | Un arrêt brutal en pleine rotation provoque un glissement | Probablement aux moments sans console connectée | Horodater `host.log` (`logging` avec `%(asctime)s` dans `scripts/lekiwi_host.py`) et compter les arrêts pendant un essai |

## 7. Pistes de correction

- **Logiciel** :
  - remettre `angular_scale` à 1.0 tant que H1–H5 ne sont pas tranchées ;
  - si H4 se confirme, envoyer les positions des codeurs de roues dans l'observation du host
    (`scripts/lekiwi_host.py`) et intégrer côté laptop avec `WheelOdometry` comme en filaire, en
    gardant `raw_observation` intact pour les politiques ;
  - si H1 se confirme, s'appuyer sur le recalage au marqueur de la poubelle (`orchestrator/sweep.py`,
    `_anchor`), qui corrige position et cap à chaque dépose, et faire `recheck_after_m` plus court ;
  - tracer la zone sans tourner (avant, côté, arrière avec ← →), ou la mesurer et l'écrire dans
    `configs/local.yaml` (`navigation.sweep.room`).
- **Matériel** : batterie chargée, galets et vis des roues, alignement des roues, sol de la démo.

## 8. Reproduire

```powershell
# Pi : host (tmux host), option A ; laptop : Wi-Fi « makai-kiwi », Internet par USB
uv run python scripts/drive.py --link host      # console : http://localhost:8000
```

- Onglet Mission : Trace zone → ⟲ 90° ×4 → Cancel (rotation seule) ; Precise move ↑ (ligne droite).
- Chaque déplacement exact s'ajoute à `data/goto_log.csv`, chaque déplacement de l'onglet Measure à
  `data/move_trials.csv` (avec la mesure au mètre si on la saisit).
- Mode filaire pour H4 : sur la Pi, host arrêté, `cd ~/MAKAI && git pull && python scripts/drive.py --link wired`,
  puis `http://10.42.0.1:8000`, onglet Measure.

## 9. Fichiers

| Fichier | Contenu |
|---|---|
| `docs/logs/odometry/move_trials_measure_tab.csv` | Déplacements de l'onglet Measure : cible, odométrie, mètre, dérive, durée, réglages |
| `docs/logs/odometry/goto_log_exact_moves.csv` | Déplacements exacts : départ, cible, arrivée selon l'odométrie, durée |
| `docs/logs/odometry/move_trials_sim.csv` | Les mêmes en simulation |
| `docs/logs/odometry/pi_state_and_host_log.txt` | État de la Pi, du réseau, des caméras, et `host.log` résumé |
| `docs/logs/odometry/laptop_local_config.yaml` | `configs/local.yaml` et les poses de test du laptop |

Code concerné : `src/makai/robot/manual.py` (boucle de la console, `DriveLoop`, bases, `go_relative`),
`src/makai/robot/moves.py` (`PreciseMove`, `GoTo`, `TrialLog`), `src/makai/robot/lekiwi.py`
(conversion des unités, `speed_scale`), `src/makai/navigation/odometry.py`,
`src/makai/robot/drive_server.py` (routes), `src/makai/robot/console_page.html`,
`scripts/lekiwi_host.py`.

Commits du 15 nov. sur ces sujets : `9a4666b` (flux), `1b27686` (bras home), `94d316f` (quarts de
tour), `457f463` (bases), `5970d3e` (déplacements exacts), `c146340` (journal), `e164a5f` et
`ebf6e80` (facteurs d'odométrie), `7e69025` (rampe en rotation).

## 10. Analyse en profondeur (15 nov., 18 h)

Faite sans le robot, à partir des journaux ci-dessus, du code, et de nos épisodes de saisie
enregistrés (qui contiennent les vitesses de roues lues sur ce robot).

### 10.1 Ce que disent les données

**Les mesures au mètre se contredisent, quel que soit le côté.** Entre deux essais, seul le
réglage `s` change : la console fait tourner les roues de 360/s degrés d'odométrie brute.
L'angle réel devrait suivre, avec une pente de 1 environ (k réel).

| Essais comparés | Odométrie brute en plus | Angle réel en plus, selon les côtés supposés | Pente |
|---|---|---|---|
| R2 − R1 | +17,2° | +12,6° ou +43,6° (ou leurs opposés) | 0,73 ou 2,5 |
| R1 − R3 | +13,2° | +4,8° ou +26,2° (ou leurs opposés) | 0,36 ou 2,0 |

Aucune combinaison ne donne une pente proche de 1. Donc soit le robot ne tourne pas pareil
d'un essai à l'autre (au moins ±2 %, soit ±7° par tour), soit le mètre se trompe d'autant.
**On ne peut tirer aucun facteur de ces essais** : `angular_scale` est remis à 1.0.

**R4 ne mesure pas qu'un cap.** 32,5 cm de côté et 52,5 cm devant font 61,7 cm parcourus pour
50 cm demandés. Le robot s'était donc déplacé d'au moins 10 cm pendant ses quatre quarts de
tour, alors que l'odométrie le voyait immobile à 1 mm près (H5), ou la mesure est partie d'un
autre point.

**La vitesse que renvoient les servos est grossière.** Dans nos 44 526 images d'épisodes
(`pick_sock_v1`, `pick_can_v1`), base immobile, les vitesses de roues ne prennent que les
valeurs 0, ±50, ±100 et ±150 pas/s : le servo compte ses pas de codeur sur 20 ms. Et une roue
immobile lit ±50 pas/s : c'est le cas d'au moins une roue dans **26 à 28 % des images**.

| Roue | `pick_sock_v1` : valeurs non nulles | `pick_can_v1` |
|---|---|---|
| gauche | −50 : 1542, +50 : 1541, −100 : 4 | −50 : 1890, +50 : 1866, ±100 : 45, ±150 : 3 |
| arrière | −50 : 863, +50 : 849 | −50 : 313, +50 : 326, ±100 : 3 |
| droite | −50 : 724, +50 : 810, ±100 : 2 | −50 : 1086, +50 : 1142, ±100 : 24, +150 : 3 |

**Cette vitesse grossière n'explique pourtant pas 10 à 32°.** Simulation de toute la chaîne
de mesure (servo qui compte sur 20 ms, host à 30 Hz, laptop Windows dont l'horloge avance par
pas de 15,6 ms, `GoTo` réel), roues parfaites, 30 tirages de quatre quarts de tour :

| Odométrie | Écart réel − odométrie sur 360° |
|---|---|
| Vitesses lues (comme le 15 nov.) | 0,4° d'écart-type, 0,9° au pire |
| Codeurs de roues par le host | 0,01° d'écart-type |

Donc **H4 n'est pas la cause principale**, tant que le servo compte honnêtement ses pas (ce que
montrent les valeurs au repos). La chaîne logicielle mesure bien ce que font les roues, à 1°
près. Les 10 à 32° viennent d'ailleurs : du sol et de la mécanique (H1, H5), ou du mètre (H3).

### 10.2 Deux défauts du logiciel trouvés en chemin

| Défaut | Effet | Preuve |
|---|---|---|
| **Le bruit au repos est intégré.** Une roue immobile qui lit 50 pas/s fait tourner l'odométrie de 0,6°/s pendant cette image | dérive d'environ 1° par minute à l'arrêt ; visible dans le journal : 358,68° puis 359,11° 21 s plus tard, sans bouger (R1) | valeurs ci-dessus |
| **La mission intégrait une lecture sur toute la durée d'une saisie.** Pendant une saisie (8 à 20 s) la mission ne lit pas la base ; au pas suivant, elle multipliait la vitesse du moment par toute cette durée | une roue à 50 pas/s × 15 s = **8,8° de cap** d'un coup, environ une saisie sur quatre ; pareil pour la position de l'objet suivi | `tests/test_sweep.py`, `test_a_noisy_speed_reading_after_a_pick_does_not_turn_the_map` : échoue avant le correctif |

Le second n'a pas joué dans les essais R1 à R4 (faits avec la console, qui lit en continu). Il
aurait faussé toute mission avec saisie.

### 10.3 Ce qui est corrigé (branche `ws1/encoder-odometry`)

- **L'odométrie compte les pas des codeurs de roues.** Le host (`scripts/lekiwi_host.py`)
  ajoute à chaque observation la position des trois roues (0 à 4095 par tour) et son horloge ;
  le laptop en déduit le déplacement exact (`EncoderMotion`, `src/makai/robot/lekiwi.py`). Plus
  de bruit au repos, plus de dépendance à la cadence ni à l'horloge. Ce que voient les modèles
  de saisie ne change pas. Avec un host pas encore mis à jour, la console retombe sur les
  vitesses et le dit (onglet Drive, « odometry »).
- **Un silence de plus d'une seconde n'est plus intégré** (`navigation/odometry.py`,
  `orchestrator/mission.py`).
- **`angular_scale: 1.0`** en attendant une mesure fiable ; `linear_scale: 0.978` est gardé
  (deux mesures concordantes), à revérifier une fois sur les codeurs.
- **Le journal du host est daté** : on saura quand le chien de garde a coupé la base (H7).
- **Un enregistreur de vol** : la console écrit `data/odometry_trace_<heure>.csv` (commande,
  vitesses lues, codeurs, pose) pendant chaque déplacement. `scripts/odometry_report.py` le
  résume : vitesses contre codeurs, pas de chaque roue, régularité du flux.
- **Un test de rotation à la caméra**, `scripts/turn_check.py` : il lit la direction d'un
  marqueur, fait 360° à l'odométrie, relit. Signé, répété, sans mètre ni règle.

### 10.4 À faire sur le robot : dix minutes qui tranchent

```bash
# 1. Mettre le host à jour sur la Pi, puis le relancer (docs/SETUP.md, section 4)
scp scripts/lekiwi_host.py kiwi@10.42.0.1:~/makai_host.py

# 2. Robot à 1,5 m du marqueur de la poubelle, face à lui, console fermée
uv run python scripts/turn_check.py              # 3 tours à gauche, à 0,6 rad/s
uv run python scripts/turn_check.py --speed 0.3  # plus lentement
uv run python scripts/turn_check.py --right      # dans l'autre sens

# 3. Après quelques déplacements depuis la console
uv run python scripts/odometry_report.py
```

| Ce que dit `turn_check` | Conclusion | Quoi faire |
|---|---|---|
| Les rapports réel / odométrie concordent à 1 % près | une simple échelle (rayon de la base, H6) | écrire la valeur proposée dans `robot.odometry.angular_scale`, relancer : le rapport doit donner 1,00 |
| Ils diffèrent, et moins à 0,3 rad/s | les roues glissent à l'accélération (H1) | tourner lentement : `GoToTuning.max_ang_rad_s` 0,3 |
| Ils diffèrent quelle que soit la vitesse | glissement propre au sol ou à la mécanique (H1, H5) | contrôles matériels ci-dessous ; ne pas compter sur les rotations (ci-dessous) |
| La distance au marqueur change entre avant et après | le robot se déplace en tournant (H5) | une roue porte moins que les autres : centrer le poids, vérifier les roues |

| Ce que dit `odometry_report` | Conclusion |
|---|---|
| « speeds / enc » loin de 1 | les vitesses lues étaient fausses : corrigé par les codeurs |
| « uneven » de plus de 2 % dans un tour sur place | un servo de roue ne suit pas sa commande : batterie, servo, roue freinée |

**Contrôles matériels**, du plus probable au moins probable :

1. **Une roue qui tourne sur son moyeu.** Ni les codeurs ni les vitesses ne le voient : le
   servo tourne, la roue pas autant. Tracer un trait au feutre à cheval sur chaque roue et son
   moyeu ; après dix tours, les deux moitiés doivent rester alignées. Resserrer les vis.
2. **La répartition du poids.** Bras replié en `home` ; batterie centrée. Une roue arrière peu
   chargée glisse, et le robot se déplace en tournant.
3. **Les galets** : ils doivent tourner librement, sans grains du sol coincés.
4. **La batterie** : au-dessus de 11,5 V pour les essais.
5. **Le sol** : refaire `turn_check` sur le sol de la démo, et sur un sol lisse pour comparer.

**Solution retenue pour la démo, quelle que soit la cause (15 nov., 19 h)** : mettre la
poubelle en face du robot, de l'autre côté de la zone. En Vacuum & collect il ne tourne alors
plus du tout, et la caméra corrige l'odométrie en continu sur le marqueur de la poubelle
(`docs/NAVIGATION.md`, section 2 ; `orchestrator/sweep.py`, `_fix_on_markers`). En simulation
avec des roues qui glissent : 4 cm d'écart au pire, contre 38 cm avec la poubelle derrière.

**Avec la poubelle derrière**, la mission est déjà faite pour se passer des rotations en grande
partie : en Vacuum & collect le robot ne tourne jamais pendant qu'il balaie, et il recale sa
position et son cap sur le marqueur de la poubelle à chaque dépose. Il reste les deux
demi-tours de chaque dépose. Tracer la zone sans tourner. Mettre `recheck_after_m: 3`.

### 10.5 Ce qui reste incertain

- Rien de la section 10.3 n'a tourné sur le robot. Le host modifié lit trois registres de plus
  par boucle : vérifier qu'il tient toujours 30 observations par seconde.
- La simulation suppose que le servo compte ses pas sur 20 ms sans biais. Les valeurs au
  repos le suggèrent ; `odometry_report` le confirmera ou non sur un vrai tour.
- La précision de `turn_check` dépend du modèle de la caméra avant et du fait que le robot
  tourne sur place ; à 1,5 m, 5 cm de déplacement de côté valent 2°.

## 11. Résultats sur le robot (15 nov., 19 h 30 à 19 h 40)

**Conditions.** Host d'Ali (#35, codeurs de roues et horloge du host) installé sur la Pi et
relancé à 19 h 30 ; `turn_check` affiche « odometry from: wheel encoders, through the host ».
Batterie à 10,8–10,9 V, sous les 11,5 V conseillés. Moquette du hackerspace. Robot à 1,20–1,24 m
d'un carton, option A. Journal : `docs/logs/odometry/turn_check_20261115.csv`.

**La cible.** Pas les bandes de scotch, que la caméra du robot ne trouve pas (§11.3), mais un
motif imprimé prêté par un autre groupe, collé sur le carton : un carré sombre avec un U blanc.
Ce n'est pas un code ArUco lisible (aucun dictionnaire ne le décode, son carré est aussi sombre
que le scotch autour). Un petit détecteur écrit pour l'occasion (hors du dépôt) trouve le U
blanc et a été branché sur `turn_check.py` à la place de `build_station_detector`. Robot à
l'arrêt, il le voit sur 40 images sur 40, direction stable à 0,01° près.

### 11.1 Rotations

| Série | Sens, vitesse | `angular_scale` | Réel / odométrie, 3 tours de 360° | Moyenne |
|---|---|---|---|---|
| 1 | gauche, 0,6 rad/s | 1.0 | 0,948 · 0,944 · 0,944 | 0,945 |
| 2 | gauche, 0,3 rad/s | 1.0 | 0,953 · 0,950 · 0,949 | 0,951 |
| 3 | droite, 0,6 rad/s | 1.0 | 0,947 · 0,952 · 0,944 | 0,947 |
| 4 | gauche, 0,6 rad/s | **0.947** | 1,006 · 1,002 · 1,003 | **1,004** |

(Un premier essai, avant la série 1, avait donné 0,945 puis perdu le marqueur : défaut du script,
§11.2.) En degrés : l'odométrie compte 358,8° (la cible moins la tolérance d'arrêt), le robot
fait 338 à 342° avec l'échelle 1.0, et 359,5 à 360,8° avec 0.947.

Ce qu'on en tire, d'après le tableau de la section 10.4 :

- **Avec les codeurs, c'est une échelle**, pas un écart au hasard : 9 tours entre 0,944 et 0,953,
  dans les deux sens. Les 10 à 32° qui variaient d'un essai à l'autre venaient des vitesses lues
  par les servos (§10.1), pas des roues.
- **Peu d'effet de la vitesse** : 0,951 à 0,3 rad/s contre 0,945 à 0,6. Pas de glissement
  notable à l'accélération ; rien à changer à `GoToTuning`.
- **Le robot tourne sur place** : distance au marqueur de 1,16 à 1,25 m avant et après chaque
  tour, sans dérive qui s'accumule (série 4 : 1,20 m au début, 1,24 m à la fin). Une partie de
  l'écart vient de ce que le marqueur est mesuré à des endroits différents de l'image.
- **Cause probable de l'échelle** : H6, le rayon effectif de la base (centre aux points de
  contact des roues) 5,6 % plus grand que dans `BaseGeometry`, ou un glissement régulier des
  galets sur la moquette. L'échelle corrige les deux. Sur un autre sol, refaire `turn_check`.
- **Corrigé** : `robot.odometry.angular_scale: 0.947` dans `configs/makai.yaml` (moyenne des
  9 tours ; le script proposait 0,950 après la série 4, l'écart est dans le bruit). Valable
  seulement avec le host à codeurs.

À faire encore : `linear_scale` (0,978) a été mesuré avec les vitesses lues : refaire un
100 cm au mètre avec les codeurs ; `odometry_report.py` après quelques déplacements à la
console ; refaire `turn_check` batterie chargée pour confirmer.

### 11.2 Défaut corrigé dans `turn_check.py`

Après un tour où il avait fallu chercher le marqueur, le script se retournait vers lui dans le
mauvais sens (`nominal - moved` au lieu de `nominal + moved`) : l'écart doublait, le marqueur
sortait du champ et l'essai suivant s'arrêtait sur « Marker lost before the turn ». C'est ce
qui avait interrompu les deux premiers lancements. Corrigé.

### 11.3 La caméra du robot ne trouve pas les bandes de scotch des cartons

À voir avant de compter sur la disposition « poubelle en face » ou sur le recalage au
marqueur. Deux images de la caméra avant, prises à l'arrêt, détecteur de #39 :

- `docs/figures/stations_robot_camera_09m.jpg`, cartons à ~0,9 m, les deux bandes entières dans
  l'image : **rien n'est détecté**. Avant #39, le détecteur prenait l'ombre sous le rabat du
  carton de droite pour une bande horizontale à 4,6 m.
- `docs/figures/stations_robot_camera_12m.jpg`, cartons à ~1,2 m : bande horizontale vue à
  2,5 m au lieu de 1,2 m. Ici le motif de l'autre groupe en cache une partie et fausse sa
  longueur, donc cette image compte moins.

Pourquoi, mesuré sur la première image (espace Lab, médianes) :

| Zone | Clarté L | Chroma |
|---|---|---|
| bande horizontale (carton de gauche) | 76 | 5 |
| bande verticale (carton de droite) | 88 | 8 |
| carton de gauche, à l'ombre | 117 | **12** |
| carton de droite | 148 | 23 |
| sol (moquette) | 157 | 15 |
| ombre sous le rabat du carton de droite | 60 | 17,5 |

- **Carton de gauche** : la caméra du robot délave les couleurs, et ce carton est à l'ombre. Son
  chroma (12) est sous le seuil du carton (`min_flank_chroma` 19) et, pour la moitié de ses
  pixels, sous celui du scotch (`grey_chroma` 12) : tout le carton passe pour du gris, la bande
  ne s'en détache pas.
- **Carton de droite** : son carton va bien, mais l'ombre sous son rabat coupe la bande
  verticale à ~8 cm du sol, donc à la hauteur de l'objectif, où que soit le robot. Les deux
  morceaux s'arrêtent à la ligne d'horizon, et la règle « une bande verticale traverse
  l'horizon » les rejette.

Pistes : côté scène, cartons éclairés, rabats fermés ou scotchés à plat pour que la bande
verticale court sur du carton uni ; côté code, définir le carton par rapport au scotch (plus
clair d'un écart donné) plutôt que par un chroma absolu, et régler les seuils sur des images de
la caméra du robot, pas d'un téléphone. À défaut, un motif imprimé sur fond blanc (marqueur
ArUco, si une imprimante se trouve) se détecte sans ambiguïté.
