# Installation et mise en route

## État du robot (vérifié le 14 novembre)

- **Base** : 3 roues omnidirectionnelles, servos Feetech STS3215 en mode vitesse.
  Identifiants **7 (gauche), 8 (arrière), 9 (droite)**, déjà programmés. Les roues n'ont
  pas besoin de calibration.
- **Batterie** : `Present_Voltage` lit 125, soit 12,5 V : servos en version 12 V.
- Chaque roue tourne seule, et la conduite au clavier marche depuis la Pi.
- **Bras** (moteurs 1 à 6) : pas encore monté. Tant qu'il manque, le host LeRobot refuse de
  démarrer (il exige les 9 moteurs) : utiliser le [mode filaire](#base-seule-le-mode-filaire).
- **Caméra poignet** : pas encore branchée.
- **Reste à vérifier au sol** : avancer va bien du côté de la caméra, aller à gauche va à
  gauche, tourner à gauche tourne dans le sens anti-horaire, et la vitesse réelle suit la
  commande (0,15 m/s pendant 4 s ≈ 60 cm).

Câbles qui sortent du robot :

| Câble | Rôle | Mode filaire (laptop Windows) | Mode Pi |
|---|---|---|---|
| USB n°1 | Carte moteurs | `COM5` | `/dev/ttyACM0` |
| USB n°2 | Caméra avant | OpenCV index `1` (`0` = webcam du laptop) | `/dev/video0` (YUYV 640x480 à 30 fps) |
| USB-C | Alimentation 5 V de la Pi | débranché | port USB-C de la Pi |

## 1. Ton laptop (10 minutes)

Prérequis : `git`, [`uv`](https://docs.astral.sh/uv/) (`brew install uv` ou
`curl -LsSf https://astral.sh/uv/install.sh | sh`), `ffmpeg`.

```bash
git clone https://github.com/AliGhemires/MAKAI.git && cd MAKAI
make setup        # tout : LeRobot, torch, ultralytics (plusieurs Go, à lancer tôt)
make check        # lint + tests : doit être vert
make sim          # la mission complète en simulation
cp configs/local.example.yaml configs/local.yaml   # puis l'éditer
```

`make setup-lite` installe seulement le cœur (simulation, navigation, géométrie) en
quelques secondes : suffisant pour WS3 et WS5 au début.

Python 3.12 est imposé par LeRobot 0.7.0 ; `uv` l'installe tout seul.

Connexion au Hub Hugging Face (datasets et modèles) :

```bash
uv run hf auth login        # token en écriture : https://huggingface.co/settings/tokens
```

Sur Mac, autoriser le terminal dans Réglages Système → Confidentialité et sécurité →
**Surveillance de l'entrée** et **Accessibilité**, sinon la téléop clavier ne marche pas.

### Sous Windows

- `make` n'existe pas : lancer directement les commandes du `Makefile`.

  | Au lieu de | Lancer |
  |---|---|
  | `make setup` | `uv sync --all-extras` |
  | `make check` | `uv run --no-sync ruff check .`, `uv run --no-sync ruff format --check .`, `uv run --no-sync pytest` |
  | `make sim` | `uv run --no-sync makai-mission --sim` |

- Le code Python se met dans un fichier `.py` lancé avec `uv run python fichier.py`. Tapé
  directement dans `cmd`, il donne « 'from' n'est pas reconnu en tant que commande ».
- Les ports série s'appellent `COMx`. Sur certains laptops, `COM3` et `COM4` sont des ports
  Bluetooth : la carte moteurs est le port qui apparaît quand on la branche.
- Autoriser Python dans le pare-feu Windows, sinon la liaison ZeroMQ entre la Pi et le
  laptop est bloquée.
- Un avertissement Bonjour `mdnsNSP.dll` (LSA) pendant `pip` est sans rapport : l'ignorer.
- Les premiers tests ont été faits dans un environnement conda `lerobot` (Miniforge,
  Python 3.12, ffmpeg 7.1.1, LeRobot 0.7.1 installé depuis les sources). Le code MAKAI, lui,
  tourne dans l'environnement `uv` du dépôt.

## 2. La Raspberry Pi 5 (WS1)

### Ce qui est installé

- Raspberry Pi OS Lite 64 bits sur une microSD de 64 Go. Nom d'hôte `lekiwi`, utilisateur
  `kiwi` : `ssh kiwi@lekiwi.local`.
- Environnement conda `lerobot`, LeRobot 0.7.1 installé depuis les sources dans
  `~/lerobot` (`pip install -e ".[lekiwi]"`). À chaque connexion :
  `conda activate lerobot && cd ~/lerobot`.
- `kiwi` est dans le groupe `dialout` : accès au port des moteurs sans `sudo chmod`.
- Le code des moteurs et de LeKiwi est identique entre le tag `v0.7.0` de LeRobot et
  cette 0.7.1 (vérifié avec `git diff` sur le clone du laptop) : un laptop en 0.7.0 parle
  donc au host de la Pi.

### MAKAI sur la Pi

Avoir le dépôt sur la Pi permet de faire tourner MAKAI sur le robot lui-même (la
[page de pilotage](#conduire-la-base-depuis-un-navigateur), le mode filaire) et de le mettre
à jour avec `git pull`. Le dépôt est privé : la Pi s'identifie avec une **clé de déploiement
en lecture seule**, pas avec le compte GitHub de quelqu'un, puisque toute l'équipe utilise
la Pi.

```bash
# sur la Pi : créer la clé, une seule fois
ssh-keygen -t ed25519 -C "lekiwi-pi" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Le propriétaire du dépôt colle cette ligne dans GitHub → Settings → Deploy keys → Add deploy
key, sans cocher « Allow write access ». Ensuite, sur la Pi :

```bash
ssh -T git@github.com            # la première fois, répondre yes ; doit dire « successfully authenticated »
git clone git@github.com:AliGhemires/MAKAI.git ~/MAKAI
conda activate lerobot && cd ~/MAKAI
pip install --no-deps -e .       # MAKAI dans l'env de LeRobot, qui a déjà ses dépendances
python -c "import makai.robot.manual; print('ok')"
```

Mettre à jour : `cd ~/MAKAI && git pull`. La Pi ne peut pas pousser : on code sur son laptop,
on pousse, puis on fait `git pull` sur la Pi.

### Réinstaller depuis zéro

Si les organisateurs ont fourni une carte SD déjà préparée, vérifier d'abord ce qui est
installé (`lerobot-info`). Sinon :

```bash
# sur la Pi, en SSH
curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.bashrc
mkdir -p ~/makai && cd ~/makai
uv venv --python 3.12 && source .venv/bin/activate
uv pip install "lerobot[lekiwi]==0.7.0"
```

Raspberry Pi OS « Bookworm » fournit Python 3.11, trop ancien : c'est pour cela qu'on
passe par `uv`, qui installe Python 3.12 à côté.

**`/tmp` est un tmpfs de 2 Go** : l'installation de torch échoue avec « No space left on
device ». Avant d'installer, avec `pip` comme avec `uv`, faire `mkdir -p ~/tmp && export TMPDIR=~/tmp`.
Ce qui a marché avec `pip`, dans `~/lerobot` :

```bash
pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install --no-cache-dir -e ".[lekiwi]"
```

### Réseau, ports et caméras

Réseau : la Pi et les laptops sur le **même réseau dédié** (routeur de voyage ou partage
de connexion). Noter l'IP de la Pi (`hostname -I`) dans `configs/makai.yaml` → `robot.remote_ip`.
Sur le partage de connexion iPhone, c'est aujourd'hui `172.20.10.3`. Une IP qui ne vaut que
pour un réseau peut aussi aller dans `configs/local.yaml`, qui n'est pas partagé.

Ports et caméras, sur la Pi :

```bash
lerobot-find-port                 # port de la carte moteurs, en général /dev/ttyACM0
sudo chmod 666 /dev/ttyACM0
lerobot-find-cameras opencv       # repérer laquelle est la C270 (avant) et la HBVCAM (poignet)
```

Sur notre Pi : carte moteurs `/dev/ttyACM0`, caméra avant `/dev/video0`. Le `chmod` y est
inutile, `kiwi` étant dans le groupe `dialout`. `ls /dev/v4l/by-id/` donne des chemins de
caméra qui ne changent pas au redémarrage.

`/dev/video19` et au-delà sont les nœuds ISP et codec de la Pi 5, pas des caméras. Préférer
les chemins `/dev/v4l/by-id/...` aux numéros `/dev/videoN`, qui peuvent changer.

Si un autre utilisateur n'a pas accès au port : `sudo usermod -aG dialout $USER`, puis se
reconnecter.

Reporter les chemins des caméras dans `configs/makai.yaml` → `robot.cameras` **et** dans
la commande du host ci-dessous : les noms (`front`, `wrist`) et les résolutions doivent
être identiques des deux côtés.

## 3. Moteurs et calibration (une seule fois)

Les roues ont déjà leurs identifiants (7, 8, 9) et n'ont pas besoin de calibration :
LeRobot leur écrit un réglage fixe (pas d'origine, encodeur entier). Ne relancer
`lerobot-setup-motors` que pour un kit neuf. Le bras se calibre une fois monté sur le même bus.

```bash
# sur la Pi : identifiants des moteurs (bras 1 à 6, roues 7 à 9), seulement si le kit est neuf
lerobot-setup-motors --robot.type=lekiwi --robot.port=/dev/ttyACM0

# sur la Pi : calibration du bras du robot
lerobot-calibrate --robot.type=lekiwi --robot.id=makai_kiwi

# sur le laptop : calibration du bras leader
uv run lerobot-find-port
uv run lerobot-calibrate --teleop.type=so101_leader --teleop.port=/dev/tty.usbmodemXXXX --teleop.id=makai_leader
```

**L'identifiant `makai_kiwi` ne change plus jamais** : c'est sous ce nom que la
calibration est rangée. La calibration du leader est stockée sur le laptop : si un autre
laptop téléopère, copier `~/.cache/huggingface/lerobot/calibration/` ou recalibrer.

## 4. Démarrer le robot (à chaque session)

Le host exige les 9 moteurs : tant que le bras n'est pas monté, passer au
[mode filaire](#base-seule-le-mode-filaire).

Sur la Pi :

```bash
cd ~/makai && source .venv/bin/activate
python -m lerobot.robots.lekiwi.lekiwi_host \
  --robot.id=makai_kiwi --robot.port=/dev/ttyACM0 \
  --robot.cameras='{front: {type: opencv, index_or_path: /dev/video0, width: 640, height: 480, fps: 30, fourcc: MJPG}, wrist: {type: opencv, index_or_path: /dev/video2, width: 640, height: 480, fps: 30, fourcc: MJPG}}' \
  --host.connection_time_s=36000
```

Sur notre Pi, LeRobot est dans l'environnement conda : remplacer la première ligne par
`conda activate lerobot && cd ~/lerobot`.

Sans `--host.connection_time_s`, le host s'arrête au bout de 30 secondes. Lancer cette
commande dans `tmux` pour qu'elle survive à une coupure SSH.

Sur le laptop :

```bash
make teleop       # leader pour le bras, clavier pour la base, flux dans Rerun
```

Clavier : `w` `s` avancer et reculer, `a` `d` gauche et droite, `z` `x` tourner, `r` `f`
vitesse. `p` enregistre la pose courante du bras dans `configs/poses_captured.yaml`.

### Base seule : le mode filaire

Sans le bras, MAKAI pilote la base directement par le câble USB de la carte moteurs, sans
host. Le câble est branché sur la machine qui fait tourner MAKAI : la Pi elle-même
(`/dev/ttyACM0`, le plus simple : voir la [page de pilotage](#conduire-la-base-depuis-un-navigateur)),
ou un laptop. Sur un laptop Windows, dans `configs/local.yaml` :

```yaml
robot:
  link: wired
  base:
    port: COM5
```

`LeKiwiRobot.from_config` passe alors par `WiredBase` (`src/makai/robot/lekiwi.py`) :
`robot.drive()` envoie les vitesses des roues avec la même cinématique que LeRobot. Les
valeurs des roues sont dans `configs/makai.yaml` → `robot.base` : identifiants 7, 8 et 9,
roues de 0,05 m de rayon à 0,125 m du centre, montées à 240°, 0° et 120° moins 90° (gauche,
arrière, droite). Vitesse plafonnée à 3000 pas/s par roue (environ 0,23 m/s) ; au-delà, les
trois roues ralentissent ensemble pour garder la direction.

Dans ce mode :
- pas de bras ni de caméras. `get_observation()` renvoie seulement la vitesse mesurée de la
  base, et `make teleop` comme `make mission` passent toujours par le host ;
- comme avec le host, la base s'arrête si aucune commande n'arrive pendant 0,5 s : une
  boucle doit renvoyer la commande en continu ;
- **si le câble USB se débranche pendant que le robot roule, les roues gardent leur
  dernière vitesse.** Premiers essais robot sur cales, main près de l'interrupteur, câble
  assez long et attaché.

Retirer `link: wired` de `local.yaml` pour repasser par le host.

Vérifier la vitesse au sol : 0,15 m/s pendant 4 s, le robot doit parcourir environ 60 cm.

```python
# drive_check.py, lancé avec : uv run python drive_check.py
import time

from makai.config import load_config
from makai.contracts import BaseVelocity
from makai.robot.lekiwi import LeKiwiRobot

robot = LeKiwiRobot.from_config(load_config())
robot.connect()
try:
    end = time.monotonic() + 4.0
    while time.monotonic() < end:
        robot.drive(BaseVelocity(x=0.15))
        time.sleep(0.05)
finally:
    robot.disconnect()
```

### Conduire la base depuis un navigateur

`scripts/drive.py` sert une page de pilotage : un joystick pour aller dans toutes les
directions, un curseur pour tourner, le chemin parcouru, les vitesses commandées et
mesurées, la tension de la batterie. Elle marche sur téléphone, tablette ou laptop sans rien
installer, et le script n'utilise que la bibliothèque standard de Python : rien à ajouter
sur la Pi.

C'est l'interface du robot, **MAKAI control**, en trois onglets :
- **Drive** : la caméra avant en direct (la caméra de poignet en vignette, un clic les
  échange ; « Save image » enregistre l'image), le chemin parcouru, les vitesses, la charge
  des roues et les angles du bras ;
- **Measure** : déplacements précis vérifiés au mètre (section suivante) ;
- **Robot** : bras (angle de chaque articulation, pince en %), batterie et température de
  chaque moteur, état des caméras, connexion. Lien direct : `http://lekiwi.local:8000/#robot`.

D'où viennent les données :

| | Mode filaire, sur la Pi | Mode host, depuis un laptop |
|---|---|---|
| Caméras | ouvertes directement (`robot.cameras` de la config) | images du host |
| Bras | lu sur le bus, **jamais commandé** (pas même son couple), si la calibration du bras existe sur la Pi | angles du host |
| Batterie, températures | oui | non (le host ne les envoie pas) |

En mode host, ne pas lancer la page en même temps que `teleop.py` ou `record.py` : ils se
partagent le flux du host. Une caméra absente (poignet pas branché) est signalée, sans
empêcher le reste. `--no-cameras` pour ne pas les ouvrir, `--camera-fps 5` pour un réseau lent.

Sur la Pi, carte moteurs branchée sur la Pi (le bras n'est pas nécessaire) :

```bash
ssh kiwi@lekiwi.local
tmux new -As drive                   # la page survit à une coupure SSH
conda activate lerobot && cd ~/MAKAI
python scripts/drive.py --link wired
```

Puis ouvrir `http://lekiwi.local:8000` sur un appareil du même réseau, ou
`http://<IP de la Pi>:8000` si le nom en `.local` ne répond pas (certains Android). Le script
affiche ces adresses au démarrage.

Sans robot, pour essayer la page : `uv run python scripts/drive.py --sim`, puis
`http://localhost:8000`. Avec le bras monté et le host lancé, depuis un laptop :
`uv run python scripts/drive.py --link host`.

| | Téléphone, tablette | Clavier | Manette |
|---|---|---|---|
| Se déplacer, toutes directions | joystick de gauche | `W` `A` `S` `D` ou flèches, combinables pour les diagonales | stick gauche |
| Tourner | curseur de droite | `Q` `E` | stick droit |
| Vitesse | 25, 50, 75, 100 % | `1` à `4` ; `Shift` maintenu : lent | `LB` `RB` |
| Arrêt d'urgence | STOP | `Espace` | `B` |
| Reprendre | Resume | `Entrée` | `Start` |

Ce sont les positions des touches qui comptent : sur un clavier AZERTY, `W` `A` `S` `D`
sont `Z` `Q` `S` `D`.

Ce qui rend la conduite douce et sûre (`src/makai/robot/manual.py`, réglages dans
`configs/makai.yaml` → `teleop.drive`) :
- **Accélérations limitées** : le robot atteint sa vitesse maximale en 0,5 s et freine plus
  de deux fois plus fort, quoi que fasse le joystick. Le joystick est plus fin au centre
  qu'au bord, pour les petits déplacements.
- **Homme mort** : la page envoie la commande 20 fois par seconde. Si rien n'arrive pendant
  0,4 s (onglet fermé, téléphone verrouillé, WiFi coupé), le robot freine jusqu'à l'arrêt.
- **Un seul pilote** : le premier appareil qui touche un joystick conduit, les autres
  regardent ; « Take over » prend la main. Tout le monde peut appuyer sur STOP.
- **Arrêt d'urgence** : vitesse coupée tout de suite, et le robot ne repart pas avant « Resume ».
- `Ctrl+C`, ou la fin de la session SSH quand on n'est pas dans `tmux`, arrête les roues et
  libère le port série.

Limites :
- la page est ouverte à tout le réseau, sans mot de passe : rester sur le réseau de l'équipe,
  ou `--bind 127.0.0.1` pour la réserver à la machine elle-même ;
- elle ne tourne pas en même temps que le host ou qu'un autre script sur le même port série ;
- si le processus est tué brutalement (`kill -9`, Pi qui s'éteint) ou si le câble USB se
  débranche, les roues gardent leur dernière vitesse : couper l'interrupteur ;
- le chemin affiché vient de l'odométrie des roues : il dérive, surtout en tournant.

### Mesurer et calibrer les déplacements (onglet Measure)

L'onglet **Measure** de la page de pilotage (lien direct : `http://lekiwi.local:8000/#measure`)
fait faire au robot un déplacement précis : avancer, reculer, aller à gauche ou à droite d'une
distance donnée, ou tourner d'un angle donné. Le robot suit ses encodeurs de roues
(`src/makai/robot/moves.py`) : démarrage doux, ralentissement avant l'arrivée, arrêt quand la
distance est atteinte, sans jamais revenir en arrière, et maintien des deux autres axes. Ensuite
on mesure au mètre ce qu'il a vraiment parcouru, et la page compare.

Les roues ne savent que de combien elles ont tourné : elles ne voient ni le glissement ni une
erreur sur le rayon des roues. Seule une mesure extérieure (mètre, rapporteur) dit la vérité.

Procédure, sur le sol de la démo et batterie chargée :
1. Coller un mètre ruban au sol dans la direction du déplacement, et repérer un point fixe du
   robot (le bord avant).
2. Measure → Forward, 20 cm, Medium → **Go**. Lire le mètre, taper la valeur dans « Tape
   measure says », **Save**. Recommencer au moins 3 fois, puis avec 50 cm.
3. Lire le bloc **Forward / back** :
   - *Wheels stop at* : où le robot s'arrête d'après ses roues. Doit rester sous 1 mm ;
   - *Real error (tape − asked)* : l'erreur réelle, celle qui compte ; *spread* : sa
     dispersion d'un essai à l'autre, qu'aucune calibration ne corrige ;
   - *Tape ÷ wheels* et la ligne `Set robot.base.wheel_radius_m: ...` : la correction proposée.
4. Reporter la valeur dans `configs/makai.yaml` → `robot.base.wheel_radius_m` (fichier partagé :
   l'annoncer), relancer `drive.py`, refaire 3 mesures : l'erreur doit tomber sous 0,5 %.
5. Ensuite seulement, les rotations : Turn left 360° (et Turn right), mesurer l'angle réel avec
   une bande collée au sol le long de l'avant du robot, en déduire `robot.base.base_radius_m`.
6. Vérifier Left / Right : si l'écart diffère beaucoup de l'avant, les galets des roues
   glissent sur le côté ; le noter dans la fiche WS1.

Les mesures sont gardées dans `data/move_trials.csv` sur la Pi (hors git, conservées au
redémarrage) et se téléchargent avec **Download CSV**. « Clear all » garde une copie datée.
En simulation, `--sim --sim-scale 0.96` simule un robot dont les roues se trompent de 4 % :
la valeur « mesurée » est remplie automatiquement, ce qui permet d'essayer toute la procédure.

## 5. Mise en place avant toute collecte (porte G2)

À faire dans cet ordre, une fois, puis **ne plus rien toucher au montage**.

1. **Fixer les caméras** définitivement. Photographier le montage sous deux angles et
   mettre les photos dans `assets/`. Tracer un repère au marqueur.
2. **Mesurer** la caméra avant (hauteur de l'objectif, inclinaison, avance par rapport au
   centre de la base) et remplir `perception.camera_model` dans `configs/makai.yaml`.
3. **Définir la pose `home`** du bras : repliée, hors du champ de la caméra avant, pince
   au-dessus de la zone de saisie. La capturer (`p` pendant la téléop) et la copier dans
   `configs/arm_poses.yaml`. Elle doit remplir quatre conditions :
   - **la caméra de poignet voit toute la zone de pré-saisie** (étape 4), avec de la marge :
     le modèle doit voir l'objet dès la première image, avant de bouger ;
   - **le bras n'apparaît pas dans l'image de la caméra avant**, qui cherche les objets en roulant ;
   - **elle est reposante pour les servos** : coude plié, pas de bras tendu à l'horizontale.
     Le robot y attend, y roule et y transporte l'objet ;
   - **le leader y retombe tout seul** sur un support fixe (cale en carton, ruban) :
     l'enregistrement démarre et s'arrête d'après cette pose.

   Pour la trouver : `make teleop`, les deux images ouvertes dans Rerun. Poser l'objet au
   centre de la zone puis dans chacun des quatre coins, et chercher une pose repliée où il
   reste visible dans l'image de poignet pour les cinq positions. Lâcher le leader sur son
   support, vérifier que le bras y revient, puis `p`.

   La caméra de poignet doit voir l'objet **au départ et pendant toute la descente**, jusqu'à
   la fermeture de la pince ; après, l'objet est dans la pince et la vue change, c'est normal.
   Faire une descente d'essai en ne regardant que l'image de poignet : si l'objet sort du
   champ avant la saisie, corriger la pose ou la trajectoire.
4. **Choisir la pose de pré-saisie** : poser un objet là où le bras saisit le plus
   facilement, mesurer sa position, la reporter dans `navigation.approach.goal_x_m` et `goal_y_m`.
5. **Calibrer le sol** :
   ```bash
   make markers              # génère assets/markers/, imprimer ground_sheet.png à 100 %
   make calibrate-ground     # feuille à plat devant le robot, à 2 ou 3 distances
   ```
   Vérifier à la règle qu'un marqueur imprimé mesure bien 60 mm ; sinon passer
   `--scale <mesure en mm>/60`. Commiter `configs/ground_plane.yaml`.
6. **Stations** : imprimer `station_0_clothing.png` et `station_1_trash.png`, les coller
   verticalement sur la face avant des bacs, au ras du sol. Capturer `drop_reach` et
   `drop_open`.
7. Commiter la config et noter le tout dans `docs/DECISIONS.md`.

## 6. Lancer la mission

```bash
make sim          # sans robot
make mission      # sur le robot (host lancé sur la Pi)
```

## Dépannage

| Symptôme | Cause probable |
|---|---|
| `connect()` expire | Host non lancé ou arrêté après 30 s, mauvaise IP, réseaux différents. `ping <ip>` |
| Le host refuse de démarrer : `motor check failed`, `Missing motor IDs` 1 à 6 | Bras pas monté : le host exige les 9 moteurs. Passer au mode filaire (section 4) |
| `Missing motor IDs` 7, 8, 9 avec une liste trouvée vide `{}` | Moteurs non alimentés : batterie ou interrupteur |
| `Accès refusé` (`Access is denied`) en écrivant aux moteurs, sous Windows | Le port USB a disparu pendant qu'il était ouvert : câble tiré par le robot qui roule, ou faux contact. Vérifier que `COM5` existe encore. Les roues gardent leur dernière vitesse : couper l'alimentation si elles tournent encore |
| `lerobot-find-port` : `No difference was found` | La carte n'était pas détectée au lancement. La brancher, vérifier que son port apparaît dans la liste « before », relancer |
| `No space left on device` pendant une installation sur la Pi | `/tmp` limité à 2 Go : `export TMPDIR=~/tmp` (section 2) |
| Page de pilotage « offline » | `drive.py` arrêté, ou appareil sur un autre réseau. Essayer `http://<IP de la Pi>:8000` au lieu de `lekiwi.local` |
| `drive.py` : `cannot listen on port 8000` | Il tourne déjà, peut-être dans un autre `tmux` : `pkill -f scripts/drive.py`, ou `--http-port 8001` |
| Bandeau rouge `Robot error: drive: ...` sur la page | Liaison série perdue : câble, alimentation des moteurs. La page reprend seule quand la liaison revient |
| `DeprecationWarning` sur `FeetechMotorsBus` | Sans gravité. MAKAI utilise `SerialMotorsBus`, son remplaçant |
| La base s'arrête par à-coups | Boucle laptop trop lente : le chien de garde du host (0,5 s) coupe. Regarder la cadence affichée |
| Couleurs bleues et rouges inversées | Conversion RGB/BGR : corriger dans `makai/robot/lekiwi.py`, pas ailleurs |
| Image de poignet tournée | Ajuster `rotation` (0, 90, 180, 270) dans la commande du host et dans la config |
| `Incorrect status packet` | Câble moteur mal enfoncé ou alimentation faible. Vérifier la batterie |
| Clavier sans effet en téléop | Autorisations macOS (section 1). Sous Linux Wayland, la téléop clavier ne marche pas : utiliser X11 |
| Le bras tremble ou force | Calibration à refaire, ou un servo en butée : couper, vérifier à la main |
