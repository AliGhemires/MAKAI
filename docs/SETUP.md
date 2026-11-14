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

**État réel de notre Pi (sam. 14)** : hostname `lekiwi`, utilisateur `kiwi` (mot de passe
dans le chat d'équipe), LeRobot 0.7.1 installé depuis les sources dans l'env conda
`lerobot`, dépôt LeRobot dans `~/lerobot` (détails : `docs/LEKIWI_HANDOFF (2).md`). Après
chaque connexion SSH : `conda activate lerobot && cd ~/lerobot`.

### Réseau

La Pi et les laptops doivent être sur le **même réseau**. L'IP de la Pi va dans
`configs/local.yaml` → `robot.remote_ip` (propre à chaque laptop). La Pi connaît deux
réseaux et prend le premier disponible par ordre de priorité :

| Réseau | Rôle | IP de la Pi | État |
|---|---|---|---|
| Hotspot Windows du laptop « PC-08792 6521 », 5 GHz | principal (priorité 10, profil `makai-laptop`) | `192.168.137.50`, fixe | profil créé, **pas encore validé** |
| Hotspot iPhone « Cyrine », 2,4 GHz | secours automatique (profil `netplan-wlan0-Cyrine`) | `172.20.10.3` en général (DHCP) | marche, mais lent |

- **Hotspot iPhone, mesuré** : aller-retour médian 50 à 140 ms, pics jusqu'à 1,2 s ; le bras
  avance par à-coups en téléop. Le trafic fait deux sauts Wi-Fi (Pi → iPhone → laptop) sur
  une bande 2,4 GHz saturée pendant le hackathon.
- **Hotspot du laptop** : un seul saut, en 5 GHz. Réglages Windows → Réseau → Point d'accès
  mobile : bande 5 GHz, **économie d'énergie désactivée** (sinon Windows le coupe), et le
  laptop ne doit pas se mettre en veille. Inconvénient : le robot dépend de ce laptop.
- **Pas encore essayé** : la Pi comme point d'accès (tous les laptops s'y connectent, ne
  dépend de personne : le plus robuste pour la démo) ; un câble Ethernet laptop ↔ Pi
  (le plus rapide, mais robot attaché).
- L'économie d'énergie Wi-Fi de la Pi est **désactivée**
  (`/etc/NetworkManager/conf.d/99-wifi-powersave-off.conf`) : elle provoquait des pics
  de 1 s.

Changer de réseau à la main, sur la Pi (la session SSH coupe ; si le réseau visé échoue,
la Pi revient seule sur l'autre) :

```bash
sudo nmcli connection up makai-laptop            # hotspot du laptop
sudo nmcli connection up netplan-wlan0-Cyrine    # hotspot iPhone
nmcli -f NAME,AUTOCONNECT-PRIORITY connection show
```

**Mesurer un réseau**, sans faire bouger le robot (téléop arrêtée) :

```bash
uv run python scripts/net_check.py --ip 192.168.137.50   # ou 172.20.10.3
```

Il donne l'aller-retour vers la Pi et, si le host tourne, la régularité du flux
d'observations (trous de plus de 100 et 200 ms, débit). Repères : aller-retour médian
sous 10 ms et aucun trou de plus de 200 ms, c'est bon pour la téléop.

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

# sur la Pi : calibration du bras du robot ; '{}' = sans caméra (sinon échec si la caméra
# de poignet /dev/video2 n'est pas branchée)
lerobot-calibrate --robot.type=lekiwi --robot.id=makai_kiwi --robot.port=/dev/ttyACM0 --robot.cameras='{}'

# sur le laptop : calibration du bras leader
uv run lerobot-find-port
uv run lerobot-calibrate --teleop.type=so101_leader --teleop.port=/dev/tty.usbmodemXXXX --teleop.id=makai_leader
```

**L'identifiant `makai_kiwi` ne change plus jamais** : c'est sous ce nom que la
calibration est rangée. La calibration du leader est stockée sur le laptop : si un autre
laptop téléopère, copier `~/.cache/huggingface/lerobot/calibration/` ou recalibrer.

**Fait le sam. 14** : bras du robot calibré sur la Pi (`makai_kiwi.json`, 17:48, pas
encore copié dans le dépôt) ; leader calibré, dans le dépôt
(`calibration/teleoperators/so_leader/makai_leader.json`). Pour l'installer sur un autre
laptop : `cp -R calibration/. ~/.cache/huggingface/lerobot/calibration/`. Un bras calibré
comme `so_follower` (SO-101 seul) n'est pas utilisable par le LeKiwi : noms de moteurs
différents et pas de roues.

## 4. Démarrer le robot (à chaque session)

Sur la Pi, avec notre host (`scripts/lekiwi_host.py`, copié sur la Pi sous
`~/makai_host.py` ; après une modification : `scp scripts/lekiwi_host.py kiwi@<ip>:~/makai_host.py`) :

```bash
conda activate lerobot && cd ~/lerobot
python ~/makai_host.py --arm_acceleration=50 \
  --robot.id=makai_kiwi --robot.port=/dev/ttyACM0 \
  --robot.cameras='{front: {type: opencv, index_or_path: /dev/video0, width: 640, height: 480, fps: 30, fourcc: MJPG, warmup_s: 3}}' \
  --host.connection_time_s=3600
```

- C'est le host de LeRobot, avec une accélération réduite pour les servos du bras.
  LeRobot les règle au maximum (254) : quand les commandes arrivent par paquets sur le
  Wi-Fi, le bras saute. 30 = plus doux, 100 = plus vif ; les roues gardent 254.
- `warmup_s: 3` : la webcam avant met 1,2 s à livrer sa première image, le défaut (1 s)
  fait échouer le démarrage.
- Pour l'instant, seule la caméra avant est branchée. Une « Generic USB HD Camera » apparaît
  dans `lsusb` sans `/dev/video` : câble ou alimentation de la caméra de poignet à vérifier.
- Sans `--host.connection_time_s`, le host s'arrête au bout de 30 secondes. `tmux` n'est pas
  installé sur la Pi (`sudo apt install tmux`) : en attendant, garder la fenêtre SSH ouverte.
- Arrêter le host coupe le couple des moteurs : **tenir le bras**, il tombe.
- « No command available » en boucle est normal tant qu'aucun laptop n'est connecté.

Sur le laptop :

```bash
make teleop       # leader pour le bras, clavier pour la base, flux dans Rerun
```

Clavier : `w` `s` avancer et reculer, `a` `d` gauche et droite, `z` `x` tourner, `r` `f`
vitesse. `p` enregistre la pose courante du bras dans `configs/poses_captured.yaml`.

- **Le clavier est lu dans toutes les fenêtres**, pas seulement celle de la téléop : taper
  dans un chat ou un navigateur fait rouler le robot. Ne rien taper ailleurs pendant la
  téléop ; Échap coupe le clavier.
- Avant de lancer, mettre le leader à peu près dans la pose du bras du robot : sinon le
  bras du robot rejoint le leader d'un coup.
- Windows : le leader est sur un port `COMx` (`teleop.leader_port` dans `configs/local.yaml`) ;
  `make` vient de MSYS2 sous le nom `mingw32-make` (alias PowerShell possible :
  `Set-Alias make mingw32-make` dans le profil).

## 5. Mise en place avant toute collecte (porte G2)

À faire dans cet ordre, une fois, puis **ne plus rien toucher au montage**.

1. **Fixer les caméras** définitivement. Photographier le montage sous deux angles et
   mettre les photos dans `assets/`. Tracer un repère au marqueur.
2. **Mesurer** la caméra avant (hauteur de l'objectif, inclinaison, avance par rapport au
   centre de la base) et remplir `perception.camera_model` dans `configs/makai.yaml`.
3. **Définir la pose `home`** du bras : repliée, hors du champ de la caméra avant, pince
   au-dessus de la zone de saisie. La capturer (`p` pendant la téléop) et la copier dans
   `configs/arm_poses.yaml`.
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
| `Timed out waiting for frame from camera ... after 1000 ms` | Webcam lente à démarrer : `warmup_s: 3` dans `--robot.cameras` |
| Le bras avance par à-coups, latence | Réseau (section 2, « Réseau ») : mesurer avec `scripts/net_check.py`. Puis `--arm_acceleration` plus bas |
| Les roues bougent quand on tape ailleurs | Clavier lu dans toutes les fenêtres (section 4) |
| La Pi ne répond plus après un changement de réseau | Attendre 2 à 3 min (elle essaie les réseaux connus), puis débrancher et rebrancher son alimentation USB-C |
| `lekiwi.local` ne se résout pas | mDNS capricieux sous Windows : utiliser l'IP |
