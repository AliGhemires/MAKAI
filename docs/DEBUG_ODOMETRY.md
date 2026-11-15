# Débogage navigation : odométrie, rotations, flux du robot (15 nov.)

Pour une analyse logicielle et matérielle en profondeur. Écrit à partir des journaux du laptop
d'Amine (Windows) et de la Pi, et des mesures faites au mètre par l'équipe le 15 nov. entre
16 h et 17 h 40. Tous les fichiers cités sont dans `docs/logs/odometry/`.

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
