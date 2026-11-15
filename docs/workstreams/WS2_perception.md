# WS2 · Perception

**Responsable :** _à inscrire_ · **Couloir :** `src/makai/perception/`

## Mission

Transformer l'image de la caméra avant en une liste d'objets au sol (catégorie, position
en mètres) et de stations. La navigation ne voit le monde qu'à travers toi.

## Interface

`CameraPerception.perceive(Observation) -> Scene` (`perception/pipeline.py`). `Scene.targets`
en mètres dans le repère base, `Scene.stations` par catégorie. Ne pas changer ces types
sans le dire dans le chat : les autres modules en dépendent.

Déjà en place et testé : homographie du sol (`geometry.py`), calibration par feuille de
marqueurs (`calibration.py`), stations ArUco (`stations.py`).

### Détection et tri : un détecteur appris (depuis le 14 nov. au soir)

Le détecteur par défaut est `LearnedDetector` (`perception.detector: learned`) : un petit
modèle entraîné sur nos propres images, qui trouve l'objet et donne sa catégorie en une
passe. Poids : `models/detector_v2.pt` (5 Mo, dans git) depuis le 15 nov. ; le v1 reste à côté.

**v1 connaît deux objets : une chaussette noire et une canette écrasée, filmées au téléphone.**

Mesures du 14 nov. (`scripts/eval_frames.py`, « ok » = une seule détection, bonne catégorie) :

| Test | Détecteur appris v1 | Couleur du sol |
|---|---|---|
| 24 images du soir jamais vues à l'entraînement | 23 ok, 0 fausse alerte | — |
| Les 122 images du soir (73 ont servi à l'entraînement) | 117 ok (96 %) | 18 ok (15 %) |
| Test d'éclairage, 12 photos de jour × 18 éclairages (9 photos ont servi à l'entraînement) | 216 sur 216 retrouvés, bonne catégorie | 89 % retrouvés, 77 % bonne catégorie sur 15 éclairages |

Comment il a été obtenu, sans aucune annotation manuelle :
1. le détecteur par la couleur du sol, fiable en plein jour, a étiqueté 9 photos de jour ;
2. un premier modèle entraîné sur ces photos, copiées sous des éclairages et des ombres
   aléatoires, a trouvé l'objet dans 93 images du soir sur 122, sans fausse alerte ;
3. ses boîtes (vérifiées à l'œil sur une cinquantaine d'images) ont étiqueté les images du
   soir, et la v1 a été entraînée sur l'ensemble.

**Réentraîner** (nouvel objet, et surtout images de la caméra du robot) : filmer 20 s autour
de l'objet, extraire les images, puis

```bash
ffmpeg -i video.MOV -vf "fps=3,scale=-2:640" data/test_frames/<nom>/f_%03d.jpg
uv run python scripts/train_detector.py --name v2 --clothing data/test_frames/<chaussette> --trash data/test_frames/<canette>
uv run python scripts/eval_frames.py --clothing ... --trash ...
```

Environ 10 minutes sur un Mac. Mettre ensuite le chemin des poids dans
`perception.learned.weights` et commiter le fichier.

Temps par image, mesuré le 14 nov. sur un Mac M5, image 640×480 :

| Étape | Temps |
|---|---|
| Détecteur appris, GPU du Mac (`mps`) | 10 ms (pire cas 13 ms) |
| Détecteur appris, processeur seul | 32 ms |
| Marqueurs des stations | 6,5 ms |
| Décodage de l'image reçue de la Pi | 1 ms |

Soit environ 18 ms par image sur 33 disponibles à 30 images par seconde. Le premier appel
coûtait 1,3 s : le détecteur s'échauffe maintenant au démarrage. Réduire la taille de l'image
ne fait rien gagner sur le GPU. Sur un laptop sans GPU la boucle descend vers 25 images par
seconde : **le laptop qui pilote la démo doit avoir un GPU**. Non mesuré, faute de robot : le
réseau entre la Pi et le laptop, et la policy du bras.

Limites :
- **entraîné sur des images de téléphone** : à réentraîner avec la caméra du robot dès qu'elle
  est montée, c'est une autre optique et une autre résolution ;
- ne connaît que ces deux objets ; un autre objet sera ignoré ou mal classé ;
- pas encore mesuré sur un sol vide (aucune vidéo de sol vide pour l'instant) ;
- de très loin en vue rasante, la chaussette est encore ratée sur quelques images.

### Repli : détection par la couleur du sol

`perception.detector: floor` (`FloorBlobDetector`, `floor.py`) cherche tout ce qui n'a pas la
couleur de la moquette. Aucun modèle, mais **ne tient pas quand l'éclairage change** (15 %
sur les images du soir). Sert à étiqueter les toutes premières images de jour.

Le détecteur à vocabulaire ouvert reste disponible (`perception.detector: open_vocab`). Il
localise bien l'objet mais lui donne un score trop bas pour le séparer du bruit ; un modèle
plus gros (`yoloe-11l`) n'a pas fait mieux.

Essayer sur des photos (HEIC à convertir en JPG d'abord) :

```bash
uv run python scripts/detect.py --image data/test_images/*.jpg --ignore-top 0.22
```

`--ignore-top` n'est utile que pour des photos au téléphone, où le haut de l'image montre le
décor. Sur le robot, c'est l'homographie qui écarte ce qui est trop loin ou trop grand
(`perception.floor.min_size_m`, `max_size_m`, `perception.max_range_m`).

### Tri linge / reste par l'aspect (utilisé seulement avec le repli `floor`)

`perception.classifier: uniformity` (`UniformityClassifier`, `classify.py`) : un tissu est
uni et mat, un emballage est imprimé et contrasté. Deux mesures sur l'objet découpé (part
de pixels sur un contour, écart de luminosité), aucun modèle, aucun téléchargement.

Mesuré le 14 nov. sur 12 photos au téléphone (7 d'une chaussette noire roulée, 5 d'une
canette écrasée) :

| Taille de l'objet dans l'image | Bien classé |
|---|---|
| 90 px et plus (de près) | 12 sur 12 |
| 45 à 140 px (mi-distance, simulée) | 12 sur 12 |
| 20 à 55 px (loin, simulée) | 10 sur 12 : deux chaussettes prises pour un déchet |

D'où la règle : en dessous de 45 px (`uniformity.min_object_px`), le classifieur ne répond
pas. L'objet est quand même signalé, avec la catégorie par défaut et une confiance de 0, pour
que le robot s'approche ; la mission retient la dernière catégorie donnée avec confiance.

Limites :
- réglé sur **deux objets**. Tout nouvel objet doit être photographié et vérifié ;
- un objet clair et uni (câble blanc, boule de papier lisse, chaussette blanche) sera
  probablement lu comme du linge ; un tissu à motifs comme un déchet ;
- seuils à revérifier avec la caméra du robot (`perception.uniformity` dans la config).

Autres pistes, non retenues pour l'instant :
- classer la zone découpée avec YOLOE : bonne catégorie 6 fois sur 7, scores très bas ;
- `ClipClassifier` (`perception.classifier: clip`) : écrit, **jamais exécuté**. Le
  téléchargement des poids (340 Mo) a échoué sur le WiFi de la salle (fichier corrompu).

### Robustesse à l'éclairage : insuffisante (mesurée le 14 nov.)

`scripts/eval_lighting.py` ré-éclaire artificiellement chaque photo (sombre, clair, lumière
chaude, froide, délavé, bruit) et vérifie que l'objet est retrouvé avec la bonne catégorie.

```bash
uv run python scripts/eval_lighting.py data/test_images/*.jpg
```

Détecteur par la couleur du sol + tri par l'aspect, 12 photos × 15 éclairages :

| | Résultat |
|---|---|
| Objet retrouvé | 161 sur 180 (89 %) |
| Bonne catégorie | 139 sur 180 (77 %) |
| Fausses alertes | 53 |
| Pire cas | lumière chaude : 5 sur 12 retrouvés |

Causes : les seuils de couleur et de luminosité sont fixes ; une ombre profonde passe pour
un objet sombre (faux positif visible sur `IMG_1373` en pleine résolution) ; le tri par
l'aspect dépend de la luminosité absolue.

Ce test est nécessaire mais pas suffisant : le ré-éclairage artificiel est uniforme sur
l'image, pas l'éclairage réel. Des photos prises sous l'éclairage du soir restent le test
qui compte. **Tout nouveau détecteur doit faire mieux que ces chiffres avant d'être adopté.**

## Tâches

### Samedi, avant 18:00
- [x] Tester le détecteur à vocabulaire ouvert sur nos objets : insuffisant (3 sur 7)
- [x] Détection par la couleur du sol, intégrée et testée sur photos (7 sur 7)
- [x] Canette écrasée : trouvée 5 fois sur 5 et classée « déchet »
- [x] Tri linge / reste par l'aspect, intégré (12 sur 12 de près)
- [x] Détecteur appris v1 (chaussette noire, canette écrasée), robuste à l'éclairage du soir
- [ ] Filmer le sol vide et mesurer les fausses alertes (`eval_frames.py --empty`)
- [ ] **Réentraîner avec des images de la caméra du robot** dès qu'elle est montée
- [ ] Suivi dans le temps : n'accepter un objet que s'il est vu sur plusieurs images de suite
- [ ] Vérifier les seuils de couleur sous l'éclairage du soir, et sur sol vide (aucune détection attendue)
- [ ] Petit script de visualisation : image + boîtes + position au sol en mètres (Rerun)

### Samedi 18:00–22:00
- [ ] Avec WS1 : `make markers`, impression, `make calibrate-ground`, erreur sous 5 mm
- [ ] Vérifier à la règle : un objet posé à 30 cm et à 60 cm est-il bien mesuré ?
- [ ] Tester le détecteur sur les images de la caméra du robot ; régler `perception.floor.color` si besoin
- [ ] Stations : portée de détection des marqueurs, taille et hauteur de collage à ajuster
- [ ] Mesure chiffrée : sur 30 images du robot, combien d'objets trouvés, combien de fausses alertes

### Dimanche
- [ ] Si la couleur du sol ne suffit pas (éclairage, objets peu contrastés) : affiner un petit YOLO (voir ci-dessous)
- [ ] Filtrer les fausses détections : le bras, la pince, les bacs, les pieds des gens
- [ ] Classement linge / déchet : matrice de confusion sur nos 6 objets
- [ ] Bonus : objet inconnu classé par un modèle vision-langage

## Plan B : affiner un détecteur sur nos images

1. Enregistrer 200 à 300 images depuis la caméra du robot, objets à des distances variées.
2. Les annoter : pré-annotation automatique avec le modèle à vocabulaire ouvert, puis
   correction à la main (Roboflow ou Label Studio), 2 classes : `clothing`, `trash`.
3. Entraîner un petit modèle Ultralytics (quelques minutes sur GPU).
4. Mettre le chemin des poids dans `perception.model` : le reste du code ne change pas.

Décider dimanche 10:00 au plus tard si on y va.

## Terminé quand

Sur le tapis de démo, les 6 objets sont détectés à plus de 90 % entre 0,3 et 1,5 m, la
catégorie est juste à plus de 90 %, la position est juste à ±2 cm en dessous de 60 cm.

## Pièges connus

- Au premier lancement, le détecteur télécharge ses poids dans le dossier courant :
  `yoloe-11s-seg.pt` (28 Mo) et l'encodeur de texte `mobileclip_blt.ts` (572 Mo, 12 minutes
  sur le WiFi de la salle le 14 nov.). Lancer depuis la racine du dépôt pour qu'ils soient
  retrouvés ensuite (ils sont ignorés par git). Plutôt que de retélécharger, se passer les
  deux fichiers par AirDrop ou clé USB.
- Essai du 14 nov. sur un Mac M5 : chargement et détection fonctionnent, environ 53 ms par
  image (640 px), sur l'image d'exemple d'Ultralytics avec les mots `person` et `bus`. Rien
  n'est encore mesuré sur nos objets ni depuis la caméra du robot : c'est ta première tâche.
- Un objet de la couleur de la moquette (orange, brun) est invisible : choisir des objets contrastés.
- Tout ce qui traîne au sol est une cible (câble, sac, pied) : zone de démo dégagée.
- La caméra avant a un champ étroit et ne voit ni tout près ni les marqueurs en hauteur :
  lire `docs/ARCHITECTURE.md`, section du compromis de la caméra.
- Le point utilisé est le bas de la boîte (contact avec le sol). Une boîte qui inclut
  l'ombre de l'objet fausse la distance.
- `ultralytics` est sous licence AGPL-3.0 : sans importance pour le hackathon, à mentionner
  si on parle de produit.
- `cv2.imshow` n'est pas disponible (OpenCV sans interface graphique) : visualiser avec Rerun.

## État

_Mis à jour avant chaque point d'équipe : ce qui marche (chiffres), ce qui bloque, besoins._

**Dim. 15, 19 h : stations repérées par une bande de scotch gris** (`TapeStationDetector`,
`perception/stations.py`). Deux cartons : bande horizontale (linge), bande verticale (déchets).
- Sur la photo des deux cartons (`tests/samples/bins_tape.jpg`) : les deux bandes trouvées et
  distinguées. Sur des scènes synthétiques vues par la caméra du robot : distance à 6 % près
  de 0,8 à 2,6 m, 3 cm près à 35 cm ; un mur gris, un objet gris au sol, une chaussette noire,
  un carton sans scotch sont ignorés. 10 ms par image.
- Pas essayé sur une image de la caméra du robot. À faire : onglet Drive, « Save image »
  devant les cartons à 0,5, 1 et 2 m, puis bouton « Zone from marker ».
- À mesurer : la longueur de chaque bande (`perception.stations.tape`). La bande horizontale
  de la photo est froissée (3 cm visibles au lieu de 4,8) : la recoller à plat.

**Dim. 15, 7 h : détecteur v2, sur la caméra du robot.** Le v1 (photos de téléphone) ne
transférait pas : sur des images de la caméra du robot jamais vues, il trouvait la canette
dans 4 sur 14 et la chaussette dans 3 sur 12. Le v2 ajoute aux images du v1 celles de nos
épisodes de saisie, annotées toutes seules par différence entre la première image (objet au
sol) et la dernière (objet ramassé), `perception/autolabel.py`.

| Images jamais vues à l'entraînement | v1 | v2 |
|---|---|---|
| Caméra du robot, canette | 4 sur 14 | **14 sur 14** |
| Caméra du robot, chaussette | 3 sur 12 | **10 sur 12** |
| Caméra du robot, sol vide (aucune détection attendue) | 14 sur 14 | 14 sur 14 |

Sur les vidéos de téléphone du soir, le v2 fait 61 sur 64 (canette) et 58 sur 58
(chaussette), mais les trois quarts de ces images ont servi à son entraînement.
**Limite :** les images du robot sont toutes prises de près (objet à la distance de saisie).
Le v2 n'a pas été essayé à la distance du balayage (0,5 à 1,5 m), ni sur un autre sol. Dans
la salle de démo : `docs/NAVIGATION.md`, section 5 (dix minutes).
