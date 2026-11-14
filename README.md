# MAKAI

**Le robot qui range avant qu'on nettoie.** Une base mobile LeKiwi et un bras SO-101
parcourent la pièce, ramassent ce qui traîne au sol, reconnaissent le linge et les
déchets, et déposent chacun au bon endroit.

Leukerbad Robotics Carnival Hack 2026 · Track 1 « Autonomous Urban Services » ·
deadline **lundi 16 novembre, 12:00**.

## Démarrer

```bash
git clone https://github.com/AliGhemires/MAKAI.git && cd MAKAI
make setup      # ou `make setup-lite` : le cœur seulement, en quelques secondes
make check      # lint + tests
make sim        # toute la mission dans le simulateur, sans robot
```

Puis lire, dans cet ordre : [`docs/PLAN.md`](docs/PLAN.md), [`docs/WORKFLOW.md`](docs/WORKFLOW.md),
et la fiche de ton workstream dans [`docs/workstreams/`](docs/workstreams/).

`make help` liste toutes les commandes.

## L'équipe

| Workstream | Responsable | Fiche |
|---|---|---|
| WS1 Robot et données | _à inscrire_ | [WS1](docs/workstreams/WS1_robot_data.md) |
| WS2 Perception | _à inscrire_ | [WS2](docs/workstreams/WS2_perception.md) |
| WS3 Navigation | _à inscrire_ | [WS3](docs/workstreams/WS3_navigation.md) |
| WS4 Policy | _à inscrire_ | [WS4](docs/workstreams/WS4_policy.md) |
| WS5 Intégration et démo | _à inscrire_ | [WS5](docs/workstreams/WS5_integration_demo.md) |

## Documentation

| Document | Pour quoi |
|---|---|
| [PLAN](docs/PLAN.md) | Ce qu'on construit, niveaux de périmètre, calendrier, risques |
| [CE_SOIR](docs/CE_SOIR.md) | Samedi soir : collecte des démonstrations et entraînement de nuit, pas à pas |
| [WORKFLOW](docs/WORKFLOW.md) | Branches, merges, partage du robot, points d'équipe |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Modules, contrats, repères, machine à états |
| [SETUP](docs/SETUP.md) | Installer, démarrer le robot, calibrer |
| [DATA_COLLECTION](docs/DATA_COLLECTION.md) | Protocole d'enregistrement des démonstrations |
| [TRAINING](docs/TRAINING.md) | Entraîner, évaluer, améliorer la policy |
| [DEMO_PITCH](docs/DEMO_PITCH.md) | Scénario de démo, pitch, questions du jury |
| [DECISIONS](docs/DECISIONS.md) · [REGISTRY](docs/REGISTRY.md) | Décisions prises · datasets, modèles, résultats |

## Le matériel

LeKiwi (base à 3 roues omnidirectionnelles, Raspberry Pi 5 embarquée) · bras SO-101 ·
caméra avant Logitech C270 · caméra de poignet HBVCAM · LeRobot 0.7.0.

## Comment ça marche

```
caméra avant → PERCEPTION → objets et stations en mètres → MISSION (machine à états)
                                                              ├─ NAVIGATION : approche jusqu'à la pose de pré-saisie
                                                              ├─ SAISIE     : policy apprise par imitation (ACT)
                                                              └─ DÉPÔT      : poses scriptées, station repérée par marqueur
```

La navigation amène toujours l'objet au même endroit devant le robot ; la policy n'a donc
qu'un seul geste à apprendre. Le reste est de la géométrie, testée en simulation.

## Arborescence

```
src/makai/
  contracts.py        types et interfaces partagés (prévenir avant de changer)
  robot/              adaptateur LeRobot ↔ LeKiwi                      WS1
  perception/         détecteur, homographie du sol, marqueurs          WS2
  navigation/         approche, odométrie                               WS3
  sim/                simulateur 2D                                     WS3
  manipulation/       saisie (policy ou scriptée), dépôt                WS4
  orchestrator/       machine à états de la mission                     WS5
  app.py              `makai-mission`                                   WS5
scripts/              téléop, enregistrement, entraînement, marqueurs
configs/              makai.yaml (partagé), local.yaml (personnel), poses du bras
tests/                tests unitaires + mission complète simulée
docs/                 plan, organisation, modes d'emploi, fiches par workstream
```
