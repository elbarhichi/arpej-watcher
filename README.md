# Surveillance des disponibilités ARPEJ

Ce projet surveille les huit résidences retournées par la recherche ARPEJ fournie.
Il utilise directement l'API JSON publique appelée par le site : aucun navigateur,
Selenium ou Playwright n'est nécessaire.

Pour une exécution indépendante du PC avec GitHub Actions, suivre
[`GITHUB_SETUP.md`](GITHUB_SETUP.md).

## Résidences surveillées

- Charles Frederick Worth — Suresnes
- Louis Blériot — Suresnes
- Raymond Aron — La Garenne-Colombes
- Guy de Maupassant — Bezons
- Louis Faure-Dujarric — Colombes
- Jacques-Henri Lartigue — Courbevoie
- Neuilly-Roule — Neuilly-sur-Seine
- Chanzy — Nanterre

Les identifiants de recherche et de résidences sont dans `config.json`. Toute
nouvelle résidence retournée par les mêmes villes sera aussi surveillée. En revanche,
si l'une des huit résidences attendues disparaît de la réponse, le contrôle échoue
explicitement au lieu d'annoncer à tort qu'elle est complète.

## Lancement manuel

Python 3.10 ou plus récent suffit ; aucune dépendance externe n'est requise. Le
lanceur utilise Python pour Windows s'il est installé, puis utilise automatiquement
Python dans WSL en solution de repli. Cette machine utilisera actuellement WSL.

Sous PowerShell :

```powershell
cd C:\Users\DCTH3282\ARPEJ
.\run_checker.ps1 -Force
```

Ou directement :

```powershell
py -3 .\arpej_checker.py
```

À chaque passage, le programme affiche les huit résidences et leur nombre de
logements disponibles. Il conserve également :

- `data/arpej_history.sqlite3` : historique complet des contrôles ;
- `data/arpej_checker.log` : journal technique rotatif ;
- `data/availability_alerts.log` : notifications de disponibilité générées.

Sur GitHub Actions, le journal de chaque passage est également ajouté au fichier
[`arpej_checker.log`](arpej_checker.log), directement consultable dans le dépôt.
Chaque exécution reste aussi visible dans l'onglet **Actions** avec une copie du
journal téléchargeable pendant 30 jours.

Une erreur réseau ou un changement de structure de l'API est enregistré comme une
erreur, jamais comme une absence de logement.

## Notification mobile active avec ntfy

Cette installation utilise actuellement ntfy, car le réseau local bloque les
connexions vers l'API Telegram. Le sujet privé est conservé dans `secrets.json` et
les alertes sont envoyées avec une priorité élevée.

Pour créer ou retester le sujet :

```powershell
wsl.exe --cd C:\Users\DCTH3282\ARPEJ python3 ./setup_ntfy.py
```

La commande affiche une URL web et un lien pour l'application mobile ntfy. Le nom du
sujet doit être traité comme un secret : toute personne qui le connaît peut lire ou
publier des messages sur ce sujet public.

## Notification Telegram facultative

Il n'est pas nécessaire de communiquer un numéro de téléphone au programme. Telegram
utilise un bot, son token secret et l'identifiant numérique du chat destinataire.

1. Dans Telegram, ouvrir le bot officiel `@BotFather`.
2. Lui envoyer `/newbot` et suivre ses instructions.
3. Copier le token qu'il fournit, sans le communiquer ni l'ajouter dans Git.
4. Dans PowerShell, lancer l'assistant :

```powershell
cd C:\Users\DCTH3282\ARPEJ
.\setup_telegram.ps1
```

Le token est demandé avec une saisie masquée. L'assistant demande ensuite d'envoyer
`/start` au nouveau bot, trouve le chat ID et envoie immédiatement une notification
de test. Les deux valeurs sont enregistrées dans `secrets.json`, un fichier local
explicitement exclu de Git. Il ne faut ni publier ce fichier, ni envoyer son contenu
dans une conversation.

Pour tester à nouveau plus tard :

```powershell
wsl.exe --cd C:\Users\DCTH3282\ARPEJ python3 ./arpej_checker.py --test-notification
```

## Notification webhook facultative

Sans configuration, une alerte apparaît dans la sortie et dans
`data/availability_alerts.log`. Pour recevoir le même message dans Discord, Slack ou
un service compatible avec les webhooks JSON, ajouter la clé suivante à
`secrets.json` :

```json
{
  "webhook_url": "https://exemple-du-service/webhook/..."
}
```

Ne jamais placer l'URL secrète du webhook dans `config.json` ou dans Git. Les
variables d'environnement Linux restent également acceptées pour une utilisation
avancée.

À chaque contrôle, une notification est envoyée si au moins un logement est
disponible, même si la même disponibilité était déjà présente au contrôle précédent.
Elle indique le nom exact de la résidence, la ville, le nombre de logements et le
lien direct. Lorsqu'aucun logement n'est disponible, aucune notification distante
n'est envoyée et cette décision est inscrite explicitement dans le journal.

Le workflow GitHub utilise le fuseau `Europe/Paris` pour l'heure affichée et pour
filtrer la plage active. Comme le workflow Snake du profil, il demande un
déclenchement à chaque minute de la plage UTC couverte. GitHub applique néanmoins
sa fréquence et sa disponibilité propres. Dès que le premier contrôle de l'heure réussit,
`scheduler_state.json` verrouille ce créneau : les déclenchements suivants terminent
avant le contrôle, sans interroger ARPEJ, envoyer de notification, modifier le
journal ou créer un commit. Un contrôle en échec ne pose pas le verrou, afin que la
tentative suivante puisse réessayer.

## Planification de 08h00 à 18h00 sur Windows

Ouvrir PowerShell dans le dossier et exécuter :

```powershell
.\install_hourly_task.ps1
```

Le script crée la tâche `ARPEJ - Verification des disponibilites`. Elle s'exécute
tous les jours à 08h00, 09h00, puis chaque heure jusqu'à 18h00 inclus. Les exécutions
simultanées sont interdites et chaque contrôle est limité à cinq minutes.

La tâche ne garde pas Python actif entre deux passages. Pour la consulter, la mettre
en pause, la réactiver ou lancer un contrôle immédiatement :

```powershell
.\manage_task.ps1 status
.\manage_task.ps1 pause
.\manage_task.ps1 resume
.\manage_task.ps1 run
```

La commande `run` force un contrôle immédiat, même avant 08h00 ou après 18h00. Le
checker possède aussi une protection horaire : un déclenchement automatique rattrapé
après 18h00 est ignoré et inscrit dans le journal.

Pour retirer la tâche ultérieurement :

```powershell
Unregister-ScheduledTask -TaskName "ARPEJ - Verification des disponibilites"
```

Le PC doit être allumé, connecté à Internet et la session Windows de l'utilisateur
doit rester ouverte (elle peut être verrouillée). Le réglage `StartWhenAvailable`
permet à Windows de rattraper une exécution manquée après une veille. La tâche est
également autorisée à démarrer et à continuer lorsque le PC fonctionne sur batterie.

## Tests

```powershell
wsl.exe --cd C:\Users\DCTH3282\ARPEJ python3 -m unittest discover -s tests -v
```
