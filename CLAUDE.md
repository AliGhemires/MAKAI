# MAKAI — contexte pour Claude

Hackathon Leukerbad Robotics Carnival 2026, Track 1. Équipe de 5, chacun avec son Claude.
**Deadline : lundi 16 novembre 2026, 12:00.** Checkpoint dimanche 15 à 17:00.

Robot mobile LeKiwi + bras SO-101 qui ramasse ce qui traîne au sol, trie linge et déchets,
et les dépose dans la bonne station. Stack : Python 3.12, `uv`, LeRobot 0.7.0, Ultralytics.

## À lire avant d'agir

1. `docs/PLAN.md` : périmètre, calendrier, niveaux L0 à L5, plans de repli.
2. `docs/WORKFLOW.md` : qui possède quoi, règles git.
3. La fiche du workstream de la personne : `docs/workstreams/WS<N>_*.md`.
4. `docs/ARCHITECTURE.md` avant de toucher au code.

Si la personne n'a pas dit quel est son workstream, le lui demander.

## Règles de travail

- **Pas de relecture, pas d'attente.** L'équipe a deux jours : les branches et `main` servent
  à s'organiser. Quand la personne demande un changement, va jusqu'au merge sur `main` dès
  que les tests passent, sans redemander ni attendre une approbation.
- **`main` doit toujours passer `make check` et `make sim`** : c'est la seule règle stricte.
  Lancer `make check` avant tout push. Du code : branche `ws<N>/<sujet>`, PR mergée en squash
  dès que ses tests sont verts. Docs, fiches, config, petits correctifs : directement sur `main`.
- **Reste dans le couloir de la personne.** Dossiers par workstream : tableau de
  `docs/PLAN.md`, section 6. Si la tâche oblige à toucher le code d'un autre couloir, fais-le
  et dis-le à la personne, pour qu'elle prévienne le responsable dans le chat.
- **Fichiers partagés** : `src/makai/contracts.py`, `configs/makai.yaml`,
  `configs/arm_poses.yaml`, `configs/ground_plane.yaml`, `docs/PLAN.md`, ce fichier. Tu peux
  les modifier quand la tâche le demande ; signale-le à la personne, qui l'annonce dans le chat.
- **Jamais dans git** : données, vidéos, poids de modèles, tokens. Ils vont sur le Hub
  Hugging Face. Les valeurs propres à un laptop vont dans `configs/local.yaml` (ignoré).
- **En fin de session**, proposer de mettre à jour la fiche du workstream : tâches
  cochées, section « État » avec des chiffres, pièges rencontrés. Une décision qui engage
  les autres va dans `docs/DECISIONS.md`.
- Docs en français, code, commentaires et messages de commit en anglais.

## Priorités quand il faut trancher

1. Une boucle complète fiable passe avant toute amélioration d'une brique.
2. Ne pas commencer un niveau tant que le précédent n'a pas réussi son test chiffré.
3. Si une porte du calendrier est manquée, passer au plan de repli plutôt qu'insister.
4. Préférer la solution la plus simple qui marche lundi midi. Pas d'abstraction pour plus tard.
5. Après dimanche 22:00 : corrections et réglages uniquement.

## Faits techniques à ne pas réinventer

- Les contrats entre modules sont dans `src/makai/contracts.py`. Chaque contrat a une
  implémentation réelle et une implémentation simulée (`src/makai/sim/`).
- Repère base : `x` avant, `y` gauche, angles anti-horaires, mètres, rad/s. LeRobot parle
  en degrés et deg/s : la conversion est dans `src/makai/robot/lekiwi.py` uniquement.
- La distance aux objets vient d'une homographie du sol (`perception/geometry.py`), pas
  d'un modèle de profondeur.
- LeRobot 0.7.0 a beaucoup changé par rapport aux versions antérieures : **vérifier dans
  le code installé** (`.venv/lib/python3.12/site-packages/lerobot/`) ou avec `--help`
  avant d'écrire une commande ou un import. Points déjà vérifiés : `docs/ARCHITECTURE.md`,
  dernière section. Doc : https://huggingface.co/docs/lerobot
- Inférence et déploiement : `lerobot-rollout` (stratégies `base`, `dagger`...).
  Entraînement cloud : `lerobot-train --job.target=<gpu>`.
- Le host LeKiwi s'arrête après 30 s sans `--host.connection_time_s`.
- Pas de `cv2.imshow` (OpenCV sans interface graphique) : visualiser avec Rerun.

## Ce qui n'a pas encore tourné sur le vrai robot

Écrit et contrôlé contre l'API de LeRobot 0.7.0, mais jamais exécuté sur le matériel :
`src/makai/robot/lekiwi.py`, `PolicyPick` dans `src/makai/manipulation/skills.py`,
`scripts/teleop.py`, `scripts/record.py`, `build_real` dans `src/makai/app.py`. Le détecteur
`OpenVocabDetector` fonctionne sur une image d'exemple, pas encore sur nos objets. Première
exécution prudente : vitesses réduites, bras dégagé. Retirer un élément de cette liste
une fois validé.

## Commandes

```bash
make setup | setup-lite     # installer tout | le cœur seulement
make check                  # lint + tests (ce que fait la CI)
make sim                    # mission complète simulée
make teleop | mission       # sur le robot (host lancé sur la Pi, voir docs/SETUP.md)
make markers | calibrate-ground
uv run python scripts/record.py --name pick_sock_v1 --episodes 25
scripts/train.sh pick_sock_v1 act_pick_v1 --job.target=a10g-large
```
