# Registre des données et des modèles

Tout dataset et tout modèle est inscrit ici dès sa création. Ce tableau décide du modèle
de la démo et fournit les chiffres du pitch. Se pousse directement sur `main`.

## Datasets

| Nom sur le Hub | Date, heure | Objets | Épisodes | Opérateur | Remarques (lumière, incidents) |
|---|---|---|---|---|---|
| `local/makai_pick_sock_v1` (pas sur le Hub : zip, [TransferNow](https://www.transfernow.net/dl/20261115eDTzT6zc)) | dim. 15, 02:00–03:08 | chaussette noire roulée | 60 (22 780 images, 12,7 min, 30 fps) | Amine (laptop Windows, option A) | 2 sessions de 30 ; épisodes de 7,8 à 18,2 s (médiane 13,2 puis 11,6) ; caméras avant et poignet décodées sur chaque épisode ; pose de départ à ±9° ; pince fermée dans chaque épisode ; base immobile ; 0 épisode marqué mauvais. Zip 627 Mo ; le lien TransferNow expire |

## Modèles

| Nom sur le Hub | Datasets | Pas | Entraîné sur | Durée | Remarques |
|---|---|---|---|---|---|
| | | | | | |

## Évaluations sur le robot

Protocole fixe : 10 essais, objet amené par l'approche autonome (`docs/TRAINING.md`).

| Date, heure | Modèle, checkpoint | Objet | Succès /10 | Comment ça échoue |
|---|---|---|---|---|
| | | | | |

## Mesures système

| Date, heure | Mesure | Résultat |
|---|---|---|
| | Approche : erreur finale sur 10 essais | |
| | Détection : rappel et fausses alertes sur 30 images | |
| | Mission complète : objets rangés, durée | |
| sam. 14, 21:10 | Entraînement ACT, HPC de DTU (V100 32 Go), batch 8, images de synthèse | 0,21 s par pas, 37 images/s, 3,7 Go de mémoire GPU, file d'attente 12 s |
| sam. 14, 20:10 | Entraînement ACT, Mac M5, batch 8 | 1,9 s par pas (batch 16 : 3,8 s ; précision mixte : plante) |
| sam. 14, 21:20 | Modèle du HPC rapatrié sur le laptop (207 Mo, partage de connexion) | 47 s |
| sam. 14, 19:20 | Exécution de la policy sur un Mac, robot simulé | 27 à 30 commandes par seconde |
| sam. 14, 18:20 | Détecteur appris v1, images du soir jamais vues | 23 sur 24, 0 fausse alerte ; 10 ms par image |
