# La tribu

Un site familial en français pour Alice, Anaëlle et Tiziano. Interface responsive pour ordinateur, iPhone et iPad ; serveur Flask, SQLite et photos privées. Aucun service payant requis pour le fonctionnement courant.

## Démarrage dans cet environnement

```sh
cd /workspace/famillejerichotache-
bash scripts/install.sh
bash scripts/start.sh
```

L’installation crée `/workspace/family-venv`, installe les versions figées et lance les tests. Le démarrage utilise Gunicorn sur le port 5000, en accès local par défaut. `HOST` et `PORT` peuvent adapter l’écoute à l’hébergement. Chaque tâche cloud est déjà isolée : utiliser le checkout existant, sans créer de worktree.

Pour un développement hors de ce cloud : créer un environnement virtuel, installer `requirements.txt`, puis lancer `python app.py` depuis le dépôt. Ne pas utiliser le serveur de développement Flask comme serveur public.

## Ce qui fonctionne

- Sélection des trois profils enfants et connexion au profil temporaire « Parent test » avec le code convenu. Un code individuel enfant peut être défini par un parent, notamment pour une tablette partagée.
- Planning par semaine, navigation entre les semaines et sélection de chaque jour.
- Lit et chambre obligatoires tous les jours. Base hebdomadaire : Alice 5 CHF, Anaëlle 5 CHF, Tiziano 25 CHF. Les 14 validations parentales sont nécessaires pour débloquer le montant de base.
- Missions bonus facultatives : table matin/soir, table du midi le week-end par défaut, lave-vaisselle à vider et à remplir chaque jour, linge selon les besoins. Les parents peuvent ajouter des missions communes ou individuelles, récurrentes ou ponctuelles, et archiver les bonus.
- Une mission bonus commune ne peut être réclamée que par un seul enfant par jour. Les enfants voient les missions déjà prises. Les tâches obligatoires restent individuelles.
- Photo obligatoire pour envoyer une tâche, commentaire facultatif, validation ou retour avec conseil. Les photos JPEG/PNG/WebP sont décodées, réorientées, réduites et réencodées sans métadonnées EXIF. Une tâche validée ne rapporte pas de points une deuxième fois.
- Défis familiaux avec description, échéance, points, participation et validation parentale. Les points d’un défi comptent dans la semaine de son échéance.
- Notifications gratuites dans le site, créées lors des actions réelles et actualisées toutes les 20 secondes lorsque le site est visible. Boîte privée par profil et état lu/non lu.
- Coffre hebdomadaire, progression des 7 jours et badges de la semaine calculés sur les validations réelles.
- Montants de base et conversion bonus réglables par les parents. Par défaut, les points bonus sont comptés mais leur conversion monétaire n’est pas définie (valeur 0). Tous les montants sont stockés en centimes.
- Enregistrement d’un versement après les validations. Le montant versé est conservé et la semaine est clôturée pour les nouveaux envois. Il faut traiter les tâches et participations en attente avant de verser. Le site ne transfère pas d’argent.

## Données et accès

`data/` (ignoré par Git) contient la base SQLite, les photos dans cette base et la clé des sessions. Ne pas perdre cette clé lors d’un redémarrage. Sauvegarder ce dossier de manière privée ; arrêter le serveur avant une copie simple ou utiliser l’API de sauvegarde SQLite pour une sauvegarde à chaud.

Le dossier est privé (0700), la base et la clé sont privées (0600). Les API exigent une session, les écritures un jeton CSRF. Les photos sont servies seulement au parent et à l’enfant concerné. Les mauvaises tentatives de connexion sont limitées à 5 par adresse IP sur 5 minutes. Le compte enfant ouvert sans code est uniquement destiné aux essais en développement.

Le catalogue `config/tasks.json` initialise une nouvelle base ; les réglages ultérieurs se font dans l’espace parents et sont conservés dans SQLite. Modifier le catalogue ne réinitialise pas les données existantes. Les changements de montants affectent les calculs des semaines non versées ; les versements déjà enregistrés gardent leur montant.

## Avant une utilisation familiale à distance

Le site est testé localement, pas encore publié sur Internet. Prévoir un hébergement avec stockage persistant, un domaine HTTPS et des sauvegardes privées. Un hébergement gratuit peut suffire pour les essais dans ses limites ; la conservation des données doit être vérifiée.

En production, utiliser `APP_ENV=production`, `COOKIE_SECURE=1` et un véritable profil parent. Pour initialiser ce profil, fournir `PARENT_PIN` de façon sécurisée au premier démarrage ; le serveur en stocke un hash scrypt. Cette variable n’est pas affichée et le code n’est pas conservé en clair. Définir aussi les codes des enfants en développement avant la mise en ligne ; sans code, un enfant ne peut pas entrer en production. Le profil temporaire `parent-test` est exclu des connexions et des sessions en production, même si une ancienne base le contient. Le code parent de test doit être remplacé pour un usage réel.

La configuration temporaire se trouve dans `config/test_profiles.json`. Pour la retirer définitivement, retirer l’entrée du fichier et supprimer la ligne `parent-test` de la table `users`, serveur arrêté, après avoir créé le vrai parent. Ne pas effacer les tâches, photos ou comptes enfants.

## Vérification

```sh
/workspace/family-venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
```

Les tests couvrent la validation photo, les droits d’accès, les doublons, la connexion parent, la limitation des tentatives, les tâches partagées, les défis et les montants hebdomadaires.

Le test navigateur `tests/browser.cjs` utilise Playwright et Chromium. Le lancer uniquement contre une instance isolée car il crée une tâche terminée et un défi et modifie la valeur des points :

```sh
DATA_DIR=/tmp/family-browser-data PORT=5001 /workspace/family-venv/bin/python app.py
# Dans un autre terminal, avec Playwright disponible :
TEST_BASE_URL=http://127.0.0.1:5001 node tests/browser.cjs
```

Utiliser un nouveau `DATA_DIR` vide pour chaque exécution. Le test valide les formats 1440, 768 et 390 pixels, l’envoi réel d’une image de test, la validation parentale, les défis, les réglages, les récompenses et les notifications. Cela simule les formats ; aucun iPhone/iPad physique n’a été testé.

## Limites actuelles

- Les notifications fonctionnent lorsque le site est ouvert. Pas encore de Web Push lorsque le site est fermé. Sur iPad/iPhone, cette fonctionnalité demandera HTTPS, l’installation sur l’écran d’accueil et une version compatible (iOS/iPadOS 16.4+).
- Le manifeste permet de préparer l’ajout à l’écran d’accueil ; le site n’offre pas de mode hors connexion.
- L’ancien adaptateur SMS `notifications.notify_parent` est conservé, mais aucune route du site ne l’appelle. SMS et WhatsApp ne sont pas activés ; aucun message payant n’est envoyé.
- Pas encore de gestion des absences/exceptions parentales, de boutique personnalisée de récompenses ou de changement d’avatar. Les badges sont hebdomadaires, pas un historique de trophées.
- Les tâches déjà validées ne sont pas annulables depuis l’interface. Les photos HEIC doivent être exportées en JPEG/PNG pour être acceptées.
