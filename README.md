# MMA Agenda

Agenda MMA personnel, construit à partir des sources V4.7.

## État réel

- Application non encore publiée et non validée en navigateur.
- Collecte automatique et connexion Supabase non encore installées.
- Les sources initiales contiennent 8 événements, 49 combats et 59 fiches de palmarès. Le nombre de fiches ne représente pas tous les participants des combats.

## Prochaine livraison

- index.html : interface conservée depuis la V4.7.
- app.js : logique et données de secours intégrées.
- mma-data.json : remplacement optionnel, validé avant application.

## Critères avant validation

1. Le calendrier affiche les événements sur novembre et décembre 2026.
2. Le bouton Liste, les filtres et les fiches fonctionnent sur smartphone via HTTPS.
3. Les compteurs sont calculés depuis les données exécutées, pas considérés comme une preuve à partir du HTML statique.
4. Un JSON absent ou invalide ne supprime pas les données intégrées.
5. Aucun secret ni mot de passe n'est enregistré dans ce dépôt public.

## Architecture cible

GitHub Pages pour l'interface, GitHub Actions pour la collecte contrôlée et Supabase pour les données. La découverte automatique ne sera déclarée opérationnelle qu'après des tests réels de découverte et de mise à jour.
