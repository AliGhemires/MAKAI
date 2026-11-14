# Plan directeur MAKAI

> Leukerbad Robotics Carnival Hack 2026 · Track 1 « Autonomous Urban Services » · équipe de 5
> **Deadline : lundi 16 nov. 12:00** · checkpoint dimanche 17:00 · pitch lundi 13:00 (4 min + 2 min de questions)

Ce document est la source de vérité du projet. Il change peu ; l'avancement vit dans
`docs/workstreams/`, les décisions dans `docs/DECISIONS.md`.

## 1. Ce qu'on construit

**Un robot mobile à ~500 CHF qui range avant qu'on nettoie.** Les robots aspirateurs
s'arrêtent devant une chaussette. MAKAI (base LeKiwi + bras SO-101) parcourt la pièce,
repère ce qui traîne au sol, le ramasse, reconnaît si c'est du linge ou un déchet, et le
dépose dans le panier à linge ou dans la poubelle.

Cas d'usage à pitcher : le ménage des chambres d'hôtel et des appartements de vacances de
Leukerbad. Le personnel manque, chaque chambre commence par « ramasser ce qui traîne ». Le
robot fait ce pré-rangement, puis l'aspirateur robot peut passer. Le détail est dans
`docs/DEMO_PITCH.md`.

Le jury note quatre critères. Voici ce qui répond à chacun :

| Critère | Notre réponse |
|---|---|
| Qualité technique | Architecture modulaire testée en simulation, policy apprise sur nos propres données, taux de succès mesurés et affichés |
| Innovation | L'apprentissage par imitation n'apprend que le geste difficile (saisir) ; tout le reste est de la géométrie fiable. Aucun capteur de profondeur |
| Valeur réelle | Matériel open source bon marché, problème concret du housekeeping, extension naturelle des aspirateurs robots |
| Complétude | Boucle entière autonome : chercher, approcher, saisir, trier, déposer, recommencer, et s'arrêter quand la pièce est propre |

## 2. Principes (à relire quand on hésite)

1. **Une boucle complète fiable bat une brique impressionnante.** On ne passe au niveau
   suivant que quand le niveau courant réussit son test chiffré.
2. **La policy apprend le moins possible.** La navigation amène toujours l'objet au même
   endroit devant le robot (pose de pré-saisie). Le dépôt est scripté. Seule la saisie est apprise.
3. **Toujours un plan B qui tourne.** Chaque brique a une version de repli (section 4).
4. **L'intégration existe depuis l'heure zéro.** `make sim` fait tourner toute la mission
   avec le vrai code de navigation et la vraie machine à états. On remplace les briques
   simulées une par une par les vraies.
5. **Les démonstrations passent par le système.** Pendant la collecte, c'est le robot qui
   s'approche tout seul de l'objet ; l'humain ne téléopère que la saisie. Ainsi la policy
   voit à l'entraînement exactement ce qu'elle verra en démo.
6. **Le robot est la ressource rare.** Un seul robot pour cinq : tout ce qui peut se faire
   sans lui (simulation, images enregistrées, entraînement) se fait sans lui.

## 3. Comment ça marche

```
          caméra avant (C270)                                 caméra poignet (HBVCAM)
                 │                                                     │
        ┌────────▼─────────┐   objets et stations en mètres            │
        │   PERCEPTION     │   dans le repère du robot                 │
        │ détecteur + sol  ├──────────────┐                            │
        │ + marqueurs      │              │                            │
        └──────────────────┘     ┌────────▼─────────┐         ┌────────▼────────┐
                                 │     MISSION      │ pick    │  MANIPULATION   │
                                 │ machine à états  ├────────►│ policy ACT      │
                                 │                  │ drop    │ + poses scriptées│
                                 └────────┬─────────┘────────►└────────┬────────┘
                                          │ vitesses base              │ angles bras
                                 ┌────────▼────────────────────────────▼────────┐
                                 │  ROBOT : laptop ⇄ ZMQ/WiFi ⇄ Raspberry Pi 5  │
                                 └──────────────────────────────────────────────┘
```

Cycle : `SEARCH → APPROACH → PICK → FIND_STATION → GO_TO_STATION → DROP → BACK_OFF → SEARCH`,
puis `DONE` quand il n'y a plus rien. Détails, repères et contrats : `docs/ARCHITECTURE.md`.

Trois idées portent le projet :

- **La distance sans capteur de profondeur.** Les objets sont au sol et la caméra est fixée
  au robot : une homographie calibrée une fois convertit un pixel en position au sol, au
  centimètre près à courte distance.
- **Le dernier mètre à l'odométrie.** Tout près du robot, l'objet sort du champ de la caméra
  avant. La mission continue alors sur l'odométrie des roues pour les derniers centimètres.
- **Les stations portent un marqueur ArUco.** C'est fiable et réaliste : un aspirateur
  robot a bien une base de recharge.

## 4. Niveaux de périmètre et plans de repli

| Niveau | Contenu | Test de passage | Échéance cible |
|---|---|---|---|
| **L0** | Téléop complète, 2 caméras, un dataset enregistré et rejoué | rejouer un épisode saisit l'objet | sam. 21:00 |
| **L1** | Détection + approche autonome jusqu'à la pose de pré-saisie | 9/10 arrivées à ±2 cm | dim. 00:00 |
| **L2** | Saisie autonome d'un type d'objet | 7/10 saisies | dim. 12:00 |
| **L3** | Boucle complète : tri + dépôt dans la bonne station, plusieurs objets | 3 objets rangés d'affilée, 3 essais sur 4 | **dim. 17:00 (checkpoint)** |
| **L4** | Robustesse : 6 objets variés, reprises sur échec, tableau de bord | 5 objets sur 6 en moins de 6 min | dim. 23:00 |
| L5 (bonus) | Commande vocale ou texte, classification par VLM d'objets inconnus, SmolVLA | seulement si L4 est tenu | lun. 09:00 au plus tard |

Replis, du préféré au dernier recours :

| Brique | Plan A | Plan B | Plan C |
|---|---|---|---|
| Saisie | Policy ACT | Séquence de poses scriptée (`pick.kind: scripted`) | Rejeu d'un épisode enregistré |
| Détection | YOLOE vocabulaire ouvert | YOLO affiné sur 200 de nos images | Tapis uni + « tout ce qui n'est pas le sol » |
| Classement linge/déchet | Étiquette du détecteur | Appel VLM sur le crop | Couleur ou taille |
| Stations | ArUco + approche visuelle | Stations à position fixe + odométrie | Une seule station, deux bacs côte à côte |
| Entraînement | Hugging Face Jobs | GPU loué (RunPod, Lambda) ou Colab | DTU HPC, ou MPS sur un Mac pendant la nuit |
| Démo | En direct | En direct sur le tapis de démo | Vidéo enregistrée dimanche soir |

## 5. Calendrier

Les heures sont des cibles. Si une porte (🚪) n'est pas franchie à l'heure, on active le
plan B de la brique concernée au lieu d'insister.

### Samedi 14

| Heure | Quoi |
|---|---|
| 15:00–16:00 | **H0.** Chacun clone, `make setup`, `make check`, `make sim`. Répartition des workstreams (section 6). Checklist matériel (section 8). Compte et organisation Hugging Face |
| 16:00–18:00 | WS1 : moteurs, calibration, host sur la Pi, téléop. WS2 : détecteur sur webcam de laptop puis sur images du robot. WS3 : réglage de l'approche en simulation. WS4 : entraînement à blanc sur un dataset public pour valider toute la chaîne GPU. WS5 : visualisation de la mission, CI, trame du pitch |
| **17:00** | Équipe et track verrouillées : vérifier l'inscription |
| 18:00 | 🚪 **G1** : téléop fluide avec les 2 caméras visibles dans Rerun. Point d'équipe |
| 18:00–20:00 | 🚪 **G2 « gel des caméras »** : positions des caméras définitives, photographiées et marquées. Pose `home` du bras figée. Calibration du sol. Premières poses de dépôt |
| 20:00–22:00 | Première approche autonome réelle. 10 épisodes d'essai, rejeu d'un épisode (L0). Point d'équipe à 22:00 |
| 22:00–01:00 | **Collecte v1** : 60 épisodes, un seul type d'objet, protocole de `docs/DATA_COLLECTION.md`. Lancement de 2 entraînements pour la nuit |

### Dimanche 15

| Heure | Quoi |
|---|---|
| 08:00–10:00 | Évaluation de la policy v1 sur le robot (10 essais par checkpoint). Point d'équipe à 09:00 |
| 10:00 | 🚪 **G3** : si la policy v1 fait moins de 5/10, on bascule la démo sur la saisie scriptée et WS4 continue en parallèle |
| 10:00–13:00 | **Collecte v2** : 3 linges + 3 déchets, 25 épisodes chacun, plus corrections DAgger. Intégration de la boucle complète avec la saisie disponible. Point d'équipe à 13:00, entraînement v2 lancé à 13:00 au plus tard |
| 13:00–17:00 | Boucle complète sur le robot, réglages, premiers enregistrements vidéo |
| **17:00** | 🚪 **Checkpoint officiel : montrer une chose qui marche.** On montre L3, ou à défaut L2 |
| 17:00–22:00 | Fiabilisation : séries de 10 cycles, on corrige la cause d'échec la plus fréquente, on recommence. **Vidéo de secours tournée avant 21:00.** Entraînement v3 la nuit si nécessaire |
| **22:00** | 🚪 **Gel des fonctionnalités.** Après cela : uniquement des corrections et des réglages |

### Lundi 16

| Heure | Quoi |
|---|---|
| 08:00–09:30 | Choix du modèle final, répétitions complètes sur le lieu de la démo, vidéo finale |
| 09:30–11:30 | Pitch répété 3 fois chronomètre en main, slides finales, README à jour, tag `demo-final` |
| **12:00** | **Deadline** |
| 13:00 | Pitch de track · 15:00 finale (5 + 3 min) · 16:00 retour du matériel · 17:00 remise des prix |

On dort. Deux nuits blanches donnent un pitch raté lundi : au moins 5 heures par nuit, par
roulement si un entraînement doit être surveillé.

## 6. Qui fait quoi

Un responsable par workstream ; il décide dans son couloir et tient son fichier à jour.
Les noms sont à inscrire dans le tableau de `README.md`.

| WS | Couloir | Dossiers | Fiche |
|---|---|---|---|
| **WS1** Robot et données | Matériel, Pi, calibration, téléop, enregistrement, planning du robot | `src/makai/robot/`, `scripts/` | `docs/workstreams/WS1_robot_data.md` |
| **WS2** Perception | Détection, classement, calibration du sol, marqueurs | `src/makai/perception/` | `docs/workstreams/WS2_perception.md` |
| **WS3** Navigation | Approche, recherche, odométrie, stations | `src/makai/navigation/`, `src/makai/sim/` | `docs/workstreams/WS3_navigation.md` |
| **WS4** Policy | Protocole de collecte, entraînement, évaluation, saisie | `src/makai/manipulation/` | `docs/workstreams/WS4_policy.md` |
| **WS5** Intégration et démo | Machine à états, `main`, visualisation, pitch, vidéo, tenue du planning | `src/makai/orchestrator/`, `src/makai/app.py`, `docs/` | `docs/workstreams/WS5_integration_demo.md` |

L'organisation au quotidien (branches, merges, points d'équipe, partage du robot) est
décrite dans `docs/WORKFLOW.md`.

## 7. Risques

| Risque | Parade |
|---|---|
| Pas de bras leader pour téléopérer | À vérifier à H0. Sans leader : demander un second SO-101 aux organisateurs, sinon téléop clavier ou téléphone (voir la doc LeRobot) et saisie scriptée en plan A |
| WiFi de la salle saturé (100 robots) | Routeur de voyage ou partage de connexion dédié au robot. Jamais le WiFi public pour la liaison laptop–Pi |
| Une caméra bouge après la collecte | Gel G2, vis ou colle, photo de référence, repères au marqueur. Si elle a bougé : on la remet d'après la photo, sinon on recollecte |
| La policy ne marche pas | Porte G3, saisie scriptée, DAgger, plus de données d'un seul objet avant d'en ajouter d'autres |
| Servo qui chauffe ou casse | Pauses, pose `home` reposante, couple limité, repérer dès samedi qui a des servos de rechange |
| Batterie vide en démo | Charger à chaque pause, noter l'autonomie réelle samedi, alimentation secteur pendant le développement |
| Le sol de la salle (reflets, roues qui glissent) | Tapis de démo uni de 2 × 2 m sur lequel on collecte ET on fait la démo |
| Bras trop court pour le rebord des stations | Stations basses (rebord ≤ 15 cm), validé en téléop samedi avant de choisir les bacs |
| Objets trop gros ou trop durs à saisir | Liste d'objets validée en téléop samedi : petits, légers, moins de 6 cm de large à la prise |
| Intégration tardive | Contrats figés (`contracts.py`), simulation, intégration réelle dès samedi soir |
| Upload ou téléchargement lent | Vidéos en 640×480, partage de connexion 4G/5G en secours |
| Perte de travail | Tout est poussé : code sur GitHub, données et modèles sur le Hub, après chaque session |

## 8. Checklist H0 (samedi, avant tout le reste)

- [ ] Inscription de l'équipe et de la track faite (verrouillage à 17:00)
- [ ] **A-t-on un bras leader SO-101 ?** Sinon, voir la section 7 tout de suite
- [ ] La Raspberry Pi 5 démarre, on connaît son IP, SSH fonctionne
- [ ] Réseau dédié robot + laptops en place
- [ ] Batterie du LeKiwi : état de charge, chargeur, autonomie
- [ ] Les deux caméras sont reconnues sur la Pi (`lerobot-find-cameras opencv`)
- [ ] Un compte ou une organisation Hugging Face commune, un token en écriture par personne
- [ ] Moyen de paiement prêt pour le GPU (HF Jobs ou autre), budget décidé
- [ ] Tapis de démo, 2 bacs bas, 6 objets (3 linges, 3 déchets), ruban adhésif, imprimante pour les marqueurs
- [ ] Chacun a fait `make setup && make check && make sim`

## 9. La démo est prête quand

- la mission complète réussit 4 fois sur 5 sur le tapis de démo avec 4 objets ;
- on la lance avec une seule commande depuis un tag git, sur deux laptops différents ;
- une vidéo de secours de 60 à 90 secondes existe, montée, sur deux machines ;
- le pitch tient en 4 minutes et chacun sait répondre aux questions de `docs/DEMO_PITCH.md`.
