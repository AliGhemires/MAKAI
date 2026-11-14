# Entraînement et évaluation de la policy

Responsable : WS4. Commandes vérifiées sur LeRobot 0.7.0 (`lerobot-train --help`).

## Choix : ACT d'abord

**ACT** est la policy de départ : légère (2 à 6 Go de mémoire GPU), rapide à entraîner,
éprouvée sur les bras SO-100 et SO-101, et elle tourne en temps réel sur un Mac.
SmolVLA ou π0 ne sont à tenter qu'en bonus (niveau L5) : plus longs à entraîner, plus
lents à l'inférence, et leur intérêt principal, les consignes en langage, ne sert pas à
notre tâche unique.

## Où entraîner

| Option | Mise en route | Quand l'utiliser |
|---|---|---|
| **Hugging Face Jobs** | Un argument : `--job.target=a10g-large`. Facturé à la seconde | Par défaut. `hf jobs hardware` liste les GPU et les prix ; vérifier dès samedi que le compte y a accès |
| GPU loué (RunPod, Lambda, Vast) | Louer une RTX 4090, installer `lerobot[training]`, lancer la même commande | Si HF Jobs n'est pas accessible |
| Google Colab | Notebook ACT de la doc LeRobot | Dépannage |
| DTU HPC | `scripts/hpc/train_act.lsf` (modèle à adapter) | Si on a déjà un accès qui marche depuis l'extérieur ; ne pas y passer plus de 30 minutes |
| Mac (MPS) | `POLICY_DEVICE=mps` | Dernier recours : 6 à 14 heures |

Ordres de grandeur donnés par la doc LeRobot pour 50 épisodes (~45 000 images), 5
passages sur les données : 30 à 60 minutes sur RTX 4090, 1 à 2 heures sur A10G ou L4.

**Samedi après-midi, avant d'avoir nos données** : lancer un entraînement à blanc de 2 000
pas sur un dataset public pour valider toute la chaîne (compte, paiement, envoi du modèle
sur le Hub, téléchargement, chargement). On ne veut pas découvrir un problème de compte à minuit.

## Lancer un entraînement

```bash
# <dataset> et <run> sans le préfixe : le namespace Hub vient de la config
scripts/train.sh pick_sock_v1 act_pick_v1 --job.target=a10g-large       # sur HF Jobs
scripts/train.sh pick_sock_v1 act_pick_v1 --policy.device=cuda          # sur une machine avec GPU
```

Le script appelle `lerobot-train` avec nos conventions : policy ACT, checkpoints envoyés
sur le Hub au fur et à mesure, suivi Trackio. Variables : `STEPS` (30 000 par défaut),
`BATCH` (16), `SAVE_FREQ` (5 000).

### Combien de pas

```
images       = épisodes × durée (s) × 30
pas/passage  = images / batch
```

60 épisodes de 12 s font 21 600 images, soit 1 350 pas par passage en batch 16. La doc
LeRobot indique une convergence en 5 à 10 passages ; on entraîne plus long (30 000 pas),
on garde un checkpoint tous les 5 000 pas, et **on choisit le checkpoint sur le robot**,
pas sur la courbe de perte. Une perte plus basse ne veut pas dire un meilleur robot.

Toujours lancer **deux entraînements en parallèle** la nuit (par exemple deux tailles de
données ou deux réglages) : si l'un échoue, on ne perd pas la nuit.

## Évaluer sur le robot

Un checkpoint n'est jugé que par un protocole fixe, toujours le même :

- 10 essais, objet amené par l'approche autonome, positions variées ;
- succès = l'objet est tenu, bras revenu en pose `home` ;
- noter aussi **comment** ça échoue (rate l'objet, le lâche, n'ose pas descendre...).

Pour tester la saisie seule, dans la mission réelle, mettre le checkpoint dans
`configs/makai.yaml` → `manipulation.pick.policy_path` et lancer `make mission` avec un
seul objet. Pour un checkpoint précis d'un dépôt Hub, LeRobot étiquette chaque checkpoint
par son numéro de pas (voir `--policy.pretrained_revision` dans la doc de `lerobot-rollout`).

`lerobot-rollout` est l'outil officiel de déploiement ; avec LeKiwi le type de robot est
`lekiwi_client`. Forme attendue, **à valider à la première utilisation** :

```bash
uv run lerobot-rollout --strategy.type=base \
  --policy.path=<namespace>/makai_act_pick_v1 \
  --robot.type=lekiwi_client --robot.remote_ip=<ip de la Pi> --robot.id=makai_kiwi \
  --task="Pick up the object from the floor" --duration=15 --device=mps
```

Les caméras déclarées côté client doivent correspondre à celles du host ; si les valeurs
par défaut de LeRobot ne conviennent pas, passer `--robot.cameras=...` comme dans `docs/SETUP.md`.

Chaque évaluation va dans `docs/REGISTRY.md` : c'est ce tableau qui décide du modèle de la
démo et qui fournit les chiffres du pitch.

## Améliorer : dans cet ordre

1. **Regarder les échecs** avant de changer quoi que ce soit. La cause est presque
   toujours dans les données ou le montage, rarement dans les hyperparamètres.
2. Le robot hésite ou s'arrête : démonstrations trop lentes ou avec des pauses → en
   refaire de plus franches.
3. Il rate toujours du même côté : pas assez de démonstrations dans cette zone → 15
   épisodes ciblés, ou DAgger.
4. Il marche sur un objet, pas sur les autres : ajouter des épisodes des objets ratés ;
   si la v2 multi-objets est moins bonne que la v1, garder la v1 pour la démo et réduire
   la liste d'objets.
5. Mouvements saccadés : vérifier la cadence réelle de la boucle (30 Hz attendus), puis
   essayer `--interpolation_multiplier` de `lerobot-rollout`.
6. En dernier : plus de pas, autre taille de batch.

**DAgger** (corrections humaines pendant que la policy tourne) :
`lerobot-rollout --strategy.type=dagger --teleop.type=so101_leader ...`, puis réentraîner
sur les données d'origine plus les corrections. Fusion de datasets : `lerobot-edit-dataset --help`.

## Conventions de nommage (Hub)

| Objet | Nom | Exemple |
|---|---|---|
| Dataset | `<namespace>/makai_<tâche>_<objet>_v<N>` | `makai_pick_sock_v1` |
| Corrections | `<namespace>/makai_dagger_<objet>_v<N>` | `makai_dagger_mix_v1` |
| Modèle | `<namespace>/makai_act_<tâche>_v<N>` | `makai_act_pick_v2` |

Un dataset publié ne se modifie plus : toute correction donne une nouvelle version.

## Faire tourner la policy dans la mission

`PolicyPick` (`src/makai/manipulation/skills.py`) charge le modèle une fois, l'exécute
`duration_s` secondes à 30 Hz **en forçant les vitesses de base à zéro**, puis joue la
séquence `after` (retour en pose `home`). Réglages dans `configs/makai.yaml` → `manipulation.pick`.

Sur les Mac, mettre `device: mps`. Vérifier que l'inférence tient les 30 Hz ; sinon baisser
`robot.fps` de la mission à 15 n'est **pas** une solution (la policy a appris à 30 Hz) :
il faut un laptop plus rapide ou l'inférence déportée (`lerobot-policy-server`).
