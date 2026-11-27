<!-- Titre : chore(release): X.Y.Z -->

## 📦 Version X.Y.Z

**Bump** : <!-- minor | patch --> parce que <!-- feat ou changement cassant → minor ;
uniquement des correctifs → patch -->

**PR incluses depuis vA.B.C** : <!-- liste des #PR -->

---

## 📝 Changelog

<!-- Coller ici la nouvelle section du CHANGELOG. -->

---

## ✅ Vérifications

- [ ] `[Unreleased]` déplacé vers `## [X.Y.Z] - AAAA-MM-JJ`, `[Unreleased]` vide conservé
- [ ] `__version__ = "X.Y.Z"` est le seul changement hors de `CHANGELOG.md`
- [ ] CI verte sur `main` au commit de base

> La fusion crée la GitHub Release et déploie sur le serveur.
