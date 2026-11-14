# Journal des décisions

Trois lignes par décision : ce qu'on a décidé, pourquoi, et ce qui la ferait changer.
On ajoute en bas, on ne réécrit pas l'historique.

| # | Date | Décision | Pourquoi | Remise en cause si |
|---|---|---|---|---|
| D1 | sam. 14 | La policy n'apprend que la saisie ; navigation et dépôt sont classiques | Peu de données et peu de temps : problème étroit pour l'apprentissage | La saisie scriptée suffit (alors plus besoin de policy), ou une policy mobile de bout en bout marche mieux |
| D2 | sam. 14 | Pas de ROS : un processus Python, contrats dans `contracts.py` | Vitesse de mise en route, 5 personnes à synchroniser | — |
| D3 | sam. 14 | Distance par homographie du sol, sans profondeur | Objets au sol, caméra fixe : exact et sans modèle | Objets sur des meubles |
| D4 | sam. 14 | ACT comme première policy, LeRobot 0.7.0 figé | Léger, rapide, temps réel sur Mac | Taux de succès insuffisant malgré de bonnes données |
| D5 | sam. 14 | Base immobile pendant la saisie ; vitesses de base forcées à zéro à l'inférence | Simplifie l'apprentissage | Le bras n'atteint pas l'objet sans bouger la base |
| D6 | sam. 14 | Stations repérées par marqueurs ArUco | Fiable, et réaliste pour un produit | — |
| D7 | sam. 14 | Fin de l'approche à l'odométrie quand l'objet sort du champ | La C270 ne voit pas à la fois loin et près | L'erreur d'arrivée dépasse ±2 cm : alignement à la caméra de poignet |
| D8 | sam. 14 | Détection par la couleur du sol (« tout ce qui n'est pas de la moquette ») au lieu du détecteur à vocabulaire ouvert | Mesuré sur 7 photos : 7 sur 7 contre 3 sur 7, sans modèle ni entraînement | Les seuils ne tiennent pas sous l'éclairage du soir ou avec la caméra du robot ; objets peu contrastés |
| D9 | sam. 14 | Tri simplifié : linge (chaussette, tissu) ou « le reste » | Suffisant pour la démo, plus simple à fiabiliser | Méthode de tri à choisir après photos des déchets |
| D10 | sam. 14 | Pas de relecture de code : chacun merge sur `main` dès que `make check` passe | Deux jours de hackathon ; les branches servent à s'organiser, pas à se contrôler | `main` cassé de façon répétée |
| D11 | sam. 14 | Tri linge / reste par l'aspect de l'objet (uni et mat = linge), décidé de près seulement | 12 photos sur 12 de près, sans modèle ; le classifieur CLIP n'a pas pu être téléchargé | Objets de démo que la règle confond (clairs et unis, tissus à motifs) |
| D12 | sam. 14 | Détecteur appris sur nos images (auto-étiquetées, ré-éclairées) à la place de la couleur du sol | Images du soir : 96 % contre 15 % ; 23 sur 24 jamais vues, sans fausse alerte | Ne tient pas avec la caméra du robot malgré un réentraînement |
| D13 | sam. 14 | Objets de la démo : une chaussette noire roulée et une canette écrasée (à confirmer en équipe). Un dataset et un modèle de saisie par objet | Deux objets fixes simplifient la détection et la saisie ; LeRobot 0.7.0 n'entraîne pas sur plusieurs datasets | La canette ne se saisit pas proprement en téléop : chaussette seule |
| D14 | sam. 14 | La démo est dans une autre salle, sans lampe : données du lieu dès que possible, tapis de démo en carton, conditions variées, et un essai « caméra de poignet seule » | Le sol et le décor changent autant que la lumière, pour le détecteur comme pour la saisie | Accès à la salle de démo dès dimanche : on y concentre la collecte |
| D15 | sam. 14 | Réseau robot : hotspot iPhone « Cyrine » ; le point d'accès de la Pi (« makai-kiwi », option A) reste prêt mais pas au démarrage | Le plus simple : tout le monde y est déjà, laptops gardent Internet. Pas d'écart ressenti en téléop. Mesures (`docs/SETUP.md`, Réseau) : iPhone 38 à 143 ms, pics jusqu'à 1,2 s ; option A 6 ms, flux régulier | Le bras saute pendant la collecte ou la démo : passer en option A (procédure dans `docs/SETUP.md`) |
| D16 | sam. 14 | Host du robot : `scripts/lekiwi_host.py` (accélération du bras 50) au lieu du host LeRobot brut | Sur Wi-Fi, les commandes arrivent par paquets et le bras sautait à pleine accélération | Mouvements trop mous pour la saisie : monter `--arm_acceleration` |

À décider samedi et à inscrire ici : montage et inclinaison de la caméra avant, pose
`home`, pose de pré-saisie (`goal_x_m`, `goal_y_m`), liste des objets, bacs, namespace du Hub.
