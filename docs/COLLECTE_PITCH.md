# Collecte sur plusieurs fonds (salle de pitch ou salle actuelle)

But : apprendre aux modèles que le décor change. On ajoute aux datasets d'hier des
épisodes enregistrés robot tourné vers chacun des quatre côtés, puisqu'on ne sait ni dans
quelle salle ni dans quelle direction sera la démo. **Dans la salle de pitch si on y a
accès, sinon dans la salle actuelle** : ce qui compte, c'est que le fond change d'une
session à l'autre. Ajouter des fonds ne fait pas overfitter, c'est le remède : avec un
seul décor, le modèle peut s'appuyer sur lui ; avec plusieurs, il apprend à l'ignorer.

Les datasets d'hier ne sont pas modifiés : chaque objet a une **v2 = v1 + salle de pitch**,
créée par une copie à la première session.

| Objet | Départ | Nouveau dataset | Épisodes au départ |
|---|---|---|---|
| Chaussette | `pick_sock_v1` (60, dont le raté n° 31) | `pick_sock_v2` | 59 (le 31 est retiré à la copie) |
| Canette | `pick_can_v1` (68, ratés déjà retirés) | `pick_can_v2` | 68 |

Objectif : **12 épisodes par direction et par objet**, soit 48 par objet et 96 en tout.
Environ 1 h 15 de collecte, plus le temps de tourner le robot.

## 0. Sur le laptop d'Amine, une fois

```powershell
git pull
uv sync
```

Vérifier que les datasets d'hier sont là (le dossier `local` de LeRobot) :
`%USERPROFILE%\.cache\huggingface\lerobot\local\makai_pick_sock_v1` et `...\makai_pick_can_v1`.

Puis host sur la Pi et réseau comme hier : `docs/ROBOT_NETWORK.md`, `docs/SETUP.md` section 4.
`collect.py` affiche la commande exacte du host si le robot ne répond pas.

## 1. Choisir les quatre directions

Placer le robot à l'endroit probable de la démo. Nommer les quatre directions d'après ce
que voit la caméra avant, par exemple : `public`, `ecran`, `porte`, `fenetre`. On écrit ce
nom dans `--note` : il reste attaché à chaque épisode (`makai_episodes.csv` dans le zip).

Dans la salle actuelle, rendre les quatre fonds aussi différents que possible : déplacer
chaises, sacs, personnes debout derrière le robot entre deux sessions ; une session lumières
allumées, une autre éteintes ou stores ouverts. Le noter dans `--note`
(ex. `"salle porte lumiere eteinte"`). Limite : le sol ne change pas ; si celui de la démo
est différent, quelques sessions sur un tapis ou une nappe proche de ce sol aident.

**On tourne le robot, pas l'objet.** Les caméras sont sur le robot : en le faisant pivoter,
c'est le fond qui change, la zone de saisie reste la même. Pivoter le robot à la main entre
deux sessions, bras en `home`, sans toucher aux caméras.

## 2. Essai dans la salle (2 épisodes jetables)

```powershell
uv run python scripts/collect.py sock --try
```

Regarder les deux caméras dans Rerun : lumière correcte, chaussette visible par le poignet
pendant la descente. Supprimer ensuite le dossier `makai_essai_sock` affiché.

## 3. La chaussette : quatre sessions de 12

Même commande à chaque session, seul `--note` change. À la première, `--from` copie la v1
sans l'épisode 31 ; aux suivantes, il est ignoré et les épisodes s'ajoutent.

```powershell
uv run python scripts/collect.py sock --name pick_sock_v2 --from pick_sock_v1 --drop "[31]" --episodes 12 --note "pitch public"
```

**Contrôle à la première session :** la ligne `pick_sock_v2: copy of makai_pick_sock_v1 with 59 episodes`.
Si le nombre n'est pas 59, s'arrêter et prévenir.

Puis pivoter le robot d'un quart de tour, et relancer avec `--note "pitch ecran"`, puis
`"pitch porte"`, puis `"pitch fenetre"`.

## 4. La canette : pareil, sans `--drop`

```powershell
uv run python scripts/collect.py can --name pick_can_v2 --from pick_can_v1 --episodes 12 --note "pitch public"
```

**Contrôle :** `copy of makai_pick_can_v1 with 68 episodes`. Si c'est 70, c'est la copie
de sauvegarde : supprimer `makai_pick_can_v2` et relancer avec `--drop "[8, 68]"`.

## 5. Les règles du pilote (inchangées)

- **Le même geste qu'hier** : même approche, même fermeture de pince, même fin en `home`
  immobile une seconde. C'est le geste qui doit être constant, pas le décor. Amine pilote
  si possible, comme pour la v1.
- Varier la position de l'objet dans la zone de saisie (±3 à 4 cm : centre, coins, bords)
  et son orientation, régulièrement dans chaque direction.
- Saisie ratée, hésitation, choc : flèche gauche, on refait. Mains hors du champ pendant
  l'enregistrement.
- Flèches et Échap seulement : `r`, `f` et `q` commandent aussi la base.
- Si un raté a été sauvegardé quand même, `record.py` affiche à la fin la commande qui le
  supprime.

## 6. Après la collecte

1. Les zips `makai_pick_sock_v2.zip` et `makai_pick_can_v2.zip` sont sur le Bureau,
   reconstruits à chaque session : n'envoyer que ceux de la dernière.
2. Les envoyer à qui lance l'entraînement (TransferNow, clé USB).
3. Noter les deux datasets dans `docs/REGISTRY.md` : épisodes, directions, heure, lumière.
4. Entraîner sur `pick_sock_v2` et `pick_can_v2` (anciens et nouveaux épisodes ensemble),
   puis tester avec `scripts/try_pick.py` dans chacune des quatre directions.
