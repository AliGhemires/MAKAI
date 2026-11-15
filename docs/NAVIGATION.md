# Navigation : parcourir la zone, ramasser, déposer, reprendre

Le robot parcourt une zone et range ce qu'il y trouve. Deux usages, choisis dans la console
avant de lancer la mission :

| | Vacuum & collect | Scan & collect |
|---|---|---|
| Exemple | une chambre d'hôtel : il passe l'aspirateur et en profite pour ramasser | une rue : il patrouille à la recherche de déchets et de vêtements |
| But | passer sur tout le sol | trouver les objets |
| Parcours | des rangées serrées, sans jamais tourner : il reste face à la zone, perpendiculaire au mur de la poubelle, et glisse de côté | de larges couloirs ; il avance en regardant à gauche puis à droite |
| Ce qu'il ramasse | ce qui se trouve sur son passage, à moins d'un mètre | tout ce qu'il repère, aussi loin que la caméra voit |

Dans les deux cas, une fois l'objet en vue, le robot quitte son parcours, se place devant,
le ramasse avec le modèle entraîné pour cet objet et le porte à la poubelle. Puis il revient
exactement là où il avait quitté son parcours et continue.

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
| SWEEP | suit son parcours : glisse le long des rangées (Vacuum), ou avance en balayant du regard (Scan) | odométrie |
| APPROACH | se place devant l'objet, à la distance de saisie | caméra avant : l'objet est remesuré à chaque image et le robot se dirige sur cette mesure, pas sur une position de la carte ; l'odométrie ne sert qu'aux derniers centimètres, quand l'objet passe sous le champ de la caméra, et quand il sort un instant de l'image |
| PICK | le modèle de l'objet pilote le bras, jusqu'à 3 essais | caméras avant et de poignet |
| DOCK | va vers la station ; dès qu'il la voit, passe à l'état suivant | odométrie, corrigée par la caméra, tant que la station n'est pas en vue |
| GO_TO_STATION | se dirige sur la station vue par la caméra, jusqu'à 35 cm devant elle | caméra avant : bande de scotch du carton (ou marqueur ArUco) |
| DROP, BACK_OFF | dépose, puis recule | poses du bras |
| RESUME | revient où il avait quitté son parcours, dans le bon sens | odométrie, recalée |
| RETURN_HOME | pièce balayée : revient devant la poubelle | odométrie, puis marqueur |

Dans tous les états sauf SWEEP, le robot s'occupe d'un objet : il y tourne librement. La
console affiche ce qu'il fait : Vacuuming, Scanning ou Collecting.

**Vacuum : les rangées.** La base est holonome : elle peut glisser de côté sans tourner. Le
robot garde donc le cap du départ. Il glisse le long d'une rangée parallèle au mur, avance
d'une rangée, repart dans l'autre sens. La caméra regarde toujours la bande de sol devant
lui, celle qu'il n'a pas encore atteinte : il ne roule jamais sur du sol qu'il n'a pas vu.
La première rangée est la ligne de départ. Il ne quitte sa rangée que pour un objet à moins
de `pickup_range_m` (1 m) : ceux qui sont plus loin, il les voit, les note sur la carte, et
les ramassera quand il y arrivera.

**Scan : le regard qui balaie.** Le robot suit un couloir au milieu de chaque bande de
`scan_swath_m` (1,6 m) de large : un seul couloir pour une zone de cette largeur. Avant de
partir, puis tout le long, son cap oscille de 60° à gauche et à droite de sa route pendant
que la base continue tout droit : la caméra couvre ainsi une bande large. Chaque coup d'œil
à gauche est suivi du même à droite, donc ce que les roues glissent en tournant s'annule au
lieu de s'ajouter. Il avance lentement (8 cm/s) pour avoir le temps de regarder des deux côtés.

**Le principe : l'odométrie est mauvaise, la caméra décide.** Tout ce que le robot peut voir,
il le rejoint en le regardant : un objet, une station. L'odométrie ne sert qu'à suivre le
parcours entre deux repères, et la caméra la corrige dès qu'une station est dans l'image.

**La carte.** Le robot n'a pas de capteur de distance. Sa carte est faite de deux choses :
l'odométrie (où il est) et l'empreinte au sol de la caméra avant (ce qu'il voit de là). Une
case est « vue » quand la caméra l'a regardée. La carte retient aussi le chemin parcouru et
chaque objet : vu, en approche, ramassé, déposé, abandonné.

**Le recalage : la caméra corrige l'odométrie.** Les roues glissent, donc l'odométrie
dérive, surtout en rotation (`docs/DEBUG_ODOMETRY.md`). La position de la poubelle dans la
carte est connue, et son marqueur sert de repère de deux façons :

- **en continu, dès qu'il est dans l'image** (jusqu'à 2,5 m) : la direction dans laquelle le
  robot voit le marqueur corrige son cap, et la distance du marqueur corrige sa position, un
  peu à chaque image ;
- **de près, à l'arrivée devant la poubelle** : l'inclinaison du marqueur donne le cap
  directement, et le robot efface toute la dérive accumulée.

Avec la poubelle en face du robot (section 2), le marqueur reste dans l'image pendant presque
tout le balayage : l'odométrie est tenue en permanence. Avec la poubelle derrière lui, il
n'est vu qu'aux déposes ; on peut alors demander un retour au marqueur tous les N mètres
(`recheck_after_m`).

## 2. Préparer la salle

L'origine de la carte est la pose de départ du robot, **face à la zone**. `x` va vers la
zone, `y` vers la gauche. Deux dispositions :

| | Poubelle en face (recommandée) | Poubelle derrière |
|---|---|---|
| Où est la poubelle | de l'autre côté de la zone, son marqueur tourné vers le robot | juste derrière le robot, qui lui tourne le dos |
| Pose de départ | au bord de la zone, face à la poubelle, à 1,3 m ou plus | centre de la base à 35 cm du marqueur, dans son axe |
| Rotations dans une mission Vacuum | **aucune** : il avance vers la poubelle pour déposer, puis revient à sa rangée en glissant | deux demi-tours par dépose |
| Le marqueur est dans l'image | pendant presque toute la mission (93 % du temps en simulation) | seulement aux déposes (23 %) |
| Pire écart entre l'odométrie et la réalité, roues qui glissent de 4 % (simulation) | **4 cm** | 38 cm |
| Définir la zone | bouton **Zone from marker** : la caméra lit la distance de la poubelle | la tracer ou la mesurer |
| À la fin | retour à la pose de départ | retour devant la poubelle |

Les rotations sont ce que le robot fait le moins bien : la première disposition les supprime
et garde le repère sous les yeux de la caméra. La seconde reste possible, rien ne change pour
elle.

- [ ] **Les deux stations** : deux cartons, chacun avec une bande de scotch gris sur sa
      face avant. Bande **horizontale** : le linge. Bande **verticale** : les déchets (à
      confirmer, et à changer dans `perception.stations.tape` si c'est l'inverse). La direction
      de la bande dit quel carton c'est ; sa taille dans l'image dit à quelle distance il est
      (`docs/figures/stations_tape.jpg`).
    - Coller les bandes **à plat**, droites, sur du carton nu (du carton au-dessus et
      au-dessous, ou à gauche et à droite : c'est à cela que le robot reconnaît une bande).
    - **Mesurer à la règle** la longueur de chaque bande et l'écrire dans
      `perception.stations.tape` (`horizontal_length_m`, `vertical_length_m`). Les valeurs
      actuelles (41 et 21 cm) sont lues sur une photo.
    - La bande horizontale doit être à peu près à la hauteur de la caméra (7 à 10 cm du sol),
      la verticale doit monter du bas du carton jusqu'au-dessus de cette hauteur.
    - Une bande ne dit pas dans quel sens le carton est tourné : le cap n'est pas relu de
      près, seulement corrigé à distance par la direction de la bande. Poser les cartons bien
      face au robot.
    - Pas d'autre scotch gris en vue si possible. Celui collé au sol est écarté par le
      détecteur (vu de biais, il n'a ni la forme ni la hauteur d'une bande sur un carton),
      mais l'enlever reste plus sûr.
    - Avec des marqueurs ArUco imprimés à la place : `perception.stations.kind: aruco`
      (`make markers`, n° 0 pour le linge, n° 1 pour les déchets).
- [ ] **Le robot** : à la pose de départ de la disposition choisie.
- [ ] **Poubelle en face : bouton Zone from marker** (console, onglet Mission), robot à la
      pose de départ. La caméra lit où est le marqueur : la poubelle est placée dans la
      carte, son point d'arrêt 35 cm devant elle, et la zone va de la ligne de départ à ce
      point. La largeur ne se lit pas sur un marqueur : elle reste celle de la configuration
      (`room.width_m`), ou celle d'une zone tracée avant. Le résultat est gardé dans
      `configs/zone.yaml`.
- [ ] **La zone à balayer** : un rectangle imaginaire devant le robot, sans mur. On la
      trace en conduisant le robot (ci-dessous). On peut aussi la mesurer et l'écrire dans
      `configs/local.yaml` : longueur dans l'axe du robot, largeur centrée sur lui,
      `margin_m: 0` s'il n'y a pas de mur.

```yaml
navigation:
  sweep:
    room: {length_m: 2.0, width_m: 1.6, margin_m: 0.0}
```

**Tracer la zone en conduisant le robot**, pour sa largeur ou pour une poubelle derrière.
**Sans tourner** : avancer, glisser de côté, reculer. Les lignes droites sont bonnes (2 cm
d'écart sur 90 cm), les rotations ne le sont pas. Dans la console, onglet Mission :

1. Robot à la pose de départ : devant la poubelle, dos à elle, face à la pièce.
2. Bouton **Trace zone**. La pose de départ devient l'origine.
3. Onglet Drive : conduire le robot le long du bord de la zone, ou seulement jusqu'à ses
   coins, sans tourner. Pour tourner à un coin : boutons **⟲ 90°** et
   **⟳ 90°** de l'onglet Mission (visibles pendant le tracé). Le robot se cale sur le quart
   suivant de son cap de départ (0, 90, 180, 270°), pas seulement 90° de plus : la petite
   dérive de la conduite à la main est rattrapée à chaque coin et la zone sort carrée.
   Attendre une seconde après avoir lâché les commandes, sinon « Another device is driving ».
4. Retour à l'onglet Mission : la carte montre le chemin et la taille de la zone. Bouton
   **Use this zone**.
5. Remettre le robot à la pose de départ avant **Start mission**.

**Bases et déplacements précis** (onglet Mission, sous la carte) :

- **Set base 1 / 2** retient où est le robot, cap compris ; **Go base 1 / 2** l'y ramène sur
  l'odométrie, en ligne droite en tournant en même temps (base omnidirectionnelle), à 1 cm
  et 1,5° près selon l'odométrie. Un reset de l'odométrie (nouveau tracé) invalide les bases.
- **Vérifier l'odométrie** : scotch au sol sous un repère du robot, Set base 1, rouler où l'on
  veut (virages compris), Go base 1, mesurer l'écart entre le repère et le scotch. La console
  affiche ce que l'odométrie croit qu'il reste : la différence avec le mètre est l'erreur.
- **Déplacement précis** : distance en cm, puis ↑ ↓ ← →. Comme Go base et les quarts de tour,
  il est **fermé dans les deux sens** sur l'odométrie : un dépassement est rattrapé (1 cm,
  1,5°). C'est ce qu'il faut pour tracer une zone.
- **L'onglet Measure** de la page de conduite, lui, ne recule jamais, exprès : il mesure.
  Utilisé pour tracer une zone de 1 × 2 m le 15 nov., chaque virage a dépassé de 2,6° en
  moyenne (+10,5° sur la boucle, mêmes écarts en rapide et en moyen), et la boucle a fini à
  22,5 cm devant et 12,5 cm à côté du départ, dont 19 et 9 cm venaient de ces dépassements
  (`data/move_trials.csv`). L'odométrie seule : ~0,6 % sur 6 m. Avec les déplacements fermés,
  la même boucle en simulation, robot qui répond en retard : 1,8 cm et 1,1°.

La zone est le rectangle qui contient tout le chemin parcouru, à partir de la ligne de
départ. Le robot pourra aller jusqu'à ses bords (pas de marge, puisqu'il y est déjà passé).
Elle est gardée dans `configs/zone.yaml` (hors git) et remplace la zone de la configuration
tant que ce fichier existe : elle survit à un redémarrage. **Forget traced zone** la supprime.
Sa taille dépend de l'odométrie pendant le tracé : quelques centimètres près.

- [ ] **Rien d'autre au sol** que les objets à ramasser : le robot n'a aucun capteur
      d'obstacle et ne contourne rien.
- [ ] **La ligne de départ dégagée** : rien à gauche ni à droite du robot, sur la ligne
      où il démarre. C'est la première rangée, et la seule que la caméra n'a pas vue avant d'y
      passer. Les 15 cm devant cette ligne ne sont jamais vus non plus. Avec une marge (zone
      entre des murs), les deux coins de la zone de ce côté-là ne sont pas vus.
- [ ] **La caméra avant calibrée** sur le sol : `make calibrate-ground`
      (`docs/ARCHITECTURE.md`, « Estimer la distance avec une seule caméra »).
- [ ] **Le détecteur réentraîné sur des images de cette salle**, prises par la caméra du
      robot (section 5).
- [ ] **Les poses du bras** `drop_reach` et `drop_open` relevées dans
      `configs/arm_poses.yaml`. Elles sont encore à zéro : sans elles, la dépose envoie le
      bras dans une pose qui n'a aucun sens.
- [ ] **Le modèle** : `manipulation.pick.policy_path` dans `configs/local.yaml`. Avec un seul
      type d'objet, un seul modèle suffit, et une erreur de classement du détecteur ne change
      rien. Avec deux : `manipulation.pick.policies` (un modèle par catégorie).

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

Sans la page : `uv run makai-mission --sweep` pour Vacuum, `--sweep --use scan` pour Scan
(ajouter `--sim` sans robot).

**La console** a quatre onglets :

| Onglet | Contenu |
|---|---|
| Mission | le choix de l'usage (Vacuum & collect, Scan & collect), le tracé de la zone, la carte en direct, ce que fait le robot, les compteurs, les deux caméras, le journal ; Start, Stop |
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
| `room.length_m`, `room.width_m` | 2,0 × 1,6 m | la zone à balayer, devant le robot ; remplacée par la zone tracée (`configs/zone.yaml`) quand il y en a une |
| `room.margin_m` | 0,30 m | le centre du robot reste à cette distance des bords ; 0 sans mur (c'est le cas d'une zone tracée) |
| `room.y_offset_m` | 0 | centre de la zone, à gauche du robot ; 0 = zone centrée sur lui |
| `pattern` | `rows` | le parcours de Vacuum. `rows` : en rangées, sans tourner. `lanes` : l'ancien parcours, où le robot tourne pour suivre des couloirs qui s'enfoncent dans la pièce |
| `pickup_range_m` | 1,0 m | Vacuum : le robot ne quitte son parcours que pour un objet à moins de cette distance ; 0 = pour tout ce qu'il voit |
| `scan_swath_m` | 1,6 m | Scan : largeur de sol regardée depuis un couloir ; plus petit = plus de couloirs |
| `scan_speed` | 0,08 m/s | Scan : vitesse le long des couloirs |
| `scan_pan_deg`, `scan_period_s` | 60°, 10 s | Scan : jusqu'où le cap oscille de chaque côté, et la durée d'un aller-retour du regard |
| `lane_spacing_m` | 0,5 m | écart entre deux rangées ; plus petit = plus sûr de tout voir, plus long |
| `sweep_speed` | 0,15 m/s | vitesse le long des rangées |
| `recheck_after_m` | 0 | retour au marqueur après tant de mètres sans recalage ; 0 = seulement aux déposes |
| `stations` | poubelle en (−0,35 ; 0) | où est chaque station, et où le robot s'arrête devant ; remplacé par ce que lit **Zone from marker** |
| `marker_fix_range_m` | 2,5 m | au-delà, le marqueur n'est pas utilisé pour corriger l'odométrie |
| `marker_fix_gain` | 0,15 | part de l'écart corrigée à chaque image ; 0 = la caméra ne corrige plus en continu |
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

En simulation, avec la machine à états et la navigation réelles (`make sim`, et les 26 tests
de `tests/test_sweep.py`).

Les deux usages, dans les mêmes conditions :

| Situation simulée | Vacuum & collect | Scan & collect |
|---|---|---|
| Pièce de 2,4 × 1,8 m, 4 objets, 2 stations | 4 sur 4 en 3 min 11 ; quitte son parcours pour des objets à 0,7 à 1,0 m | 4 sur 4 en 4 min 16 ; va chercher des objets à 1,1 à 1,5 m |
| Même pièce, roues qui glissent de 4 %, cap qui dérive de 1,7° par mètre | 4 sur 4, retour à 4 cm de l'origine | 4 sur 4, retour à 1 cm |
| Zone tracée de 2,0 × 1,6 m, vide | parcours de 7,9 m, zone parcourue en 59 s, sol vu à 92 % | parcours de 1,7 m, zone parcourue en 26 s, sol vu à 96 % |

Scan parcourt une zone vide deux fois plus vite. Avec des objets il est plus lent : il
avance moins vite et regarde de nouveau à gauche et à droite chaque fois qu'il revient.

Poubelle en face contre poubelle derrière, même zone de 2,0 × 1,6 m, 4 objets, Vacuum :

| Situation simulée | Poubelle en face | Poubelle derrière |
|---|---|---|
| Roues parfaites | 4 sur 4 en 2 min 49, **0° de rotation** sur toute la mission | 4 sur 4 |
| Roues qui glissent de 4 %, cap qui dérive de 1,7° par mètre | 4 sur 4 en 2 min 55 ; odométrie à 4 cm de la réalité au pire ; 41° de petites corrections de cap | 4 sur 4 en 3 min 27 ; 38 cm au pire ; 2 160° de rotation |
| Dérive doublée | 4 sur 4 ; 9 cm au pire | 3 sur 4 ; 76 cm au pire |
| Zone vide, même dérive, caméra coupée (`marker_fix_gain: 0`) | 27 cm au pire, au lieu de 4 cm avec la caméra | — |

Vacuum, en rangées, poubelle derrière :

| Situation simulée | Résultat |
|---|---|
| Pièce de 2,4 × 1,8 m, 4 objets, 2 stations | 4 déposés dans la bonne station, retour à 2 cm de l'origine (3 min 47 avec l'ancien parcours en couloirs, 3 min 19 en rangées sans limite de distance) |
| Même pièce, vide | aucune rotation pendant tout le balayage (l'ancien parcours en demandait 700°) ; le balayage seul voit 91 % du sol : il manque les 15 cm aux pieds du robot et les deux coins près du mur de départ |
| Roues qui glissent de 4 %, cap qui dérive de 1,7° par mètre | 4 sur 4 ; chaque visite au marqueur corrige 4 à 46 cm ; retour à 3 cm de l'origine. Le robot se croit perpendiculaire au mur, mais il est de travers de 12° au pire, juste avant un recalage |
| Même dérive, marqueurs jamais vus | 2 déposés sur 4, puis échec : le robot se croit devant la station alors qu'il en est trop loin pour déposer ; il finit à 50 cm de l'origine |
| Dérive doublée | 4 sur 4, retour à 5 cm |
| Marqueur jamais vu, sans dérive | dépose à l'odométrie, mission terminée |
| Ancien parcours (`pattern: lanes`) | toujours testé : 4 sur 4 |
| Zone tracée, sans marge, décalée de 30 cm vers la gauche | 2 objets sur 2 déposés, l'objet posé hors de la zone est ignoré, sol vu à plus de 90 % |
| Zone tracée dans la console simulée en conduisant le robot | la mission suivante balaie cette zone |
| Objet impossible à saisir | 3 essais, puis le robot recule à 50 cm, tourne de 40° autour de l'objet en le gardant en face et réessaie 3 fois, puis de -40° ; abandonné ensuite, jamais réapproché (`navigation.mission.orbit_deg`) |
| Objet qui ne se laisse prendre que d'un autre côté | 3 essais manqués, le 4ᵉ vient de 40° autour de l'objet (à 8° près) et réussit |
| Objet hors de la zone | ignoré |

Sur des images réelles : la lecture de l'orientation du marqueur (6° près sur des marqueurs
tournés de ±30°), et le choix du modèle selon l'objet.

**Pas vérifié** : tout ce qui touche au vrai robot. En particulier la dérive réelle des
roues, surtout quand la base glisse de côté (Vacuum ne fait que ça) ou avance en tournant
(Scan), le flou des images pendant que le regard balaie, la portée
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
| En Scan, il passe à côté d'objets | regard trop rapide (images floues), ou objets trop loin pour le détecteur | augmenter `scan_period_s`, réduire `scan_speed` ; réduire `scan_swath_m` pour passer plus près |
| En Vacuum, il part chercher un objet trop loin, ou trop tard | `pickup_range_m` | le réduire ou l'augmenter ; rester au-dessus de l'écart entre deux rangées |
| « No station marker in view across the zone » | la bande n'est pas vue, ou le carton est à moins de 0,9 m | robot face aux cartons, à 1,3 m ou plus ; onglet Cameras pour vérifier que la bande est dans l'image, entière, sur du carton nu ; bande froissée ou à l'ombre : la recoller à plat |
| Un carton est pris pour l'autre, ou une distance est fausse | bande de travers, ou longueur mal réglée | bande bien horizontale ou verticale ; mesurer sa longueur et l'écrire dans `perception.stations.tape` |
| La tuile « Drift fixed » ne dit jamais « marker in view » | marqueur trop loin, trop petit ou hors de l'image | rapprocher la poubelle, agrandir le marqueur (`perception.stations.marker_size_m`) |
| Il heurte un bord | zone déclarée trop grande | retracer la zone ; ou réduire `room`, augmenter `margin_m` |
| La zone tracée est fausse | odométrie qui a dérivé pendant le tracé | retracer plus lentement, sans tourner ; ou **Forget traced zone** et écrire les dimensions dans `configs/local.yaml` |
| « Could not start » dans la console | modèle, calibration ou poids introuvable | le message dit lequel |
