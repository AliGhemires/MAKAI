# Navigation : balayer la pièce, ramasser, déposer, reprendre

Le robot se comporte comme un aspirateur : il parcourt la pièce en serpentin, s'arrête dès
qu'il voit un objet, le ramasse avec le modèle entraîné pour cet objet, le porte à la poubelle,
puis revient exactement là où il avait quitté sa route et continue.

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
| SWEEP | suit les couloirs du serpentin, caméra vers l'avant | odométrie |
| APPROACH | se place devant l'objet, à la distance de saisie | caméra avant : détecteur, puis projection au sol ; les 45 derniers centimètres à l'odométrie |
| PICK | le modèle de l'objet pilote le bras, jusqu'à 3 essais | caméras avant et de poignet |
| DOCK | retourne au point d'arrêt devant la station | odométrie |
| GO_TO_STATION | finit sur le marqueur de la station | caméra avant : marqueur ArUco |
| DROP, BACK_OFF | dépose, puis recule | poses du bras |
| RESUME | revient où il avait quitté sa route, dans le même sens | odométrie, recalée |
| RETURN_HOME | pièce balayée : revient devant la poubelle | odométrie, puis marqueur |

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
      sur sa face avant, à hauteur de la caméra (`make markers` pour les imprimer). Un panier
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

Sans la page : `uv run makai-mission --sweep` (ajouter `--sim` sans robot).

**La console** a quatre onglets :

| Onglet | Contenu |
|---|---|
| Mission | la carte en direct, l'état, les compteurs, les deux caméras, le journal ; Start, Stop |
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
| `lane_spacing_m` | 0,5 m | écart entre deux couloirs ; plus petit = plus sûr de tout voir, plus long |
| `sweep_speed` | 0,15 m/s | vitesse dans les couloirs |
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

En simulation, avec la machine à états et la navigation réelles (`make sim`, 30 tests) :

| Situation simulée | Résultat |
|---|---|
| Pièce de 2,4 × 1,8 m, 4 objets, 2 stations | 4 déposés dans la bonne station, sol vu à 100 %, retour à 1 cm de l'origine, en 3 min 50 |
| Roues qui glissent de 4 %, cap qui dérive de 1,7° par mètre | 4 sur 4 ; chaque visite au marqueur corrige 14 à 23 cm ; retour à 3 cm de l'origine |
| Même dérive, marqueurs jamais vus | 2 déposés sur 4, puis échec : le robot se croit devant la station alors qu'il en est trop loin pour déposer ; il finit à 90 cm de l'origine |
| Dérive doublée | 4 sur 4, retour à 6 cm |
| Marqueur jamais vu | dépose à l'odométrie, mission terminée |
| Objet impossible à saisir | abandonné après 3 essais, jamais réapproché |
| Objet hors de la zone | ignoré |

Sur des images réelles : la lecture de l'orientation du marqueur (6° près sur des marqueurs
tournés de ±30°), et le choix du modèle selon l'objet.

**Pas vérifié** : tout ce qui touche au vrai robot. En particulier la dérive réelle des
roues, la portée réelle du détecteur pendant le balayage, la visibilité du marqueur à 35 cm,
et la dépose. Le cap final, après le dernier demi-tour fait à l'odométrie, peut être faux de
10 à 20° ; la position, elle, est recalée.

## 7. Si ça se passe mal

| Ce qu'on voit | Cause probable | Quoi faire |
|---|---|---|
| Le robot passe à côté d'un objet | détecteur aveugle sur ce sol, ou objet « hors zone » | réentraîner le détecteur (section 5) ; agrandir `room` |
| Il s'arrête trop loin ou trop près de l'objet | caméra avant mal calibrée sur le sol | `make calibrate-ground`, puis `navigation.approach.goal_x_m` |
| Il tourne sur place devant la station | marqueur hors de l'image | marqueur plus haut ou plus grand ; il finit par déposer à l'odométrie |
| Il dépose à côté | station mal placée dans `stations`, ou dérive sans marqueur | mesurer la position de la station ; `recheck_after_m: 4` |
| Les couloirs partent de travers | dérive du cap | `recheck_after_m: 4` ; réduire `sweep_speed` |
| Il heurte un bord | zone déclarée trop grande | réduire `room`, augmenter `margin_m` |
| « Could not start » dans la console | modèle, calibration ou poids introuvable | le message dit lequel |
