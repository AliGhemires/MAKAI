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

### Détection : par la couleur du sol (depuis le 14 nov.)

Le détecteur par défaut est `FloorBlobDetector` (`floor.py`) : il ne cherche pas l'objet, il
cherche **tout ce qui n'a pas la couleur de la moquette**. Aucun modèle, aucun entraînement.

Mesuré le 14 nov. sur 7 photos au téléphone d'une chaussette noire roulée, vue basse, avec
sacs, câbles et chaussures en arrière-plan :

| Détecteur | Chaussette trouvée |
|---|---|
| Vocabulaire ouvert (YOLOE), seuil 0,15 | 3 sur 7 |
| Couleur du sol | 7 sur 7, une seule boîte par photo |

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

### Tri linge / reste : par l'aspect (depuis le 14 nov.)

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

## Tâches

### Samedi, avant 18:00
- [x] Tester le détecteur à vocabulaire ouvert sur nos objets : insuffisant (3 sur 7)
- [x] Détection par la couleur du sol, intégrée et testée sur photos (7 sur 7)
- [x] Canette écrasée : trouvée 5 fois sur 5 et classée « déchet »
- [x] Tri linge / reste par l'aspect, intégré (12 sur 12 de près)
- [ ] Photographier les autres objets de la démo (boule de papier, gobelet, autre linge) et vérifier le tri
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
