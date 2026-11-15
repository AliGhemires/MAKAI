# WS3 · Navigation

**Responsable :** _à inscrire_ · **Couloir :** `src/makai/navigation/`, `src/makai/sim/`

## Mission

Amener le robot, à chaque fois, exactement à la pose de pré-saisie devant l'objet, puis
devant la bonne station. La répétabilité de cette arrivée conditionne le succès de la saisie.

## Interface

`ApproachController.step(x_m, y_m) -> (BaseVelocity, arrived)` et `Odometry`. La machine à
états (WS5) les appelle ; tu règles les gains et tolérances dans `configs/makai.yaml` →
`navigation.approach`.

Déjà en place et testé en simulation : approche en deux phases, propagation de la cible à
l'odométrie, dernier mètre sans la voir, retour au point de départ.

## Tâches

### Samedi, avant 18:00 (sans robot)
- [ ] `make sim`, lire `mission.py` et `approach.py`, jouer avec les paramètres
- [ ] Ajouter au simulateur ce qui manque de réaliste : latence, bruit d'odométrie, glissement
- [ ] Petit tracé de trajectoire de la simulation (image ou Rerun) pour voir ce qui se passe

### Samedi 18:00–22:00 (avec le robot)
- [ ] Vérifier signes et unités : avancer de 0,5 m, pivoter de 90°, glisser de 0,2 m ; mesurer
- [ ] Mesurer l'erreur d'odométrie sur 20 cm et sur 1 m (10 essais)
- [ ] Trouver la vitesse minimale à laquelle les roues bougent vraiment (`min_lin`)
- [ ] Première approche réelle sur un objet ; régler gains et tolérances
- [ ] **Test L1 : 10 approches depuis des positions variées, noter l'erreur finale à la règle**

### Dimanche
- [ ] Approche des stations : distance d'arrêt (`station_standoff_m`), alignement
- [ ] Si l'odométrie du dernier mètre est trop imprécise : alignement final avec la caméra de poignet
- [ ] Recherche : au-delà de la rotation sur place, un petit parcours si le tapis est grand
- [ ] Mémoriser la position des stations pour ne pas les rechercher à chaque fois
- [ ] Sécurité : vitesse plafonnée, arrêt si la cible saute de façon incohérente

## Terminé quand

9 approches sur 10 finissent à ±2 cm de la pose de pré-saisie, en moins de 20 secondes
depuis 1,5 m.

## Pièges connus

- Pas d'évitement d'obstacles : la scène de démo est disposée en conséquence.
- Les roues omnidirectionnelles glissent, surtout en translation latérale et sur sol lisse :
  rouler lentement à la fin, et faire les mesures sur le tapis de démo.
- La boucle passe par le WiFi : si elle ralentit, le host coupe la base (0,5 s). Des
  à-coups sont un signe de latence, pas de gains trop faibles.
- Les gains réglés en simulation sont un point de départ, pas une vérité.

## État

**Dim. 15, 8 h. En simulation uniquement, rien sur le robot.** Mode d'emploi complet :
`docs/NAVIGATION.md`.

- Mission qui balaie, quitte sa route pour un objet, le dépose, revient où elle était :
  4 objets sur 4 en simulation, retour à 2 cm de l'origine.
- Dim. 15, 14 h : deux modes. Aspirateur : le robot ne tourne plus, il reste perpendiculaire
  au mur de la poubelle et glisse de côté le long de rangées (`pattern: rows`). Détection :
  inchangé, il va chercher l'objet vu puis revient à sa place. Aucune rotation pendant le
  balayage (700° avant), 3 min 19 au lieu de 3 min 47. Le balayage seul voit 91 % du sol :
  il manque les deux coins près du mur de départ. L'ancien parcours reste : `pattern: lanes`.
- Glissement simulé (4 %, cap 1,7° par mètre) : le recalage sur le marqueur corrige 4 à
  46 cm par visite ; retour à 3 cm de l'origine. Sans voir les marqueurs, la même mission
  échoue après 2 déposes et finit à 50 cm de l'origine.
- Carte de couverture, objets suivis par leur état, objets hors zone ignorés, objet
  abandonné jamais réapproché.
- Console à onglets (`scripts/drive.py`) : mission pilotée depuis la page, arrêt d'urgence
  testé en pleine mission.
- Fait dans la liste ci-dessus : glissement dans le simulateur, tracé de la trajectoire (la
  carte de la console), petit parcours de recherche, position des stations mémorisée.

À faire sur le robot, dans l'ordre : signes et unités (onglet Drive, Measure), calibration du
sol, une approche réelle, une visite au marqueur, puis une mission avec un seul objet.
