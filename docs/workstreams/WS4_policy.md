# WS4 · Policy

**Responsable :** _à inscrire_ · **Couloir :** `src/makai/manipulation/`, `docs/DATA_COLLECTION.md`, `docs/TRAINING.md`

## Mission

Obtenir une saisie autonome fiable. C'est le goulot du projet : tu possèdes le protocole
de collecte, la chaîne d'entraînement et l'évaluation.

## Interface

`PickSkill.run(robot, target) -> bool` et `DropSkill.run(robot, category) -> bool`
(`manipulation/skills.py`). Trois implémentations existent : `PolicyPick` (policy LeRobot,
base bloquée), `ScriptedPick` et `ScriptedDrop` (séquences de poses).

## Tâches

### Samedi, avant 18:00 (sans robot)
- [ ] `uv run hf auth login`, organisation Hub commune, `hub.namespace` renseigné
- [ ] **Entraînement à blanc** : 2 000 pas d'ACT sur un dataset public SO-101, par la voie
      choisie (HF Jobs en premier). Vérifier : paiement, envoi sur le Hub, téléchargement
- [ ] Charger ce modèle avec `get_policy_class("act").from_pretrained(...)` sur un Mac,
      mesurer le temps d'une inférence
- [ ] Préparer `docs/REGISTRY.md`

### Samedi 18:00–22:00
- [ ] Avec WS1 : choisir les objets, la pose `home`, la pose de pré-saisie
- [ ] Capturer les poses `pick_*` et tester `ScriptedPick` : c'est le plan B, il doit exister ce soir
- [ ] Capturer et tester le dépôt scripté dans un bac
- [ ] 10 épisodes d'essai, les regarder dans le visualiseur, rejouer un épisode sur le robot (L0)

### Samedi 22:00 → dimanche matin
- [ ] Collecte v1 (60 épisodes, un objet), 2 entraînements lancés pour la nuit
- [ ] Dimanche 08:00 : évaluer les checkpoints (10 essais chacun), remplir le registre
- [ ] Valider `PolicyPick` dans la mission ; valider `lerobot-rollout` avec `lekiwi_client`

### Dimanche
- [ ] Porte G3 à 10:00 : policy à 5/10 ou plus ? Sinon la démo passe en saisie scriptée
- [ ] Collecte v2 multi-objets, entraînement lancé avant 13:00
- [ ] DAgger sur les échecs, entraînement v3 pour la nuit
- [ ] Détection de saisie vide (`gripper_open_above`) : mesurer la valeur de la pince fermée à vide et sur objet
- [ ] Lundi 08:00 : choix du modèle final, chiffres pour le pitch

## Terminé quand

7 saisies sur 10 sur les objets de la démo, objet amené par l'approche autonome, chiffres
dans le registre.

## Pièges connus

- Le code de `PolicyPick` suit l'exemple officiel de LeRobot 0.7.0 mais n'a pas encore
  tourné sur le robot : première exécution bras dégagé, main sur l'arrêt.
- La chaîne de tâche à l'inférence doit être celle de l'enregistrement.
- Mêmes noms de caméras, même résolution, même pose `home` qu'à la collecte.
- Ne jamais juger un modèle sur sa courbe de perte.

## État

_Mis à jour avant chaque point d'équipe : ce qui marche (chiffres), ce qui bloque, besoins._
