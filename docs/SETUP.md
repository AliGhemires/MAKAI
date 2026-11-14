# Installation et mise en route

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

## 2. La Raspberry Pi 5 (WS1)

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

Réseau : la Pi et les laptops sur le **même réseau dédié** (routeur de voyage ou partage
de connexion). Noter l'IP de la Pi (`hostname -I`) dans `configs/makai.yaml` → `robot.remote_ip`.

Ports et caméras, sur la Pi :

```bash
lerobot-find-port                 # port de la carte moteurs, en général /dev/ttyACM0
sudo chmod 666 /dev/ttyACM0
lerobot-find-cameras opencv       # repérer laquelle est la C270 (avant) et la HBVCAM (poignet)
```

Reporter les chemins des caméras dans `configs/makai.yaml` → `robot.cameras` **et** dans
la commande du host ci-dessous : les noms (`front`, `wrist`) et les résolutions doivent
être identiques des deux côtés.

## 3. Moteurs et calibration (une seule fois)

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

Sur la Pi :

```bash
cd ~/makai && source .venv/bin/activate
python -m lerobot.robots.lekiwi.lekiwi_host \
  --robot.id=makai_kiwi --robot.port=/dev/ttyACM0 \
  --robot.cameras='{front: {type: opencv, index_or_path: /dev/video0, width: 640, height: 480, fps: 30, fourcc: MJPG}, wrist: {type: opencv, index_or_path: /dev/video2, width: 640, height: 480, fps: 30, fourcc: MJPG}}' \
  --host.connection_time_s=36000
```

Sans `--host.connection_time_s`, le host s'arrête au bout de 30 secondes. Lancer cette
commande dans `tmux` pour qu'elle survive à une coupure SSH.

Sur le laptop :

```bash
make teleop       # leader pour le bras, clavier pour la base, flux dans Rerun
```

Clavier : `w` `s` avancer et reculer, `a` `d` gauche et droite, `z` `x` tourner, `r` `f`
vitesse. `p` enregistre la pose courante du bras dans `configs/poses_captured.yaml`.

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
| La base s'arrête par à-coups | Boucle laptop trop lente : le chien de garde du host (0,5 s) coupe. Regarder la cadence affichée |
| Couleurs bleues et rouges inversées | Conversion RGB/BGR : corriger dans `makai/robot/lekiwi.py`, pas ailleurs |
| Image de poignet tournée | Ajuster `rotation` (0, 90, 180, 270) dans la commande du host et dans la config |
| `Incorrect status packet` | Câble moteur mal enfoncé ou alimentation faible. Vérifier la batterie |
| Clavier sans effet en téléop | Autorisations macOS (section 1). Sous Linux Wayland, la téléop clavier ne marche pas : utiliser X11 |
| Le bras tremble ou force | Calibration à refaire, ou un servo en butée : couper, vérifier à la main |
