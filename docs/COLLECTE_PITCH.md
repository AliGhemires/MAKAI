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

### Sans accès à la salle de pitch (dim. 15 au soir)

Les 127 démonstrations de la v1 montrent toutes le même mur blanc et la même moquette. Mesuré
le 15 au soir sur les modèles v1 (images enregistrées, décor ou sol repeint, écart entre les
deux gestes prévus ; repère : 1,3 à 1,5° d'écart au pilote) : un autre décor déplace le geste
de 2,5 à 3,9°, un autre sol jusqu'à 6° pour la canette, et l'entraînement « couleurs
aléatoires » ne protège pas. Quatre fonds ne rendent pas le modèle indifférent à tout décor :
ils réduisent le risque. Montrer ce qui changera demain, **jamais le mur blanc nu** :

| Session | Devant le robot, de 1 à 3 m | Sol sous l'objet | `--note` |
|---|---|---|---|
| 1 | chaises, pieds de chaises et de table | sol actuel | `"salle chaises"` |
| 2 | tissu sombre tendu (rideau, drap, vestes) | sol actuel | `"salle rideau"` |
| 3 | salle ouverte : loin, sacs, personnes debout | revêtement 1 | `"salle loin sol 1"` |
| 4 | chaises et tissu, une partie des lumières éteinte | revêtement 2 | `"salle chaises sol 2"` |

Revêtement : carton, nappe, drap ou tapis d'au moins 1 m × 1 m, à plat, scotché aux coins,
sous l'objet et devant le robot (la caméra de poignet ne doit voir que lui). Deux couleurs
différentes ; si on connaît le sol de la salle de pitch, en prendre un qui lui ressemble.
12 épisodes par session et par objet ; 6 au minimum si le temps manque.

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
4. Entraîner sur `pick_sock_v2` et `pick_can_v2` (anciens et nouveaux épisodes ensemble).
   Par objet, deux essais lancés en même temps sur le cluster (`docs/CE_SOIR.md`) :

   ```bash
   scripts/hpc/push_dataset.sh pick_sock_v2            # depuis le laptop qui a le dataset
   # puis sur le cluster, dans ~/MAKAI :
   scripts/hpc/submit.sh pick_sock_v2 act_sock_v2_ft STEPS=30000 FROM=act_sock_v1   # repart du modèle v1, ~1 h 30
   scripts/hpc/submit.sh pick_sock_v2 act_sock_v2 STEPS=100000                      # depuis zéro, ~4 h 50
   ```

   `FROM=` reprend les poids d'un essai précédent (`scripts/train.sh`). Pareil pour la canette.
5. Juger : `scripts/replay_check.py` (le modèle reste près du pilote), puis sur le robot
   `scripts/try_pick.py`, 10 essais par objet, devant un fond jamais vu. Les modèles v1
   restent ceux de la démo tant qu'un v2 ne fait pas mieux.
