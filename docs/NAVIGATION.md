# Navigation : balayer la pièce, ramasser, déposer, reprendre

Le robot se comporte comme un aspirateur. Il passe tout seul d'un mode à l'autre :

- **Mode aspirateur.** Il parcourt la pièce en rangées, sans jamais tourner : il reste face à
  la pièce, perpendiculaire au mur de la poubelle, et glisse de côté le long de chaque rangée.
- **Mode détection.** Dès qu'il voit un objet, il quitte sa rangée, se place devant, le
  ramasse avec le modèle entraîné pour cet objet et le porte à la poubelle. Puis il revient
  exactement là où il avait quitté sa rangée, se remet perpendiculaire au mur, et repart en
  mode aspirateur.

Tout se pilote depuis une seule page, la **console** (`scripts/drive.py`), décrite à la
section 3. Rien de ce qui suit n'a encore tourné sur le vrai robot : la section 6 dit ce qui
est vérifié, et comment.

## 1. Ce que fait le robot

```text
SWEEP ──objet en vue──► APPROACH ──► PICK ──► DOCK ──► GO_TO_STATION ──► DROP ──► BACK_OFF
  ▲                                                                                  │
  └──────────────────────── RESUME (retour à l'endroit quitté) ◄─────────────────────┘
SWEEP ──pièce balayée──► RETURN_HOME ──► DONE
```

| État | Ce qui se passe | Sur quoi le robot s'appuie |
|---|---|---|
| SWEEP | **mode aspirateur** : glisse le long des rangées, toujours face à la pièce | odométrie |
| APPROACH | se place devant l'objet, à la distance de saisie | caméra avant : détecteur, puis projection au sol ; les 45 derniers centimètres à l'odométrie |
| PICK | le modèle de l'objet pilote le bras, jusqu'à 3 essais | caméras avant et de poignet |
| DOCK | retourne au point d'arrêt devant la station | odométrie |
| GO_TO_STATION | finit sur le marqueur de la station | caméra avant : marqueur ArUco |
| DROP, BACK_OFF | dépose, puis recule | poses du bras |
| RESUME | revient où il avait quitté sa rangée et se remet perpendiculaire au mur | odométrie, recalée |
| RETURN_HOME | pièce balayée : revient devant la poubelle | odométrie, puis marqueur |

Tous les états sauf SWEEP forment le **mode détection** : le robot y tourne librement, comme
avant. La console affiche le mode en cours.

**Les rangées.** La base est holonome : elle peut glisser de côté sans tourner. En mode
aspirateur le robot garde donc le cap du départ. Il glisse le long d'une rangée parallèle au
mur, avance d'une rangée, repart dans l'autre sens. La caméra regarde toujours la bande de sol
devant lui, celle qu'il n'a pas encore atteinte : il ne roule jamais sur du sol qu'il n'a pas
vu. La première rangée est la ligne de départ.

**La carte.** Le robot n'a pas de capteur de distance. Sa carte est faite de deux choses :
l'odométrie (où il est) et l'empreinte au sol de la caméra avant (ce qu'il voit de là). Une
case est « vue » quand la caméra l'a regardée. La carte retient aussi le chemin parcouru et
chaque objet : vu, en approche, ramassé, déposé, abandonné.

**Le recalage.** Les roues glissent, donc l'odométrie dérive. La position de la poubelle
dans la carte est connue : chaque fois que le robot voit son marqueur de près, il en déduit
où il est vraiment, position et cap, et efface la dérive accumulée. Il le fait à chaque
dépose et à la fin. On peut aussi lui demander d'y retourner tous les N mètres
(`recheck_after_m`).

## 2. Préparer la salle

L'origine de la carte est la pose de départ du robot : **devant la poubelle, dos à la
poubelle, face à la pièce**. `x` va vers la pièce, `y` vers la gauche.

- [ ] **La poubelle** : contre un bord de la zone, marqueur ArUco n° 1 collé verticalement
      sur sa face avant, **au ras du sol** : plus haut, il sort de l'image quand le robot
      s'approche (`docs/ARCHITECTURE.md`) (`make markers` pour les imprimer). Un panier
      à linge prend le marqueur n° 0.
- [ ] **Le robot** : centre de la base à 35 cm du marqueur, dans son axe, dos à la poubelle.
- [ ] **La zone à balayer** : un rectangle devant le robot. Mesurer sa longueur (dans l'axe
      du robot) et sa largeur (centrée sur lui), et les écrire dans `configs/local.yaml` :

```yaml
navigation:
  sweep:
    room: {length_m: 2.0, width_m: 1.6, margin_m: 0.30}
```

- [ ] **Rien d'autre au sol** que les objets à ramasser : le robot n'a aucun capteur
      d'obstacle et ne contourne rien.
- [ ] **La ligne de départ dégagée** : rien à gauche ni à droite du robot, le long du mur de
      la poubelle. C'est la première rangée, et la seule que la caméra n'a pas vue avant d'y
      passer. Les deux coins de la zone de ce côté-là ne sont jamais vus : ne rien y poser.
- [ ] **La caméra avant calibrée** sur le sol : `make calibrate-ground`
      (`docs/ARCHITECTURE.md`, « Estimer la distance avec une seule caméra »), ou, sans
      imprimante, une feuille à carreaux et cinq croix de tape (ci-dessous).
- [ ] **Le détecteur réentraîné sur des images de cette salle**, prises par la caméra du
      robot (section 5).
- [ ] **Les poses du bras** `drop_reach` et `drop_open` relevées dans
      `configs/arm_poses.yaml`. Elles sont encore à zéro : sans elles, la dépose envoie le
      bras dans une pose qui n'a aucun sens.
- [ ] **Le modèle** : `manipulation.pick.policy_path` dans `configs/local.yaml`. Avec un seul
      type d'objet, un seul modèle suffit, et une erreur de classement du détecteur ne change
      rien. Avec deux : `manipulation.pick.policies` (un modèle par catégorie).

### Calibrer la caméra avant sans imprimante

Une feuille mesure le champ de vision, la hauteur et l'inclinaison de la caméra ; cinq croix
mesurées au mètre vérifient le résultat et fixent l'origine. Une seule photo, une vingtaine de
minutes. Testé sur une caméra simulée (0,4 à 0,7 cm d'erreur restante de 30 cm à 1,2 m) ;
pas encore sur le robot (15 nov.).

1. Robot à sa place, bras en `home` hors du champ : ne plus toucher au robot ni à la caméra
   jusqu'à la photo.
2. **La feuille** : un rectangle tracé au stylo sur les lignes d'une feuille à petits
   carreaux, 52 × 36 carreaux = 26 × 18 cm (vérifier au mètre que 20 carreaux font 10 cm).
   Scotchée bien à plat (le tape hors du rectangle), en bas de l'image, grand côté vers l'avant.
3. **Les croix** : un carré de tape gris, une croix au stylo dessus, son centre pile sur la
   mesure. Mesurées depuis le point du sol **sous l'objectif** (le bout du mètre pendu à
   l'objectif) : 30, 50, 80 et 120 cm dans l'axe, et 50 cm devant / 20 cm à gauche.
4. **La photo** : console lancée (`drive.py --link host`), puis
   `http://localhost:8000/api/camera/front.jpg?download=1`.
5. **Dans Paint** (la position du pixel s'affiche en bas à gauche) : les 4 coins du rectangle,
   dans l'ordre proche-gauche, proche-droite, loin-droite, loin-gauche (proche = bas de
   l'image) ; le centre de chaque croix dans un fichier CSV, `u` et `v` laissés vides pour une
   croix hors de l'image :

```text
u,v,x_m,y_m,name
,,0.30,0.00,A
,,0.50,0.00,B
,,0.80,0.00,C
,,1.20,0.00,D
,,0.50,0.20,E
```

6. **Le calcul** :

```bash
uv run python scripts/camera_from_sheet.py front.jpg "u,v u,v u,v u,v" --size 0.26,0.18 \
    --check data/ground_calib/marks.csv --from-camera
```

Il affiche l'erreur sur chaque croix (viser moins de 2 cm après correction de l'origine) et
le bloc `perception.camera_model` à mettre dans `configs/makai.yaml` : à commiter, c'est une
propriété du robot. `--from-camera 0.07` si l'on a mesuré la distance de l'objectif au centre
de la base (ligne des deux roues avant au sol, plus 6 cm) ; sans valeur, le `x_offset_m`
actuel (5 cm). Pas de `configs/ground_plane.yaml` : il remplacerait ce modèle. Le même modèle
donne aussi la distance des marqueurs des stations.

Ensuite, la cible de l'approche : mesurer depuis le même point la zone de saisie (là où était
l'objet pendant l'enregistrement), ajouter la distance objectif → centre de la base, et
l'écrire dans `navigation.approach.goal_x_m` et `goal_y_m`.

## 3. Lancer

**D'abord, sans robot**, vérifier que la mission démarre avec la configuration de ce laptop
(détecteur, calibration du sol, modèles, poses du bras). Un fichier manquant apparaît ici,
avec son nom :

```bash
uv run python scripts/mission_check.py
```

Puis le host tourne sur la Pi (`docs/SETUP.md`, section 4). Sur le laptop :

```bash
uv run python scripts/drive.py --link host
```

Ouvrir `http://localhost:8000`, onglet **Mission**, bouton **Start mission**. Le premier
démarrage charge le détecteur et les modèles (quelques secondes).

Sans robot, pour voir une mission simulée, avec des roues qui glissent :

```bash
uv run python scripts/drive.py --sim
```

Sans la page : `uv run makai-mission --sweep` (ajouter `--sim` sans robot).

**La console** a quatre onglets :

| Onglet | Contenu |
|---|---|
| Mission | la carte en direct, le mode (aspirateur ou détection), l'état, les compteurs, les deux caméras, le journal ; Start, Stop |
| Drive | la page de conduite manuelle, inchangée (sticks, mesures, moteurs) ; seule à `/drive` |
| Cameras | les deux caméras en grand |
| Data | les essais d'entraînement et les figures de `docs/figures` |

**Arrêter.** Le bouton rouge STOP (ou la barre d'espace) est l'arrêt d'urgence : il coupe la
mission où qu'elle en soit, même pendant une saisie, et bloque les roues jusqu'à « Resume ».
Le bouton Stop de l'onglet Mission arrête la mission sans bloquer les roues.

**Après un arrêt**, une nouvelle mission repart de zéro : elle suppose le robot devant la
poubelle, face à la pièce. Le remettre en place (onglet Drive) avant de relancer.

Sur la Pi, en mode filaire, il n'y a pas de mission (les modèles ont besoin du laptop) : la
page d'accueil reste la page de conduite.

## 4. Régler

Dans `configs/makai.yaml`, section `navigation.sweep` (valeurs d'une salle : `local.yaml`).

| Réglage | Défaut | Effet |
|---|---|---|
| `room.length_m`, `room.width_m` | 2,0 × 1,6 m | la zone à balayer, devant le robot |
| `room.margin_m` | 0,30 m | le centre du robot reste à cette distance des bords |
| `pattern` | `rows` | `rows` : mode aspirateur en rangées, sans tourner. `lanes` : l'ancien parcours, où le robot tourne pour suivre des couloirs qui s'enfoncent dans la pièce |
| `lane_spacing_m` | 0,5 m | écart entre deux rangées ; plus petit = plus sûr de tout voir, plus long |
| `sweep_speed` | 0,15 m/s | vitesse le long des rangées |
| `recheck_after_m` | 0 | retour au marqueur après tant de mètres sans recalage ; 0 = seulement aux déposes |
| `stations` | poubelle en (−0,35 ; 0) | où est chaque station, et où le robot s'arrête devant |
| `marker_scan_deg` | jusqu'à ±180° | où chercher le marqueur quand la dérive l'a sorti de l'image |

Un objet vu hors de la zone (à plus de 10 cm des bords) est ignoré. Un objet abandonné après
trois saisies ratées n'est plus approché.

## 5. Réentraîner le détecteur sur la caméra du robot

Le détecteur d'origine a appris sur des photos de téléphone. Sur la caméra du robot, il ne
trouve la canette que dans une image sur deux (`docs/EXPLORATIONS.md`). Il s'annote tout seul
à partir de paires d'images prises du même endroit, avec l'objet puis sans :

```text
data/robot_frames/can/vue01.jpg         la canette au sol
data/robot_frames/can/vue01_empty.jpg   le même cadrage, canette retirée
```

Dans une nouvelle salle : robot immobile, une image avec l'objet (onglet Drive, « Save
image »), on retire l'objet, une image sans. Une vingtaine de paires par objet, à des
distances de 30 cm à 1,5 m. Puis, environ dix minutes :

```bash
uv run python scripts/train_detector.py --name v3 --base models/detector_v2.pt \
    --trash data/robot_frames/can --clothing data/robot_frames/sock
```

Nos épisodes de saisie donnent ces paires gratuitement : première image de la caméra avant
(objet au sol), dernière image (objet ramassé).

## 6. Ce qui est vérifié

En simulation, avec la machine à états et la navigation réelles (`make sim`, et les 19 tests
de `tests/test_sweep.py`), en rangées :

| Situation simulée | Résultat |
|---|---|
| Pièce de 2,4 × 1,8 m, 4 objets, 2 stations | 4 déposés dans la bonne station, retour à 2 cm de l'origine, en 3 min 19 (3 min 47 avec l'ancien parcours en couloirs) |
| Même pièce, vide | aucune rotation pendant tout le balayage (l'ancien parcours en demandait 700°) ; le balayage seul voit 91 % du sol : il manque les 15 cm aux pieds du robot et les deux coins près du mur de départ |
| Roues qui glissent de 4 %, cap qui dérive de 1,7° par mètre | 4 sur 4 ; chaque visite au marqueur corrige 4 à 46 cm ; retour à 3 cm de l'origine. Le robot se croit perpendiculaire au mur, mais il est de travers de 12° au pire, juste avant un recalage |
| Même dérive, marqueurs jamais vus | 2 déposés sur 4, puis échec : le robot se croit devant la station alors qu'il en est trop loin pour déposer ; il finit à 50 cm de l'origine |
| Dérive doublée | 4 sur 4, retour à 5 cm |
| Marqueur jamais vu, sans dérive | dépose à l'odométrie, mission terminée |
| Ancien parcours (`pattern: lanes`) | toujours testé : 4 sur 4 |
| Objet impossible à saisir | abandonné après 3 essais, jamais réapproché |
| Objet hors de la zone | ignoré |

Sur des images réelles : la lecture de l'orientation du marqueur (6° près sur des marqueurs
tournés de ±30°), et le choix du modèle selon l'objet.

**Pas vérifié** : tout ce qui touche au vrai robot. En particulier la dérive réelle des
roues, surtout quand la base glisse de côté (le mode aspirateur ne fait que ça), la portée
réelle du détecteur pendant le balayage, la visibilité du marqueur à 35 cm,
et la dépose. Le cap final, après le dernier demi-tour fait à l'odométrie, peut être faux de
10 à 20° ; la position, elle, est recalée.

## 7. Si ça se passe mal

| Ce qu'on voit | Cause probable | Quoi faire |
|---|---|---|
| Le robot passe à côté d'un objet | détecteur aveugle sur ce sol, ou objet « hors zone » | réentraîner le détecteur (section 5) ; agrandir `room` |
| Il s'arrête trop loin ou trop près de l'objet | caméra avant mal calibrée sur le sol | `make calibrate-ground`, puis `navigation.approach.goal_x_m` |
| Il tourne sur place devant la station | marqueur hors de l'image | marqueur plus haut ou plus grand ; il finit par déposer à l'odométrie |
| Il dépose à côté | station mal placée dans `stations`, ou dérive sans marqueur | mesurer la position de la station ; `recheck_after_m: 4` |
| Les rangées partent de travers | dérive du cap : le robot n'a que ses roues pour savoir s'il est perpendiculaire au mur, sauf devant le marqueur | `recheck_after_m: 3` ; réduire `sweep_speed` |
| La base glisse mal de côté (à-coups, forte dérive) | roues ou sol peu adaptés au déplacement latéral | `pattern: lanes` : l'ancien parcours, où le robot avance et tourne |
| Il heurte un bord | zone déclarée trop grande | réduire `room`, augmenter `margin_m` |
| « Could not start » dans la console | modèle, calibration ou poids introuvable | le message dit lequel |
