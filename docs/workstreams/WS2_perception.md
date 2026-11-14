# WS2 · Perception

**Responsable :** _à inscrire_ · **Couloir :** `src/makai/perception/`

## Mission

Transformer l'image de la caméra avant en une liste d'objets au sol (catégorie, position
en mètres) et de stations. La navigation ne voit le monde qu'à travers toi.

## Interface

`CameraPerception.perceive(Observation) -> Scene` (`perception/pipeline.py`). `Scene.targets`
en mètres dans le repère base, `Scene.stations` par catégorie. Ne pas changer ces types
sans passer par la procédure des contrats.

Déjà en place et testé : homographie du sol (`geometry.py`), calibration par feuille de
marqueurs (`calibration.py`), stations ArUco (`stations.py`). Le détecteur
(`detector.py`) enveloppe un modèle Ultralytics à vocabulaire ouvert ; il est à régler.

## Tâches

### Samedi, avant 18:00
- [ ] `make setup`, tester `OpenVocabDetector` sur la webcam du laptop avec nos vrais objets
- [ ] Régler `perception.prompts` et `confidence` ; noter quels mots marchent
- [ ] Petit script de visualisation : image + boîtes + position au sol en mètres (Rerun)
- [ ] Mesurer le temps d'inférence sur un Mac (objectif : plus de 10 images/s)

### Samedi 18:00–22:00
- [ ] Avec WS1 : `make markers`, impression, `make calibrate-ground`, erreur sous 5 mm
- [ ] Vérifier à la règle : un objet posé à 30 cm et à 60 cm est-il bien mesuré ?
- [ ] Tester le détecteur sur les images de la caméra du robot (vue basse, rasante)
- [ ] Stations : portée de détection des marqueurs, taille et hauteur de collage à ajuster
- [ ] Mesure chiffrée : sur 30 images du robot, combien d'objets trouvés, combien de fausses alertes

### Dimanche
- [ ] Si le rappel est insuffisant : plan B, affiner un petit YOLO (voir ci-dessous)
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

- La caméra avant a un champ étroit et ne voit ni tout près ni les marqueurs en hauteur :
  lire `docs/ARCHITECTURE.md`, section du compromis de la caméra.
- Le point utilisé est le bas de la boîte (contact avec le sol). Une boîte qui inclut
  l'ombre de l'objet fausse la distance.
- `ultralytics` est sous licence AGPL-3.0 : sans importance pour le hackathon, à mentionner
  si on parle de produit.
- `cv2.imshow` n'est pas disponible (OpenCV sans interface graphique) : visualiser avec Rerun.

## État

_Mis à jour avant chaque point d'équipe : ce qui marche (chiffres), ce qui bloque, besoins._
