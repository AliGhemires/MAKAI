# Organisation de l'équipe

Cinq personnes, cinq Claude, un seul robot, 45 heures. Ces règles servent à ne pas se
marcher dessus. Elles sont courtes exprès : on les applique toutes.

## 1. Un couloir par personne

Chaque workstream possède ses dossiers (tableau dans `docs/PLAN.md`, section 6). Dans ton
couloir tu décides seul. Hors de ton couloir, préviens le responsable dans le chat ; tu
n'as pas à attendre son accord.

Quelques fichiers servent à tout le monde. Tu peux les modifier, mais **dis-le dans le chat**
au moment où tu le fais, pour que personne ne soit surpris :

| Fichier | Pourquoi c'est sensible |
|---|---|
| `src/makai/contracts.py` | C'est l'interface entre tous les modules |
| `configs/makai.yaml` | Config partagée du robot et de la démo |
| `configs/arm_poses.yaml`, `configs/ground_plane.yaml` | Liés au montage physique du robot |
| `CLAUDE.md`, `docs/PLAN.md` | Lus par tous les Claude |

## 2. Git : simple, et `main` marche toujours

**Pas de relecture de code.** On a deux jours : les branches et `main` servent à s'organiser,
pas à se contrôler. Personne n'a à approuver ce que tu merges.

- **`main` est toujours démontrable** : `make check` et `make sim` passent. C'est la seule
  règle stricte. Si tu casses `main`, le réparer passe avant tout le reste.
- **Tu merges toi-même, tout de suite**, dès que `make check` passe.
- **Avec ou sans branche, selon le changement** :
  - du code : une branche courte `ws<N>/<sujet>` et une PR mergée en *squash* dès que ses
    tests sont verts. La PR ne sert qu'à faire tourner les tests avant d'arriver sur `main` ;
  - un document, une fiche, de la config, un petit correctif : directement sur `main`
    (l'ajout de fichier par le site GitHub convient aussi).
- **Lancer `make check` avant de pousser.** Sous Windows, sans `make` :
  `uv run ruff check .` puis `uv run pytest`.
- **Se resynchroniser** souvent, au moins à chaque point d'équipe : `make sync`
  (`git pull --rebase origin main`).
- **Jamais** de `git push --force` sur `main`, jamais de données, de modèles ni de secrets
  dans git (le `.gitignore` les bloque ; ils vont sur le Hub Hugging Face).

```bash
git switch -c ws3/station-approach     # nouvelle branche depuis main à jour
# ... travail, commits ...
make check                             # lint + tests, comme la CI
git push -u origin ws3/station-approach
gh pr create --fill
gh pr merge --squash                   # dès que les tests de la PR sont verts
```

### Versions qui marchent : les tags

Dès qu'une version fait quelque chose de montrable sur le vrai robot, WS5 la marque :

```bash
git tag -a demo-ok-1 -m "approche + saisie scriptée, 7/10 sur chaussette"
git push origin demo-ok-1
```

La démo se lance **depuis un tag**, jamais depuis le dernier commit. Si une nouveauté casse
tout dimanche soir, on revient au tag précédent en dix secondes.

### Config : partagée ou personnelle

- `configs/makai.yaml` : ce qui est vrai pour le robot et la démo. Commité.
- `configs/local.yaml` : ce qui dépend de ton laptop (port série du leader, namespace Hub).
  Ignoré par git. Modèle : `configs/local.example.yaml`.

## 3. Le robot : une ressource, un planning

Le robot ne peut servir qu'une personne à la fois. WS1 tient le planning.

- **Créneaux de 45 minutes**, annoncés dans le chat : « robot : WS3 jusqu'à 16:45 ».
- Celui qui a le robot est le seul à lancer des commandes dessus. Les autres regardent ou
  travaillent hors robot.
- **Avant de rendre le robot** : bras en pose `home`, base arrêtée, batterie vérifiée, et
  ce qui a été appris écrit dans la fiche du workstream.
- Priorités en cas de conflit : ce qui débloque une porte du planning, puis la collecte de
  données, puis les réglages.

Travailler sans le robot :

| Besoin | Sans robot |
|---|---|
| Machine à états, navigation | `make sim` et les tests |
| Perception | Images et vidéos enregistrées depuis la caméra du robot (WS1 en fournit dès que possible), ou n'importe quelle image de test |
| Policy | Les datasets sont sur le Hub ; l'entraînement tourne dans le cloud |
| Pitch, vidéo, docs | Toujours |

## 4. Points d'équipe

Cinq minutes, debout, à heures fixes : **samedi 18:00 et 22:00 · dimanche 09:00, 13:00,
17:00, 21:00 · lundi 08:00 et 10:30**.

Avant le point, chacun met à jour la section « État » de sa fiche. Au point, chacun dit
trois choses : ce qui marche (avec un chiffre), ce qui bloque, ce dont il a besoin des
autres. WS5 compare au planning et annonce si une porte passe en plan B.

Entre deux points, un blocage de plus de 30 minutes se dit tout de suite dans le chat.

## 5. Les documents

| Fichier | Contenu | Qui écrit |
|---|---|---|
| `docs/PLAN.md` | Stratégie, périmètre, calendrier | WS5 |
| `docs/ARCHITECTURE.md` | Modules, repères, contrats | Celui qui change un contrat |
| `docs/workstreams/WS<N>_*.md` | Tâches et état de chaque couloir | Son responsable |
| `docs/DECISIONS.md` | Décisions et leur raison, 3 lignes chacune | Tout le monde, en ajout |
| `docs/REGISTRY.md` | Datasets, modèles, résultats d'évaluation | WS1 et WS4 |
| `docs/SETUP.md`, `DATA_COLLECTION.md`, `TRAINING.md` | Modes d'emploi | Leur responsable |
| `docs/DEMO_PITCH.md` | Scénario de démo et pitch | WS5 |

## 6. Travailler avec Claude

Chaque Claude lit `CLAUDE.md` au démarrage. Pour que cinq Claude ne se contredisent pas :

- Commence une session par : « lis `docs/PLAN.md` et ma fiche `docs/workstreams/WS<N>_...md` ».
- Dis-lui ton couloir. Il ne doit modifier que tes dossiers, sauf demande explicite.
- Quand tu lui demandes un changement, il va jusqu'au merge sur `main` dès que les tests
  passent, sans te redemander.
- En fin de session, demande-lui de mettre à jour ta fiche (tâches cochées, état, pièges
  rencontrés) et de pousser. C'est ce qui permet aux autres Claude de savoir où tu en es.
- Une décision qui engage les autres va dans `docs/DECISIONS.md`, pas seulement dans ta
  conversation.
- Les commits sont en anglais, courts, au présent : `nav: add station standoff approach`.
