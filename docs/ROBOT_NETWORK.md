# Se connecter au robot : choisir son réseau

**Pour Claude** : quand un coéquipier veut se connecter au robot, lui demander son OS
(Windows ou macOS) et s'il préfère la simplicité ou la latence la plus basse, puis suivre
la section correspondante. Mots de passe (Pi, « makai-kiwi », hotspots) : chat d'équipe,
**jamais dans le dépôt**. Démarrer le host et la téléop ensuite : `docs/SETUP.md`, section 4.

La Pi n'est que sur **un réseau à la fois** : la personne qui la change prévient l'équipe.

## En bref

| Réseau | IP de la Pi | Latence mesurée | Internet sur le laptop | Pour qui |
|---|---|---|---|---|
| **iPhone « Cyrine »** (par défaut, D15) | `172.20.10.3` en général | 38 à 143 ms, pics jusqu'à 1,2 s | oui | tout le monde, rien à régler |
| **A** : la Pi émet « makai-kiwi » | `10.42.0.1` | **6 ms**, flux régulier | seulement par câble (iPhone en USB, Ethernet) | Windows et macOS |
| **B** : le hotspot de ton laptop | Windows `192.168.137.50`, macOS `192.168.2.50` | ~50 ms (Windows partageant son Wi-Fi) | oui | Windows ; macOS seulement avec Internet par câble |

Choisir : l'iPhone pour commencer ; A si le bras saute (collecte, démo) ; B si on veut un
réseau à soi et garder Internet en Wi-Fi sous Windows.

Après tout changement : `robot.remote_ip` dans `configs/local.yaml` = IP de la Pi, puis
`uv run python scripts/net_check.py` pour vérifier (téléop arrêtée).

## SSH vers la Pi (commun)

```bash
ssh kiwi@<ip-de-la-pi>          # Windows (PowerShell) et macOS (Terminal) ont ssh
conda activate lerobot && cd ~/lerobot
```

`lekiwi.local` marche en général sous macOS, mal sous Windows : préférer l'IP. Pour trouver
la Pi sur l'iPhone : essayer `172.20.10.2` à `172.20.10.14`.

## iPhone « Cyrine » (par défaut)

1. Laptop en Wi-Fi sur « Cyrine ».
2. `remote_ip: 172.20.10.3` dans `configs/local.yaml`.
3. `ssh kiwi@172.20.10.3`.

La Pi y revient toute seule à chaque démarrage si aucun hotspot de laptop connu n'émet.

## Option A : la Pi est le point d'accès

**Avant** : donner Internet au laptop par câble, sinon il n'a plus Internet sur « makai-kiwi »
(la Pi ne distribue pas de passerelle, exprès).

- **macOS** : brancher l'iPhone en USB, partage de connexion activé sur l'iPhone : le service
  réseau « iPhone USB » apparaît tout seul.
- **Windows** : installer l'app « Apple Devices » (Microsoft Store), brancher l'iPhone,
  « Faire confiance », partage de connexion activé ; un adaptateur « Apple Mobile Device
  Ethernet » apparaît (redémarrer Windows s'il ne vient pas).

**Passer la Pi en A** (depuis le réseau où elle est, en SSH) :

```bash
sudo nmcli connection up makai-ap      # la session SSH coupe : normal
```

**Puis sur le laptop** : rejoindre le Wi-Fi « makai-kiwi » ; couper tout autre usage du Wi-Fi
(point d'accès mobile Windows, partage Internet macOS) ; `remote_ip: 10.42.0.1` ;
`ssh kiwi@10.42.0.1`. Tous ceux qui veulent le robot rejoignent « makai-kiwi ».

**Revenir à l'iPhone** : redémarrer la Pi (débrancher, rebrancher l'USB-C), ou en SSH
`sudo nmcli connection up netplan-wlan0-Cyrine`.

## Option B : le hotspot de ton laptop

### 1. Allumer le hotspot

- **Windows** : Réglages → Réseau et Internet → Point d'accès sans fil mobile. Nom, mot de
  passe, bande **« Toute bande disponible »** (une seule carte Wi-Fi ne fait pas 2,4 et 5 GHz
  à la fois : sinon le hotspot s'affiche activé mais n'émet rien), **économie d'énergie
  désactivée**. L'allumer depuis les Réglages (démarré par PowerShell, il n'émettait rien).
- **macOS** : il faut Internet par câble (iPhone en USB ou Ethernet) : macOS ne partage pas
  le Wi-Fi vers le Wi-Fi. Réglages Système → Général → Partage → Partage Internet :
  partager « iPhone USB » (ou Ethernet) vers **Wi-Fi** ; « Options Wi-Fi » : nom, sécurité
  WPA2/WPA3 Personnel, mot de passe. Vérifier le sous-réseau avec `ifconfig bridge100`
  (en général `192.168.2.1`). **Pas encore testé sur notre robot.**

### 2. Faire connaître ton hotspot à la Pi (une fois par laptop)

Pendant que la Pi est sur l'iPhone, en SSH, remplacer `<prenom>`, `<NOM>`, `<MDP>` et
choisir la ligne d'IP selon ton OS :

```bash
# Windows : IP=192.168.137.50  GW=192.168.137.1    macOS : IP=192.168.2.50  GW=192.168.2.1
IP=192.168.137.50; GW=192.168.137.1
sudo nmcli connection add type wifi ifname wlan0 con-name laptop-<prenom> ssid "<NOM>" \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk "<MDP>" \
  connection.autoconnect yes connection.autoconnect-priority 10 802-11-wireless.powersave 2 \
  ipv4.method manual ipv4.addresses $IP/24 ipv4.gateway $GW ipv4.dns $GW ipv6.method disabled
sync                                   # sans ça, une coupure de courant peut vider le profil
nmcli -f NAME,AUTOCONNECT-PRIORITY connection show
```

Profils déjà connus : `makai-laptop` (laptop Windows « PC-08792 6521 »).

### 3. Faire venir la Pi sur ton hotspot

La Pi ne change pas de réseau toute seule une fois connectée. Au choix :

- en SSH : `sudo nmcli connection up laptop-<prenom>` (la session coupe ; si ça échoue,
  la Pi revient seule sur l'iPhone) ;
- ou redémarrer la Pi avec ton hotspot allumé : au démarrage, elle préfère les hotspots
  de laptop connus (priorité 10) à l'iPhone.

Puis `remote_ip` = IP de ton OS ci-dessus et `ssh kiwi@<cette IP>`.

## Pièges

- **Une carte Wi-Fi qui sert deux réseaux** (client + hotspot) saute de canal : 1 ping sur
  3 à 130 ms mesuré. En option A, couper le hotspot du laptop.
- **Les deux caméras pèsent environ 60 Mbit/s** (deux images JPEG 640×480 en qualité 90,
  30 fois par seconde ; taille mesurée sur nos photos de sol). Quand le lien ne suit pas, les
  images arrivent en retard : 2 s observées à 10 m avec des tables sur le trajet, presque
  rien de près (14 nov., minuit). Pour la collecte et la démo : option A, laptop à moins de
  5 m en vue directe, et **un seul programme connecté au host** (deux clients se partagent
  les images, chacun en reçoit la moitié). Vérifier avec `scripts/net_check.py`, puis
  `scripts/preflight.py` : chaque caméra doit livrer près de 30 nouvelles images par seconde.
  Une personne entre la Pi et le laptop suffit à faire décrocher un lien sans marge. S'il
  reste du retard en option A : `--jpeg_quality=75` sur le host (`docs/SETUP.md`, section 4).
  Débit radio vu par la Pi : `iw dev wlan0 station dump` en option A, `iw dev wlan0 link`
  sinon (ligne « tx bitrate » ; il en faut plusieurs fois le poids du flux).
- La Pi a perdu son alimentation plusieurs fois : si elle disparaît, attendre 2 à 3 min
  (elle essaie les réseaux connus), puis débrancher et rebrancher son USB-C.
- macOS : autoriser le Terminal dans Confidentialité → Surveillance de l'entrée et
  Accessibilité, sinon le clavier de la téléop ne marche pas (`docs/SETUP.md`, section 1).
- Leader : port `COMx` sous Windows, `/dev/tty.usbmodem…` sous macOS (`lerobot-find-port`),
  dans `teleop.leader_port` de `configs/local.yaml`. Calibration du leader :
  `cp -R calibration/. ~/.cache/huggingface/lerobot/calibration/`.
