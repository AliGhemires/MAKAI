# Collecte de démonstrations

La qualité des données décide du résultat de la policy plus que tout réglage
d'entraînement. Responsable : WS4 pour le protocole, WS1 pour l'exécution.

## Ce qu'on enregistre

**Une seule compétence : saisir un objet au sol depuis la pose de pré-saisie, puis revenir
en pose `home` en le tenant.** La base ne bouge pas pendant l'épisode. Le dépôt n'est pas
enregistré, il est scripté.

Un épisode, de bout en bout :

1. bras en pose `home`, objet à la pose de pré-saisie (à quelques centimètres près) ;
2. descendre, saisir, remonter ;
3. finir en pose `home`, pince fermée sur l'objet, **rester immobile une seconde**, puis
   arrêter l'épisode (`→`). Cette seconde apprend au modèle qu'il a fini.

Durée visée : 8 à 12 secondes. La chaîne de tâche est toujours la même, au caractère près :
`Pick up the object from the floor` (c'est `manipulation.pick.task` dans la config).

## Avant de commencer

- [ ] La porte G2 est passée : caméras fixées et photographiées, pose `home` figée, pose
      de pré-saisie choisie (`docs/SETUP.md`, section 5)
- [ ] La pose `home` de `configs/arm_poses.yaml` n'est plus à zéro partout (valeurs
      provisoires), et dans cette pose la caméra de poignet voit toute la zone de pré-saisie
- [ ] Le leader a un support fixe qui le remet toujours dans la même pose : l'enregistrement
      démarre et s'arrête d'après elle
- [ ] Éclairage et sol identiques à ceux de la démo : on collecte **sur le tapis de démo**.
      C'est le point le plus risqué, la démo étant dans une autre salle
- [ ] Les deux images sont nettes dans Rerun ; la pince et l'objet sont visibles dans la
      caméra de poignet pendant toute la descente
- [ ] La cadence affichée reste proche de 30 Hz (sinon réduire la charge avant de continuer)
- [ ] Test humain : en ne regardant **que** les deux images dans Rerun, l'opérateur réussit
      la saisie. Si ce n'est pas possible, la policy n'y arrivera pas non plus
- [ ] `uv run python scripts/preflight.py` : tout est « ok »
- [ ] L'opérateur a fait 10 saisies d'entraînement non enregistrées
- [ ] 2 ou 3 épisodes d'essai enregistrés puis regardés dans le visualiseur (« Vérifier un
      dataset »), avant la première session de 30

Ce que `scripts/record.py` garantit déjà en mode mains libres, sans y penser : pas de temps
mort au début ni à la fin, faux départs jetés, deux caméras synchronisées, même pose de
départ et même seconde immobile à la fin de chaque épisode.

## Enregistrer

Une seule commande par objet. Elle contrôle le robot, enregistre, puis dépose un zip du
dataset sur le Bureau :

```bash
uv run python scripts/collect.py sock --try     # d'abord : 2 épisodes d'essai, à regarder
uv run python scripts/collect.py sock           # 30 épisodes (relancer pour 30 de plus)
```

Elle enchaîne `scripts/preflight.py` et `scripts/record.py`, qu'on peut aussi lancer seuls :

```bash
uv run python scripts/record.py --name pick_sock_v1 --object sock --episodes 30
```

L'enregistrement est mains libres : il démarre quand le leader quitte sa pose de repos et
sauvegarde l'épisode quand le bras y est revenu et reste immobile une seconde. Le détail et
les touches sont dans `docs/CE_SOIR.md`, section 2 (« Le guide du pilote »). Avec `--manual`,
le pilote décide : `→` démarre l'épisode, `→` le sauvegarde, `←` le jette, `Échap` arrête.

Faire des sessions de 30 épisodes. Relancer la même commande **ajoute** des épisodes au même
dataset : rien n'est écrasé, et un plantage ne fait perdre que l'épisode en cours. Noter chaque
dataset dans `docs/REGISTRY.md` aussitôt.

Avant le robot, répéter sans matériel et contrôler le laptop :

```bash
uv run python scripts/record.py --name repetition --object sock --episodes 2 --dry-run
uv run python scripts/preflight.py
```

Utiliser les **flèches et Échap** pour piloter l'enregistrement, pas les lettres : `r`, `f` et
`q` commandent aussi la base du robot.

## Les règles

1. **Un seul geste, toujours le même.** Même trajectoire d'approche, même façon de fermer
   la pince, même fin. Un opérateur principal pour tout un dataset.
2. **Pas d'hésitation.** Mouvement continu, ni trop lent ni saccadé. Un épisode avec une
   pause, un raté rattrapé ou un choc : `←` et on le refait. On ne garde que les réussites propres.
3. **Varier ce qui variera en démo, et rien d'autre.** Position de l'objet dans la zone de
   pré-saisie (un carré de ±3 à 4 cm), **couverte régulièrement** : centre, coins, milieux de
   bord. Orientation de l'objet, forme du tissu. Pas de
   changement de caméra, de pose `home`, ni de fond.
4. **Placer l'objet avec le robot, pas à la main.** Dès que l'approche autonome marche,
   c'est elle qui amène le robot devant l'objet avant chaque épisode : les erreurs de
   placement des démonstrations sont alors les mêmes qu'en démo.
5. **D'abord un objet, ensuite la variété.** On ne mélange les objets qu'une fois qu'un
   objet marche à 7/10.
6. **Les mains hors du champ.** Remettre l'objet en place pendant la phase de reset, pas
   pendant l'enregistrement.

## Combien

| Version | Contenu | Épisodes | Quand |
|---|---|---|---|
| v1 | Chaussette noire (60) et canette écrasée (60), un dataset par objet | 120 | samedi soir : `docs/CE_SOIR.md` |
| v2 | 20 à 30 épisodes de plus par objet sur les cas ratés, en lumière du jour | 60 | dimanche matin |
| v3 | Corrections DAgger sur les échecs de la v2 | 30 à 50 | dimanche après-midi |

Ordre de grandeur : 25 épisodes prennent 15 à 20 minutes avec le reset.

Choisir des objets **faciles** : légers, moins de 6 cm à la prise, mats, de couleur
contrastée avec le sol. Pour le linge : chaussette roulée, gant, petit carré de tissu. Pour
les déchets : boule de papier, gobelet en carton écrasé, emballage froissé. Une canette
vide debout est plus difficile (elle roule, elle brille) : à garder pour la fin.

## Corriger la policy pendant qu'elle tourne (DAgger)

Quand une première policy existe, le moyen le plus rentable de l'améliorer est de la
laisser faire et de reprendre la main avec le leader au moment où elle se trompe. Seules
les corrections sont enregistrées.

`lerobot-rollout --strategy.type=dagger` le fait (`Espace` met en pause, `Tab` démarre et
arrête la correction). La commande exacte pour LeKiwi est à valider par WS4 ; voir
`docs/TRAINING.md`.

## Vérifier un dataset

- Le regarder dans le visualiseur : https://huggingface.co/spaces/lerobot/visualize_dataset
- Contrôler : nombre d'épisodes, durées homogènes, pas d'image noire ou figée, courbes
  d'action lisses, vitesses de base à zéro.
- Un épisode douteux se supprime avec `lerobot-edit-dataset` (voir `--help`) plutôt que de
  polluer l'entraînement.

## Erreurs classiques

| Erreur | Effet |
|---|---|
| Caméra déplacée entre la collecte et la démo | La policy échoue entièrement |
| Épisodes de longueurs très différentes, pauses au début | Le robot attend ou hésite |
| Garder les épisodes ratés puis rattrapés | La policy apprend à rater |
| Collecter de jour, faire la démo sous projecteurs | Échecs imprévisibles |
| Deux opérateurs aux styles différents | Geste moyen, flou, imprécis |
| Chaîne de tâche qui change d'un dataset à l'autre | Problèmes à la fusion et à l'inférence |
