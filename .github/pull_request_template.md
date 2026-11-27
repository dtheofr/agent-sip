<!-- Titre en anglais, format Conventional Commit : `fix(sip): retransmit 200 OK until ACK`.
     Supprimer les commentaires et toute section qui ne s'applique pas. -->

## 🧭 Résumé

<!-- 1 à 3 phrases : ce qui change pour la personne au téléphone (ou « aucun changement
     visible ») et pourquoi. Correctif : symptôme → cause racine → correction. -->

Closes #
<!-- ou « Part of #N » pour une étape intermédiaire d'un chantier multi-PR -->

---

## 🔧 Changements

<!-- Puces, du plus important au moins important. Citer un fichier seulement si ça aide
     la relecture. -->

-

---

## 🔍 Où regarder

<!-- Par où commencer, et ce qui pourrait casser (état SIP/RTP, concurrence, blocage de
     la boucle asyncio, schéma DB, valeurs par défaut). « Changement mécanique » est une
     réponse valable. -->

---

## 🧪 Vérification

- **`make check`** : <!-- passé en local / CI uniquement -->
- **Tests** : <!-- ajoutés ou modifiés ; pour un correctif, le test échoue-t-il sans la
  correction ? Sinon, pourquoi aucun test. -->
- **Téléphone** : <!-- pas nécessaire | NON FAIT, à vérifier : composer …, attendu … | fait : … -->

---

## ⚠️ À savoir

<!-- Uniquement ce qui s'applique, sinon supprimer la section :
     - changement de comportement ou cassant (refactor : « aucun prévu » + comment on le sait)
     - clé de config ajoutée ou modifiée (dataclass + config.example.toml)
     - CHANGELOG : entrée sous [Unreleased], ou « pas visible »
     - retour arrière : un revert n'atteint le serveur qu'à la release suivante ;
       données ou config écrites par ce changement
     - suites à prévoir -->

---

<details>
<summary>📋 Plan</summary>

<!-- Lien vers le commentaire de plan sur l'issue, ou le plan lui-même s'il n'y a pas
     d'issue. Signaler les écarts dans « Changements ». Supprimer le bloc si sans objet. -->

</details>
