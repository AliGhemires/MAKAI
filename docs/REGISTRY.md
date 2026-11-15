# Registre des données et des modèles

Tout dataset et tout modèle est inscrit ici dès sa création. Ce tableau décide du modèle
de la démo et fournit les chiffres du pitch. Se pousse directement sur `main`.

## Datasets

| Nom sur le Hub | Date, heure | Objets | Épisodes | Opérateur | Remarques (lumière, incidents) |
|---|---|---|---|---|---|
| `local/makai_pick_sock_v1` (pas sur le Hub : zip, [TransferNow](https://www.transfernow.net/dl/20261115eDTzT6zc)) | dim. 15, 02:00–03:08 | chaussette noire roulée | 60 (22 780 images, 12,7 min, 30 fps) | Amine (laptop Windows, option A) | 2 sessions de 30 ; épisodes de 7,8 à 18,2 s (médiane 13,2 puis 11,6) ; caméras avant et poignet décodées sur chaque épisode ; pose de départ à ±9° ; pince fermée dans chaque épisode ; base immobile ; 0 épisode marqué mauvais. Zip 627 Mo ; le lien TransferNow expire ; **épisode 31 : saisie ratée** (pince vide à la fin, chaussette restée au sol), les 59 autres finissent chaussette en main (dernière image du poignet regardée pour chacun) ; **entraîner sur la copie sans l'épisode 31 : 59 épisodes, 22 408 images** (`lerobot-edit-dataset ... delete_episodes '[31]'`, identique à l'original image par image) ; 13 % d'images répétées bras en mouvement, jamais deux de suite ; chaussette tenue visible devant la caméra avant dans une partie des fins d'épisode |
| `local/makai_pick_can_v1` (pas sur le Hub : zip, [TransferNow](https://www.transfernow.net/dl/20261115PKK03rUq)) | dim. 15, jusqu'à 05:38 | canette écrasée | **68** (22 118 images, 12,3 min, 30 fps), après suppression de 2 ratés | Amine (laptop Windows, option A) | 70 enregistrés ; épisodes 8 et 68 (saisie ratée : pince fermée à vide, canette restée au sol, confirmé sur la dernière image du poignet) **supprimés du dataset** avec `lerobot-edit-dataset ... delete_episodes '[8, 68]'` : rien à exclure à l'entraînement, épisodes renumérotés de 0 à 67. Les 68 finissent canette en main (pince bloquée à 5–8 par la canette, contre 2 à vide). Épisodes de 8,1 à 14,6 s ; caméras décodées sur chaque épisode ; pose de départ à ±13° (épaule, poignet) ; base immobile. Batterie basse pendant la collecte (9,7 V avant, collecte en charge à partir de 10,8 V). Zip 686 Mo ; le lien TransferNow expire ; copie à 70 épisodes gardée sur le laptop (`makai_pick_can_v1_backup`) ; contrôlé avant l'entraînement (dim. 15, 06:00) : les 68 épisodes finissent canette en main (dernière image du poignet regardée pour chacun), 3 images de chaque épisode chargées sans erreur par le chargeur d'entraînement, pose `home` à 5° de celle de la mission, base immobile ; à la première image la canette est vue par au moins une caméra dans chaque épisode |

## Modèles

| Nom sur le Hub | Datasets | Pas | Entraîné sur | Durée | Remarques |
|---|---|---|---|---|---|
| `act_sock_v1` (pas sur le Hub : cluster DTU, `scripts/hpc/fetch_model.sh act_sock_v1`) | `pick_sock_v1` sans l'épisode 31 (59) | 100 000, un point de sauvegarde tous les 5 000 | DTU, V100, lancé dim. 15 à 03:40 | 4 h 50 prévues | Référence : deux caméras, plans de 100 actions. Relecture d'épisodes à 5 000 pas : 5,3° d'écart au pilote. Réussite sur le robot : à mesurer |
| `act_sock_v1_aug` (cluster DTU) | idem | 40 000 (fini) | DTU, V100, 03:43 | 1 h 55 | Luminosité, contraste, saturation, teinte aléatoires. Relecture à 5 000 pas : 6,2°. Erreur d'entraînement finale 0,050 |
| `act_sock_v1_c50` (cluster DTU) | idem | 40 000 (fini) | DTU, V100, 03:49 | 1 h 50 | Plans de 50 actions. Relecture à 5 000 pas : 5,5°. Erreur d'entraînement finale 0,044 |
| `act_sock_v1_wrist` (cluster DTU) | `pick_sock_v1_wrist` (59, caméra de poignet seule) | 40 000 (fini) | DTU, V100, 03:50 | 1 h 06 | Ne dépend pas du décor de la caméra avant. Relecture à 5 000 pas : 6,0°. Erreur d'entraînement finale 0,050 |
| `act_can_v1` (cluster DTU, `scripts/hpc/fetch_model.sh act_can_v1`) | `pick_can_v1` (68) | 100 000, un point de sauvegarde tous les 5 000 | DTU, V100, lancé dim. 15 à 05:55 | 4 h 50 prévues | Référence canette : deux caméras, plans de 100 actions. Réussite sur le robot : à mesurer |
| `act_can_v1_aug` (cluster DTU) | idem | 40 000 | DTU, V100, 05:57 | 2 h prévues | Luminosité, contraste, saturation, teinte aléatoires |

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
