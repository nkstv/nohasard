# NoHasard.com — logos sauvegardés dans GitHub

Tu peux continuer à gérer tes sites avec :

https://nohasard.com/?edit=1

## Ce qui change

Quand tu mets une URL dans le champ **Logo / favicon** puis que tu commits le nouveau
`index.html`, GitHub Actions :

1. télécharge le logo ;
2. l'enregistre dans `assets/logos/` ;
3. remplace l'URL distante par le chemin local ;
4. commit automatiquement le résultat.

Le logo reste donc dans ton dépôt même si l'URL d'origine disparaît plus tard.

Si tu ne renseignes aucun logo, le script essaie aussi de récupérer automatiquement
les favicons déclarés par le site (`favicon.svg`, `favicon.png`, `favicon.ico`, etc.).

Le favicon Scan-YTB que tu avais fourni est déjà inclus localement.
