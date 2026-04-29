# NAVIGATEUR DE REFERENCE

## Identite

- Nom canonique: `navigateur de reference Nanobot`
- Type: `Google Chrome partage`
- Role: navigateur unique commun a Nanobot, Omega et aux sessions Gemini

## Emplacement du profil persistant

- Profil Chrome partage:
  - `C:/AI/nanobot-omega/shared-browser/chrome-profile`

## Lanceurs

- Lanceur principal:
  - `C:/AI/nanobot-omega/Open-Shared-Nanobot-Browser.bat`
- Lanceur Bureau:
  - `C:/Users/user/Desktop/Navigateur Nanobot.bat`

## Regle systeme

- Quand l'utilisateur dit:
  - `ouvre ton navigateur`
  - `ouvre le navigateur de reference`
  - `ouvre le navigateur commun`
  - `ouvre le navigateur partage`
- il faut ouvrir ce Chrome partage, et pas un autre navigateur.

## But

- Conserver les connexions, cookies, sessions et onglets utiles dans un seul
  environnement persistant.
- Eviter qu'un compte, une app web ou une authentification soit dispersee entre
  plusieurs profils navigateur differents.

## Comportement attendu

- Si Chrome est deja ouvert avec ce profil, continuer a reutiliser ce meme
  profil.
- Si le navigateur doit etre ouvert manuellement, utiliser le lanceur principal
  ou le lanceur Bureau.
- Si une automation ou un agent navigateur est configure, il doit pointer vers
  ce profil partage.
