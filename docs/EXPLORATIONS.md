# Journal des explorations

Ce qu'on a essayé, ce qu'on a mesuré, ce qu'on en a conclu. Une entrée par question, avec les
chiffres : c'est la matière des slides. Chaque chiffre renvoie à sa source. À compléter au
fil des essais ; les chiffres encore absents sont listés à la fin.

Mettre à jour les courbes et le tableau des essais : `uv run python scripts/hpc/run_logs.py`.
Vérifier un modèle sans robot : `uv run python scripts/replay_check.py --policy <dossier>`.

## 1. Trouver les objets au sol sans annoter une seule image

| Approche | Résultat |
|---|---|
| Détecteur à vocabulaire ouvert (YOLOE) | 3 objets trouvés sur 7 |
| Détection par la couleur du sol | 7 sur 7 en plein jour, mais 18 images sur 122 le soir |
| **Notre détecteur appris** (YOLO11n, annoté automatiquement, images rééclairées) | **117 images sur 122**, 23 sur 24 sur des images du soir jamais vues, aucune fausse alerte, 10 ms par image |

Conclusion : un petit détecteur entraîné sur nos propres images, sans annotation manuelle,
bat les deux approches « sans entraînement ».

**Puis sur la caméra du robot.** Ce détecteur, appris sur des photos de téléphone, ne
transférait pas. Le robot s'est annoté tout seul : dans chaque épisode de saisie, l'objet est
au sol sur la première image et n'y est plus sur la dernière ; la différence des deux donne
la boîte, sans personne pour la dessiner (58 épisodes de canette sur 68 annotés ainsi).

| Images de la caméra du robot, jamais vues | Détecteur v1 (téléphone) | Détecteur v2 (+ caméra du robot) |
|---|---|---|
| Canette | 4 sur 14 | **14 sur 14** |
| Chaussette | 3 sur 12 | **10 sur 12** |
| Sol vide, aucune détection attendue | 14 sur 14 | 14 sur 14 |

Limite : ces images sont prises de près ; le v2 n'a pas été essayé à la distance du balayage
ni sur un autre sol. Source : `docs/workstreams/WS2_perception.md`.

## 2. Où entraîner : le laptop ou le cluster

| Machine | Secondes par pas | 100 000 pas |
|---|---|---|
| Mac M5 | 1,9 | 53 heures |
| Cluster DTU, une carte V100, deux caméras | 0,174 | 4 h 50 |
| Cluster DTU, une carte V100, caméra de poignet seule | 0,099 | 2 h 45 |

Le cluster va onze fois plus vite. Sa file était pleine la nuit de l'entraînement (près de
1 000 jobs en attente) ; nos quatre jobs ont pourtant démarré en 5 à 16 minutes.
Source : journaux des jobs du 15 nov., `docs/TRAINING.md`.

## 3. Le lien radio entre le robot et le laptop

- Les deux caméras pèsent **61 Mbit/s** (640×480, JPEG qualité 90, 30 images par seconde).
- Retard des images : 2 s à 10 m avec des tables sur le trajet, 1 s à 5 m, presque nul de
  près. Une personne sur le trajet suffit à le faire réapparaître.
- Réseau émis par la Pi (lien direct) : 6 ms, contre 38 à 143 ms en passant par un téléphone.

| Qualité JPEG | Poids du flux |
|---|---|
| 90 (réglage de LeRobot) | 61 Mbit/s |
| 75 | 37 Mbit/s |
| 60 | 28 Mbit/s |

Conclusion : laptop à moins de 5 m, lien direct, un seul programme connecté au robot.
Source : `docs/ROBOT_NETWORK.md`.

## 4. Un enregistreur que le pilote comprend

| Problème vu sur le robot | Mesure | Correction |
|---|---|---|
| Messages en rafale, rien ne se sauvegarde | avec un bras simulé en retard de 0,4 s : 0 épisode sauvegardé en 30 s | « de retour au repos » exige d'avoir quitté le repos : 2 épisodes sur 2 |
| Terminal illisible | 101 lignes à l'écran pour deux épisodes | 9 lignes ; l'encodeur vidéo écrit dans un fichier |
| Terminal et Rerun en désaccord | deux textes écrits séparément | un seul statut, affiché aux deux endroits |
| Le pilote ne décide de rien | démarrage et fin automatiques | flèche droite pour armer, départ au premier mouvement, fin au retour au repos |

Leçon : la répétition sans matériel ne reproduisait pas le retard du vrai bras. Le robot
simulé a maintenant ce retard. Source : `docs/CE_SOIR.md`, « Le guide du pilote ».

## 5. Le premier dataset : `pick_sock_v1`

| Mesure | Valeur |
|---|---|
| Épisodes | 60, en deux sessions de 30 (12,7 minutes, 30 images par seconde) |
| Durée d'un épisode | de 7,8 à 18,2 s, médiane 12,6 s |
| Saisies réussies | **59 sur 60** (dernière image du poignet regardée pour chaque épisode) |
| Pose de départ et de fin | jamais à plus de 8° de `home` |
| Images répétées pendant que le bras bouge | 13 %, jamais deux de suite |
| Pince en fin d'épisode | 2,3 à vide, 5,7 en médiane sur la chaussette |

L'épisode raté a été retiré avant l'entraînement (59 épisodes, 22 408 images). Vu aussi : la
chaussette tenue pend devant la caméra avant en fin d'épisode.

**Que voient les caméras au départ ?** Première image de chacun des 59 épisodes :

| À la première image | Épisodes |
|---|---|
| Chaussette visible par les deux caméras | 47 |
| Par la caméra avant seulement | 10 |
| Par la caméra de poignet seulement | 2 |
| Par aucune | 0 |
| Chaussette entière dans l'image | 9 pour la caméra avant, 11 pour le poignet |

La chaussette est donc toujours vue par au moins une caméra, mais presque toujours coupée
par un bord de l'image : la zone de saisie est au bord du champ des deux caméras. La caméra
de poignet la voit en moins d'une seconde dans 95 % des épisodes, en 1,9 s au plus tard.
Conséquence : au départ, le modèle « caméra de poignet seule » ne voit rien une fois sur six,
et un plan de 100 actions l'engage pour 3,3 s. Raccourcir le plan à l'essai
(`--n-action-steps 30`) le fait regarder de nouveau chaque seconde, sans réentraîner.

Images : `figures/sock_v1_first_images_front.jpg`, `figures/sock_v1_first_images_wrist.jpg`
(première image de chaque épisode), `figures/sock_v1_last_images_wrist.jpg` (dernière image
des 60 épisodes d'origine : l'épisode 31 est le seul où la pince est vide).
Source : `docs/REGISTRY.md`.

**Le second dataset, `pick_can_v1`** : 68 épisodes de canette écrasée (12,3 minutes, de 8,1 à
14,6 s), tous réussis après retrait de deux saisies ratées par le pilote. Poses de départ et
de fin à moins de 13° de `home`, base immobile. Image : `figures/can_v1_last_images_wrist.jpg`
(dernière image du poignet des 68 épisodes).

## 6. Quatre entraînements au lieu d'un

Même modèle (ACT), même dataset, une seule différence par essai, pour ne pas tout miser sur
un réglage.

| Essai | Ce qui change | Pourquoi |
|---|---|---|
| `act_sock_v1` | rien : deux caméras, plans de 100 actions, 100 000 pas | la référence |
| `act_sock_v1_aug` | luminosité, contraste, saturation et teinte tirés au hasard | la démo a lieu dans une autre salle, sans notre éclairage |
| `act_sock_v1_c50` | plans de 50 actions | regarder les caméras deux fois plus souvent |
| `act_sock_v1_wrist` | caméra de poignet seule | ne pas dépendre du décor vu par la caméra avant |

![Courbes d'apprentissage des quatre essais](figures/training_curves.png)

Les quatre apprennent au même rythme : l'erreur est divisée par cinq en 10 000 pas, par dix en
40 000. Les chiffres de la figure sont dans `docs/figures/training_curves.csv`.

La canette a ses deux essais (référence et éclairage aléatoire), lancés à 5 h 55 :
`figures/training_curves_can.png`.

**Une piste écartée : un seul modèle pour les deux objets.** L'outil de LeRobot fusionne les
deux datasets en 5 secondes (127 épisodes), mais le résultat ne se charge pas : ses vidéos ne
correspondent plus à ses épisodes (image demandée à 396 s, image trouvée à 1 879 s). Repéré en
chargeant des images avant tout envoi ; le dataset fusionné n'a pas été entraîné. Tant qu'il
n'y a pas de modèle commun, la mission doit choisir le modèle selon l'objet détecté.

## 7. Le modèle fait-il ce que faisait le pilote ?

On rejoue des épisodes enregistrés dans le modèle, avec le code même que le robot exécute,
et on compare ses commandes à celles du pilote (`scripts/replay_check.py`). Mesures à
5 000 pas, sur trois épisodes :

| Essai | Écart moyen aux commandes du pilote | Un bras qui resterait immobile |
|---|---|---|
| Référence | **5,3°** | 35,5° |
| Horizon de 50 | 5,5° | 35,9° |
| Caméra de poignet seule | 6,0° | 35,1° |
| Éclairage aléatoire | 6,2° | 38,9° |

En fin d'entraînement, mêmes épisodes, modèles finaux (dim. 15, 11 h 30) :

| Modèle final | Écart moyen au pilote | Un bras qui resterait immobile |
|---|---|---|
| Chaussette, référence (100 000 pas) | **1,5°** | 35,7° |
| Chaussette, horizon de 50 (40 000 pas) | 2,0° | 35,9° |
| Chaussette, éclairage aléatoire (40 000 pas) | 2,4° | 35,5° |
| Chaussette, caméra de poignet seule (40 000 pas) | 2,4° | 35,1° |
| Canette, référence (100 000 pas) | **1,3°** | 37,6° |
| Canette, éclairage aléatoire (40 000 pas) | 2,5° | 37,8° |
| Le modèle de la chaussette, rejoué sur des canettes | 16,8° | 37,9° |

L'écart est passé de 5,3° à 1,5° entre 5 000 et 100 000 pas. Un modèle ne vaut que pour son
objet : celui de la chaussette, sur des canettes, fait dix fois plus d'écart. Tous tournent à
29 ou 30 commandes par seconde sur le Mac.

Contre-épreuves sur la référence :

| Ce qu'on donne au modèle | Écart | Lecture |
|---|---|---|
| Les vraies images | 5,3° | |
| Des images noires | 33,3° | sans images, il ne bouge presque pas |
| Les images d'un autre épisode | 15,4° | il va là où il voit la chaussette |
| Les deux caméras inversées | 5,3° | aucun effet : ACT ne sait pas quelle caméra est laquelle |

Mêmes contre-épreuves sur le modèle final de la canette (1,3° avec les vraies images) : 32,0°
avec des images noires, 19,4° avec les images d'un autre épisode.

Ce que cela prouve : toute la chaîne d'inférence (caméras, couleurs, ordre des articulations,
normalisation) est celle de l'entraînement, et le modèle se sert des images. Ce que cela ne
prouve pas : la réussite sur le robot. Ces épisodes ont été vus à l'entraînement.

## 8. Notre méthode face aux gagnants de RoboHack 2026

| Point | Eux (insertion d'une cheville, bras fixe) | Nous |
|---|---|---|
| Modèle | ACT, réglages par défaut | ACT, réglages par défaut |
| Démonstrations | 50 pour leur bon modèle, 110 pour l'autre | 59 |
| Caméras | poignet + vue large | poignet + caméra avant du robot |
| Entraînements | 4, sur 4 plateformes | 4, sur un cluster |
| Volume | batch 16 × 60 000 pas | batch 8 × 100 000 pas |
| Réussite sur le robot | 26 % (80 % de prises initiales) | à mesurer |

Leur modèle à 110 démonstrations et batch 128 a fait bien pire, faute d'avoir ajusté le taux
d'apprentissage. Leur code ne contient aucun réglage fin. Leçon : ils ont gagné avec une
réussite d'une fois sur quatre ; une boucle complète et un pitch clair comptent plus.
Sources : github.com/Encrux/robohack26, boesch.dev/posts/robohack.

## 9. Naviguer et cartographier sans capteur de distance

Le robot n'a que deux caméras et ses roues. Il balaie la pièce, quitte sa route
pour un objet, le dépose à la poubelle et revient où il était. Sa carte : l'odométrie, plus
l'empreinte au sol de la caméra avant. Le marqueur de la poubelle est son seul point fixe : à
chaque visite, il y relit sa position et son cap.

Mesures en simulation, avec la machine à états et la navigation réelles, pièce de
2,4 × 1,8 m, 4 objets, 2 stations (`make sim`) :

| Roues simulées | Avec les marqueurs | Marqueurs jamais vus |
|---|---|---|
| Parfaites | 4 déposés sur 4, retour à 2 cm de l'origine, 3 min 19 | — |
| Glissent de 4 %, cap qui dérive de 1,7° par mètre | **4 sur 4**, retour à **3 cm** ; chaque visite corrige 4 à 46 cm | 2 sur 4 puis échec, fin à 50 cm de l'origine |
| Glissent de 8 %, cap qui dérive de 3,4° par mètre | 4 sur 4, retour à 5 cm | pas mesuré |

Ces chiffres sont ceux du parcours en rangées (ci-dessous).

**Deux façons de balayer, comparées dans la même pièce simulée.** La base est holonome : elle
peut glisser de côté. Premier parcours, en couloirs : le robot avance, tourne au bout, revient.
Second, en rangées (le mode aspirateur retenu) : il ne tourne jamais, reste perpendiculaire au
mur de la poubelle et glisse de côté ; la caméra regarde toujours la bande de sol suivante.

| | En couloirs, en tournant | En rangées, sans tourner |
|---|---|---|
| Rotation pendant le balayage (pièce vide) | 700° | **0°** |
| Longueur du parcours | 8,4 m | 7,9 m |
| Mission complète, 4 objets, roues parfaites | 3 min 47 | **3 min 19** |
| Sol vu par le balayage seul | 100 % | 91 % : les deux coins près du mur de départ manquent |
| Avec des roues qui glissent de 4 % | 4 sur 4, retour à 3 cm | 4 sur 4, retour à 3 cm |

Le gain en temps est modeste (12 %). Le gain attendu sur le robot est ailleurs : tourner est
ce qui fausse le plus le cap d'une base à roues omnidirectionnelles. Ce n'est pas mesuré.

Conclusion : sans point fixe, l'odométrie seule ne tient pas une mission ; un marqueur
imprimé sur la poubelle suffit. Limite : aucun obstacle n'est vu, et rien de cela n'a encore
tourné sur le robot. Image : `figures/console_mission.png` (la console pendant une mission
simulée). Source : `docs/NAVIGATION.md`.

## 10. Les deux datasets vérifiés épisode par épisode

Collecte du 15 nov. sur un laptop Windows, robot en lien direct (option A, 30 images/s par
caméra, aucun trou de plus de 53 ms).

| Dataset | Enregistrés | Gardés | Images | Durée d'un épisode | Ratés trouvés |
|---|---|---|---|---|---|
| `pick_sock_v1` | 60 (02:00–03:08, 2 sessions) | 59 | 22 780 | 7,8 à 18,2 s | épisode 31 |
| `pick_can_v1` | 70 (jusqu'à 05:38) | 68 | 22 118 | 8,1 à 14,6 s | épisodes 8 et 68 |

- Comment on trouve un raté sans regarder 130 vidéos : la canette est rigide, la pince qui
  la tient ne se ferme pas (5 à 8,5) ; vide, elle se ferme jusqu'à 2. Confirmé sur la dernière
  image de la caméra de poignet de chaque épisode
  (`docs/figures/can_v1_70_last_images_wrist_with_misses.jpg`).
- Pour la chaussette, molle, la pince se ferme presque autant : seule l'image le montre
  (l'épisode 31 a été trouvé ainsi).
- Les ratés de la canette sont retirés du dataset (`lerobot-edit-dataset ... delete_episodes`),
  celui de la chaussette exclu à l'entraînement.
- Pose de départ identique d'un épisode à l'autre : ±9° (chaussette), ±13° (canette).

Sources : `docs/logs/recordings/` (liste des épisodes, heure, durée), `docs/REGISTRY.md`.

## 11. Calibrer la caméra avant sans imprimante

Pas d'imprimante dans le hackerspace : une feuille A4 posée au sol (bords et contour noir
au feutre, 29,7 × 14 cm) et cinq croix de scotch mesurées au mètre suffisent
(`scripts/camera_from_sheet.py`). La caméra avant est la caméra d'origine du LeKiwi
(« GENERAL WEBCAM »), sans fiche technique : son champ de vision est mesuré, pas lu.

| Mesuré | Valeur |
|---|---|
| Hauteur de l'objectif | 7,5 cm |
| Inclinaison | 3,5° vers le bas |
| Champ de vision horizontal | 42,4° |
| Sol visible | à partir de 27 cm devant le centre de la base |
| Croix de 46 à 97 cm | 1 à 2 cm d'écart en distance, ~3 cm sur le côté (caméra décentrée) |
| Canette posée à 57,5 cm | lue à 57,3 cm par son point de contact au sol |

- Premier calcul faux de 13 % sur toutes les distances : le rectangle supposé de 26 cm faisait
  en réalité 29,7 cm (bords de la feuille). Une erreur d'échelle constante pointe vers la
  taille du rectangle.
- La croix à 131,5 cm est inutilisable : caméra si basse que 1 pixel y vaut plus de 10 cm.
- Le cadre du détecteur descend 13 pixels sous la canette : 6,5 cm d'erreur à 57 cm, mais
  ~1 cm près du bas de l'image, là où se décide l'arrêt.

Figures : `camera_calibration_grid.jpg` (quadrillage de 10 cm tracé avec le modèle),
`camera_calibration_sheet_corners.jpg`, `camera_calibration_can_57cm.jpg`. Mesures :
`docs/logs/camera_calibration_marks.csv`.

## 12. Où s'arrêter devant l'objet : demandé aux démonstrations

Au lieu de mesurer la zone de saisie, on la lit dans les données : première image de la
caméra avant de chaque épisode, passée dans le même détecteur et le même modèle de caméra que
pendant la mission. L'avant de l'objet était à **28,3 cm** (chaussette, médiane) et **27,3 cm**
(canette) du centre de la base, à −0,2 et −2,5 cm sur le côté.

- Cible d'approche : 0,28 / −0,01 m (elle était à 0,22 m : 6 cm trop près).
- Mesurée par la même chaîne que la mission, la cible porte les mêmes biais (cadre du
  détecteur, caméra décentrée) : ils s'annulent.

Source : `docs/REGISTRY.md`, mesures système.

## 13. Le retard des images et l'odométrie fausse (15 nov., en cours)

Premier essai de navigation : la zone tracée en conduisant le robot dessinait un triangle au
lieu d'un rectangle, le cap affiché valait 762° après un tour, et les images arrivaient avec
2,5 s de retard.

- Cause : le host envoie 30 observations par seconde, la console n'en lit que 10 hors mission
  et ~18 pendant (une étape de mission prend 54 ms sur le processeur du laptop). Le surplus
  s'empile dans les tampons réseau : 2,7 Mo en attente sur la Pi.
- Les vitesses des roues arrivent par le même flux : tant que la file grossit, une seconde de
  mouvement est rejouée sur deux ou trois, et l'odométrie compte deux fois les virages.
- Pistes : host à 15 Hz pour la navigation, console qui lit le flux à chaque tour, modèles sur
  la carte graphique du laptop pour repasser sous 33 ms.

Suite : sections 14 à 17. La console lit maintenant le flux à chaque tour (`9a4666b`).

## 14. D'où vient l'erreur de rotation : ce que disent nos propres données

Après la correction du flux, les lignes droites étaient bonnes (2 cm d'écart sur 90 cm) mais
quatre quarts de tour finissaient à 10, 15, 28 ou 32° de leur cible selon l'essai. Analyse
faite sans le robot, sur les journaux et sur nos épisodes de saisie enregistrés.

| Question | Réponse | Comment on le sait |
|---|---|---|
| Un facteur d'échelle suffit-il ? | Non | entre trois essais où seul le facteur change, l'angle réel ne suit pas l'odométrie : pente de 0,36 à 2,5 au lieu de 1, quel que soit le côté mesuré |
| La vitesse lue sur les servos est-elle fine ? | Non : par pas de 50 pas/s | 44 526 images d'épisodes : les roues ne lisent que 0, ±50, ±100, ±150 |
| Une roue immobile lit-elle zéro ? | Pas toujours | au moins une roue lit ±50 pas/s dans 26 à 28 % des images, base à l'arrêt |
| Est-ce cela qui fausse les rotations ? | Non | chaîne de mesure simulée de bout en bout, roues parfaites : 0,4° d'écart sur 360°, 0,9° au pire |
| Y avait-il un vrai défaut logiciel ? | Oui, ailleurs | après chaque saisie, la mission multipliait la vitesse lue à la reprise par toute la durée de la saisie : une roue à 50 pas/s pendant 15 s = 8,8° de cap d'un coup |

Conclusion : la chaîne de mesure dit vrai à 1° près ; l'erreur de 10 à 32° vient du sol, de
la mécanique ou du mètre. Corrigé au passage : l'odométrie compte les pas des codeurs de roues
(exact, sans bruit à l'arrêt) et n'intègre plus à travers une saisie. Outils : un test de
rotation lu à la caméra (`scripts/turn_check.py`) et un enregistreur de chaque déplacement.
Pas encore refait sur le robot. Source : `docs/DEBUG_ODOMETRY.md`, section 10.

## 15. L'odométrie est mauvaise : la caméra décide

Plutôt que de chercher à rendre les rotations justes, on les évite et on regarde.

- Le robot rejoint tout ce qu'il voit en le regardant : un objet est remesuré à chaque image,
  une station est visée dès qu'elle entre dans l'image.
- Dès qu'une station est dans l'image, sa direction corrige le cap du robot et sa distance
  corrige sa position, un peu à chaque image.
- La poubelle passe **en face** du robot, de l'autre côté de la zone. Il la garde alors sous
  les yeux pendant qu'il balaie, et n'a plus un seul demi-tour à faire : il avance pour
  déposer, puis revient à sa rangée en glissant.

Même zone simulée de 2,0 × 1,6 m, 4 objets, roues qui glissent de 4 % et cap qui dérive de
1,7° par mètre :

| | Poubelle derrière le robot | Poubelle en face |
|---|---|---|
| Objets déposés | 4 sur 4 | 4 sur 4 |
| Rotation sur toute la mission | 2 160° | **41°** (0° avec des roues parfaites) |
| Station dans l'image | 23 % du temps | **93 %** |
| Pire écart entre l'odométrie et la réalité | 38 cm | **4 cm** |
| Avec une dérive doublée | 3 sur 4, 76 cm | 4 sur 4, 9 cm |

Un piège trouvé en simulation : corriger la position à partir de la direction du repère,
quand c'est le cap qui a dérivé, aggrave tout (60 cm d'écart à 2 m pour 18° d'erreur). C'est
le cap que la direction doit corriger. Image : `figures/console_bin_ahead.png`. Simulation
seulement. Source : `docs/NAVIGATION.md`, sections 1 et 2.

## 16. Un robot, deux métiers

La même mission, deux usages choisis dans la console avant de démarrer.

| | Vacuum & collect (chambre d'hôtel) | Scan & collect (rue) |
|---|---|---|
| But | passer sur tout le sol | trouver les objets |
| Parcours | rangées serrées, sans jamais tourner | larges couloirs, le regard qui balaie de 60° à gauche et à droite |
| Ce qu'il ramasse | ce qui est sur son passage, à moins de 1 m | tout ce qu'il repère |
| Pièce de 2,4 × 1,8 m, 4 objets | 4 sur 4 en 3 min 11 | 4 sur 4 en 4 min 16 |
| Zone vide de 2,0 × 1,6 m | parcourue en 59 s, sol vu à 92 % | parcourue en 26 s, sol vu à 96 % |

En rangées, le robot ne tourne plus pendant qu'il balaie : 0° de rotation contre 700° avec le
premier parcours en couloirs. Images : `figures/console_mission.png`,
`figures/console_scan.png`. Simulation seulement.

## 17. Des stations sans imprimante : une bande de scotch gris

Pas d'imprimante sur place, donc pas de marqueur ArUco. Nos deux stations sont des cartons
marqués d'une bande de scotch gris : horizontale pour le linge, verticale pour les déchets.

- La direction de la bande dit quel carton c'est ; sa taille dans l'image dit à quelle
  distance il est (sa longueur de loin, sa largeur de près, quand la bande déborde de l'image).
- Une bande est grise, plus sombre que le carton sans être noire, longue et fine, avec du
  carton de chaque côté. La caméra est à 7,5 cm du sol : une bande collée en travers d'un
  carton apparaît près de la ligne d'horizon où que soit le carton.

| Essai | Résultat |
|---|---|
| La photo de nos deux cartons | les deux bandes trouvées et distinguées |
| Scènes synthétiques vues par la caméra du robot, cartons de 0,8 à 2,6 m | distance à 6 % près ; 3 cm près à 35 cm |
| Mur gris, objet gris au sol, chaussette noire, carton sans scotch | ignorés |
| Scotch gris collé au sol, au-delà de 1,8 m | **pris pour un carton** dans la première version ; corrigé : vu de biais, il n'a ni les proportions ni la hauteur d'une bande sur un carton (ignoré de 0,6 à 5 m) |
| Temps de calcul | 10 ms par image |

Jamais essayé sur une image de la caméra du robot. Image : `figures/stations_tape.jpg`.
Source : `docs/workstreams/WS2_perception.md`.

## Ce qui reste à mesurer

- Sur le robot, tout ce que disent les sections 14 à 17 : la rotation réelle lue à la caméra
  (`scripts/turn_check.py`), les bandes de scotch vues par la caméra du robot, la mission avec
  la poubelle en face.

- Le taux de réussite sur le robot : 10 essais par modèle (`scripts/try_pick.py`). Premiers
  essais du 15 nov. (`act_sock_v1`, `act_can_v1`, modèles finaux) : saisies réussies presque
  à chaque fois d'après l'équipe ; score exact non noté.
- Le seuil de la pince qui sépare une saisie réussie d'une saisie vide.
- L'effet de la salle de démo : référence contre caméra de poignet seule, dans cette salle.
- Le détecteur réentraîné sur les images de la caméra du robot.
- La boucle complète : trouver, approcher, saisir, déposer, avec les temps.
