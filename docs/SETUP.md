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
`configs/local.yaml` → `robot.remote_ip` (propre à chaque laptop). La Pi connaît trois
réseaux (profils NetworkManager). **Choix actuel : le hotspot iPhone**, le plus simple
(décision D11 dans `docs/DECISIONS.md`) ; l'option A reste prête si le bras saute trop.

| Option | Réseau | IP de la Pi | Mesuré (sam. 14, `scripts/net_check.py`) |
|---|---|---|---|
| **iPhone, retenue** | hotspot iPhone « Cyrine », 2,4 GHz (profil `netplan-wlan0-Cyrine`) ; la Pi y va seule au démarrage | `172.20.10.3` en général (DHCP) | laptop en Wi-Fi : 50 à 143 ms, pics jusqu'à 1,2 s ; laptop en USB sur l'iPhone : 38 ms (p99 294) |
| A, prête | la Pi est le point d'accès « makai-kiwi », 5 GHz canal 36 (profil `makai-ap`, jamais au démarrage) | `10.42.0.1`, fixe | aller-retour 6 ms (p99 28), flux 29,9 images/s, **aucun trou > 100 ms** |
| B | hotspot Windows du laptop « PC-08792 6521 » (profil `makai-laptop`, priorité 10) | `192.168.137.50`, fixe | aller-retour 51 ms (p99 211) |

Mots de passe (Pi, « makai-kiwi », hotspots) : chat d'équipe, jamais dans le dépôt.

**Se connecter au robot (cas normal, iPhone)** : laptop sur « Cyrine » ;
`remote_ip: 172.20.10.3` dans `configs/local.yaml` ; `ssh kiwi@172.20.10.3` pour lancer le
host (section 4). Si l'IP a changé : la chercher parmi `172.20.10.2` à `172.20.10.14`
(le hotspot iPhone n'en a que 13).

**Passer en option A** (si le bras saute trop pendant la collecte) :

1. Sur la Pi, en SSH : `sudo nmcli connection up makai-ap` (la session SSH coupe).
2. Sur le laptop : rejoindre le Wi-Fi « makai-kiwi ». Pour garder Internet, brancher
   l'iPhone en USB avant (partage de connexion, voir plus bas) ; sinon le laptop n'a plus
   Internet tant qu'il est sur « makai-kiwi ». Couper le point d'accès mobile Windows.
3. `remote_ip: 10.42.0.1` dans `configs/local.yaml`, puis `ssh kiwi@10.42.0.1`.

**Revenir à l'iPhone** : redémarrer la Pi (débrancher, rebrancher l'USB-C : `makai-ap` ne
démarre jamais seul), ou en SSH `sudo nmcli connection up netplan-wlan0-Cyrine` ; remettre
`remote_ip: 172.20.10.3`.

**Détails de l'option A** :

- La Pi distribue des adresses `10.42.0.x` mais **pas de passerelle** : un laptop connecté à
  « makai-kiwi » garde son accès Internet par une autre voie (partage USB du téléphone, ou
  Ethernet). Sans autre voie, il n'a plus Internet tant qu'il est sur « makai-kiwi ».
- Windows + iPhone : installer l'app « Apple Devices » (Microsoft Store), brancher l'iPhone
  en USB, partage de connexion activé, « Faire confiance » : un adaptateur « Apple Mobile
  Device Ethernet » apparaît. Le Wi-Fi est alors libre pour « makai-kiwi ».
- **Couper tout autre usage du Wi-Fi du laptop** (point d'accès mobile Windows notamment) :
  une carte Wi-Fi qui sert deux réseaux saute d'un canal à l'autre. Mesuré : 1 ping sur 3
  à 130 ms avec le point d'accès Windows allumé, 4 ms de moyenne une fois éteint.
- La Pi n'a pas Internet en mode point d'accès : pour `apt` ou `pip`, passer
  temporairement sur un autre réseau (commandes ci-dessous).
- Fichiers sur la Pi : `/etc/NetworkManager/system-connections/makai-ap.nmconnection`,
  `/etc/NetworkManager/dnsmasq-shared.d/makai-no-gateway.conf`.

**Option B** : réglages Windows → Réseau → Point d'accès mobile, bande « Toute bande
disponible » si le laptop est déjà en Wi-Fi sur un autre réseau (une seule carte ne fait
pas 2,4 et 5 GHz à la fois : le point d'accès semble allumé mais n'émet rien),
**économie d'énergie désactivée**, pas de veille. Le robot dépend alors de ce laptop.
L'allumer depuis les Réglages : démarré par l'API Windows (PowerShell), il s'affichait
« activé » sans rien émettre (carte MediaTek MT7921).

L'économie d'énergie Wi-Fi de la Pi est **désactivée**
(`/etc/NetworkManager/conf.d/99-wifi-powersave-off.conf`) : elle provoquait des pics de 1 s.

Changer de réseau, sur la Pi (la session SSH coupe ; se reconnecter à la nouvelle IP) :

```bash
sudo nmcli connection up makai-ap                # A : la Pi devient le point d'accès
sudo nmcli connection up makai-laptop            # B : hotspot du laptop
sudo nmcli connection up netplan-wlan0-Cyrine    # hotspot iPhone
nmcli -f NAME,AUTOCONNECT,AUTOCONNECT-PRIORITY connection show
```

Un profil créé avec `nmcli connection add` peut disparaître si la Pi perd son alimentation
juste après (fichier vide au redémarrage) : écrire le fichier `.nmconnection` directement,
puis `sync` et `sudo nmcli connection reload`.

**Mesurer un réseau**, sans faire bouger le robot (téléop arrêtée) :

```bash
uv run python scripts/net_check.py --ip 10.42.0.1        # A ; B : 192.168.137.50 ; iPhone : 172.20.10.3
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

**Fait le sam. 14** : bras du robot calibré sur la Pi, copie dans le dépôt
(`calibration/robots/lekiwi/makai_kiwi.json`, 6 moteurs du bras et 3 roues) ; leader
calibré, dans le dépôt (`calibration/teleoperators/so_leader/makai_leader.json`). Pour les
installer sur un autre laptop : `cp -R calibration/. ~/.cache/huggingface/lerobot/calibration/`.
Si la carte SD de la Pi est refaite, recopier `makai_kiwi.json` au même endroit sur la Pi
au lieu de recalibrer. Un bras calibré
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
| `Timed out waiting for frame from camera ... after 1000 ms` | Webcam lente à démarrer : `warmup_s: 3` dans `--robot.cameras` |
| Le bras avance par à-coups, latence | Réseau (section 2, « Réseau ») : mesurer avec `scripts/net_check.py`. Puis `--arm_acceleration` plus bas |
| Les roues bougent quand on tape ailleurs | Clavier lu dans toutes les fenêtres (section 4) |
| La Pi ne répond plus après un changement de réseau | Attendre 2 à 3 min (elle essaie les réseaux connus), puis débrancher et rebrancher son alimentation USB-C |
| `lekiwi.local` ne se résout pas | mDNS capricieux sous Windows : utiliser l'IP |
