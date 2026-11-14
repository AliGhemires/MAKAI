# Démo et pitch

Responsable : WS5. Lundi 13:00, **4 minutes de pitch et 2 minutes de questions** ; un
gagnant par track. Si on gagne la track : finale à 15:00, 5 minutes + 3.

## Le message en une phrase

> Les robots aspirateurs s'arrêtent devant une chaussette. MAKAI la ramasse, la trie et
> la range, avec 500 francs de matériel open source.

## Le cas d'usage : le housekeeping

Leukerbad vit du tourisme : hôtels, appartements de vacances, cliniques thermales. Le
ménage d'une chambre commence toujours par ramasser ce qui traîne, et le personnel manque.
MAKAI fait ce pré-rangement : linge au panier, déchets à la poubelle, sol dégagé. Ensuite
un aspirateur robot ordinaire peut finir le travail.

C'est le lien avec la track « Autonomous Urban Services » (livraison, nettoyage,
inspection) : un service de nettoyage autonome, dans un bâtiment réel.

Chiffres à préparer avant le pitch (à sourcer, ne rien inventer) : coût du matériel de
notre robot, temps passé au pré-rangement par chambre si on trouve une source, nombre de
lits touristiques à Leukerbad.

## Déroulé du pitch (4:00)

| Temps | Contenu |
|---|---|
| 0:00–0:30 | Le problème, avec une image : l'aspirateur robot bloqué par une chaussette |
| 0:30–1:00 | La solution et le cas d'usage hôtelier |
| 1:00–2:30 | **Démo en direct** : 2 objets, un linge et un déchet, rangés chacun au bon endroit. Écran à côté montrant ce que le robot voit |
| 2:30–3:15 | Comment ça marche : schéma en 3 blocs, l'idée clé (l'IA n'apprend que la saisie), nos chiffres mesurés |
| 3:15–3:45 | Valeur et suite : coût, extension des aspirateurs robots, ce qu'on ferait en 3 mois au labo |
| 3:45–4:00 | Phrase de fin, équipe |

La démo en direct commence avant 1:15 quoi qu'il arrive. Si elle échoue deux fois, on
bascule sur la vidéo sans commenter l'échec.

## Ce que le jury regarde

Notation : qualité technique, innovation, valeur réelle, complétude. Le jury réunit des
profils différents (affiliations d'après les slides d'accueil) ; prévoir un argument pour chacun.

| Profil | Ce qui compte pour lui | Notre argument |
|---|---|---|
| Outils de visualisation robotique (Foxglove) | Observabilité, données | Écran en direct : détections, état de la mission, flux caméras. LeRobot sait publier vers Foxglove (`init_visualization("foxglove")`) : à essayer si le temps le permet |
| Manipulation par IA (Sereact) | Robustesse de la saisie, méthode | Taux de succès mesurés, découpage navigation / saisie, DAgger |
| Accélérateur (The Residency) | Marché, équipe, vitesse d'exécution | Cas d'usage chiffré, ce qui a été fait en 45 heures |
| Fabrication matérielle (coprod, Industrial Makers) | Coût, industrialisation | Matériel open source bon marché, aucun capteur coûteux |
| Recherche (BTU, Latent Engineering) | Rigueur | Ce qui marche, ce qui ne marche pas, mesuré |

## Scénario de démo

Scène : tapis de 2 × 2 m, panier à linge et poubelle dans deux coins avec leur marqueur,
2 à 4 objets posés. Le robot démarre au centre.

1. Une commande : `make mission`.
2. Le robot tourne, repère l'objet le plus proche, s'approche, le saisit.
3. Il cherche la bonne station, y va, dépose.
4. Il recommence, puis s'arrête et annonce que la pièce est propre.

Préparation :

- **Tout fixer la veille** : positions des stations marquées au ruban, objets choisis
  parmi ceux qui réussissent le mieux, batterie pleine, tag git de démo.
- **Répéter 10 fois** dans les conditions réelles (lumière, emplacement) lundi matin.
- **Un seul pilote** au clavier, un présentateur, une personne prête à replacer un objet.
- Annoncer les limites nous-mêmes dans le pitch : pas d'évitement d'obstacles, objets
  petits. Un jury préfère une limite dite à une limite découverte.

## Plans de secours

| Problème | Réaction |
|---|---|
| Le WiFi tombe | Notre propre routeur ; sinon vidéo |
| La saisie rate | Le robot réessaie tout seul (jusqu'à 3 fois) : le dire, c'est une fonctionnalité |
| Le robot ne démarre pas | Vidéo de secours, prête sur deux laptops, lancée en moins de 10 secondes |
| Plus de batterie | Batterie de rechange ou alimentation secteur pendant le pitch |

**La vidéo de secours** (60 à 90 s) est tournée dimanche avant 21:00 : un plan large de la
boucle complète sans coupe, un insert de ce que voit le robot, un titre. Elle sert aussi
de support pour le README.

## Questions probables

- *Pourquoi ne pas tout apprendre de bout en bout ?* Avec quelques dizaines de
  démonstrations, une policy ne généralise pas à toute une pièce. On lui donne un problème
  étroit et on résout le reste par la géométrie.
- *Comment estimez-vous la distance sans caméra de profondeur ?* Objets au sol, caméra
  fixe : une homographie calibrée suffit. Précision mesurée : (à remplir).
- *Et un objet inconnu ?* Le détecteur est à vocabulaire ouvert ; un objet non classé est
  laissé en place. Extension : classification par un modèle vision-langage.
- *Quel taux de succès ?* Donner les chiffres de `docs/REGISTRY.md`, sans arrondir vers le haut.
- *Combien ça coûte ?* (à remplir avec le prix réel du kit.)
- *Et la sécurité autour de personnes ?* Robot léger, lent (0,15 m/s), arrêt automatique
  si la liaison coupe ; pour un produit il faudrait un capteur d'obstacles.
- *La suite ?* Cartographie pour plusieurs pièces, plus d'objets, intégration avec un
  aspirateur robot existant.

## Livrables pour lundi 12:00

- [ ] Slides (5 au maximum) : problème, solution, démo, comment ça marche, suite
- [ ] Vidéo de secours sur deux laptops et en ligne
- [ ] README à jour avec la vidéo, les chiffres et l'architecture
- [ ] Tag `demo-final` poussé
- [ ] Ce que demandent les organisateurs pour la soumission (à vérifier auprès d'eux samedi)
