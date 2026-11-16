# WS5 · Intégration et démo

**Couloir :** `src/makai/orchestrator/`, `src/makai/app.py`, `docs/`, `.github/`

## Mission

Faire que les quatre briques donnent un robot qui range, et que le jury le voie. Tu
gardes `main` en état de marche, tu tiens le planning, tu portes la démo et le pitch.

## Tâches

### Samedi, avant 18:00
- [ ] Vérifier que les cinq ont `make setup && make check && make sim` au vert
- [ ] Inviter l'équipe sur le dépôt GitHub, vérifier que la CI tourne
- [ ] Remplir le tableau de l'équipe dans `README.md`
- [ ] Lire `mission.py` en entier ; écrire la visualisation de la mission dans Rerun
      (état courant, cible suivie, détections sur l'image)
- [ ] Demander aux organisateurs le format exact de la soumission et du pitch
- [ ] Trame du pitch (`docs/DEMO_PITCH.md`), premières slides

### Samedi soir
- [ ] Point d'équipe 18:00 et 22:00 : comparer au planning, annoncer les plans B
- [ ] Première mission réelle « approche seule » avec WS3, saisie et dépôt encore simulés
- [ ] Journal de mission dans un fichier (événements horodatés) pour analyser les échecs

### Dimanche
- [ ] Brancher les vraies briques une par une dans `build_real` (`app.py`)
- [ ] Boucle complète sur le robot avant 15:00, démonstration au checkpoint de 17:00
- [ ] Séries de 10 cycles : tableau des causes d'échec, on corrige la première, on recommence
- [ ] Tag `demo-ok-N` à chaque version qui marche
- [ ] **Vidéo de secours avant 21:00**
- [ ] Gel des fonctionnalités à 22:00

### Lundi
- [ ] Répétitions, tag `demo-final`, slides, README, soumission avant 12:00

## Terminé quand

Les critères de la section 9 de `docs/PLAN.md` sont remplis.

## Pièges connus

- La mission réelle (`build_real`) n'a jamais tourné : la première exécution se fait à
  vitesse réduite, robot surélevé ou roues dans le vide.
- Les skills sont bloquants : pendant une saisie, la boucle de mission ne tourne pas.
- Ne pas intégrer une nouveauté après 22:00 dimanche, même « petite ».

## État

_Mis à jour avant chaque point d'équipe : ce qui marche (chiffres), ce qui bloque, besoins._
