# Installation sur GitHub Actions

Ce guide déplace la surveillance ARPEJ vers GitHub afin qu'elle fonctionne lorsque
le PC est éteint. Le workflow demande quatre tentatives par heure entre 08h00 et
18h59, heure de Paris. Le premier contrôle réussi verrouille l'heure : les autres
tentatives n'interrogent pas ARPEJ. Si une tentative échoue, la suivante réessaie.

## 1. Créer un dépôt privé

Sur `https://github.com/new`, créer un dépôt privé, par exemple `arpej-watcher`.
Ne pas demander à GitHub d'ajouter un README, un `.gitignore` ou une licence.

## 2. Vérifier les fichiers avant l'envoi

Ne jamais envoyer les éléments suivants :

- `secrets.json` ;
- `data/` ;
- `__pycache__/` ;
- les tokens ou les URL privées dans une conversation.

Ils sont déjà couverts par `.gitignore`.

## 3. Envoyer le projet

Depuis PowerShell, dans le dossier du projet :

```powershell
git init
git branch -M main
git add .
git status
git commit -m "Configure la surveillance ARPEJ"
git remote add origin https://github.com/VOTRE-COMPTE/arpej-watcher.git
git push -u origin main
```

Dans la sortie de `git status`, vérifier que `secrets.json`, `data/` et les dossiers
`__pycache__` ne figurent pas dans les fichiers ajoutés.

## 4. Ajouter le secret ntfy

Dans le dépôt GitHub :

1. ouvrir **Settings** ;
2. ouvrir **Secrets and variables**, puis **Actions** ;
3. cliquer sur **New repository secret** ;
4. nommer le secret `ARPEJ_NTFY_TOPIC_URL` ;
5. coller comme valeur l'URL ntfy complète conservée localement dans `secrets.json` ;
6. enregistrer.

Ne jamais ajouter cette URL directement dans le workflow ou dans un commit.

## 5. Envoyer un test depuis GitHub

1. ouvrir l'onglet **Actions** ;
2. choisir **Surveillance ARPEJ** ;
3. cliquer sur **Run workflow** ;
4. cocher **Envoyer uniquement une notification ntfy de test** ;
5. lancer le workflow ;
6. vérifier la réception de la notification et le résultat vert du workflow.

## 6. Désactiver la tâche locale

Seulement après la réussite du test GitHub :

```powershell
.\manage_task.ps1 pause
```

GitHub devient alors l'unique exécuteur et évite les notifications en double.

## Exploitation courante

- Les contrôles planifiés apparaissent dans l'onglet **Actions**.
- Le fichier `arpej_checker.log`, à la racine du dépôt, reçoit automatiquement le
  résultat de chaque contrôle et son historique reste visible dans GitHub.
- Le fichier `scheduler_state.json` mémorise la dernière heure contrôlée avec succès
  afin qu'un seul contrôle ARPEJ soit effectué par heure.
- Une copie téléchargeable du journal de chaque exécution est conservée 30 jours
  dans les artefacts de l'exécution GitHub Actions.
- Une disponibilité génère une notification à chaque contrôle où elle est présente.
- Aucune disponibilité génère un log, mais aucune notification.
- Le bouton **Run workflow** permet aussi de lancer un contrôle manuel en laissant
  l'option de notification de test décochée.
- Le fichier `.github/workflows/arpej-scheduled.yml` contient la planification
  automatique. Le fichier `.github/workflows/arpej-check.yml` sert uniquement aux
  lancements manuels.
