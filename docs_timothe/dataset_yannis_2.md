# dataset_yannis_2 : un jeu de données propre pour faire voter des modèles

Ce document est le **plan de construction** d'un jeu de données de qualité pour le benchmark. Il part de la base de données de Yannis, décrite dans [dataset_yannis_1.md](dataset_yannis_1.md), et la filtre et la corrige pour ne garder que des votes exploitables sans ambiguïté.

Le jeu est construit dans `dataset_2/`. Sa documentation, [docs/dataset_2.md](../docs/dataset_2.md), donne le format exact, la construction et l'usage. Les chiffres viennent des données officielles de l'Assemblée (archive du 20 novembre 2026), qui sont aussi la source de Yannis.

Le principe : **mieux vaut 126 votes impeccables que 18 000 votes douteux.**

**Décisions du 21 novembre 2026**

| Choix | Décision |
|---|---|
| 1 à 4, 6 et 8 | Appliqués tels quels. |
| 5 (filtre de clivage) | Abandonné : tous les votes sont gardés. La part de la minorité est un champ du point de données, ce qui permet de filtrer plus tard ; 57 votes sur 126 ont une minorité d'au moins 5 %. |
| 7 (résumés des textes longs) | Abandonné : les textes sont fournis en entier, l'équipe s'en charge. |
| 9 (prompt) | Toutes les informations sur le texte sont rangées dans `text_content` ; le prompt est assemblé plus tard. |
| 10 et 11 | Ce sont des règles d'analyse : les données gardent les décomptes bruts. |

## 0. Le minimum à savoir sur le Parlement

**Qui vote.**
- L'**Assemblée nationale** compte 577 **députés**. Ils se regroupent en **groupes politiques**, l'équivalent des partis à l'Assemblée : RN, LFI, Socialistes, Ensemble pour la République...
- Une **législature** est la période entre deux élections des députés. La 17e a commencé en juillet 2024.

**Comment naît une loi.**

```text
dépôt du texte -> commission -> séance publique -> vote sur l'ensemble -> Sénat -> ... -> loi
 (version        (amendée par     (amendée par                         (le texte fait des allers-retours
  déposée)        ~70 députés)     tous les députés)                     entre les deux chambres)
```

- **Texte déposé.** Un texte de loi est d'abord déposé :
  - par le gouvernement (**projet de loi**) ;
  - ou par des parlementaires (**proposition de loi**).
- **Exposé des motifs.** Le texte déposé commence par un plaidoyer des auteurs qui explique pourquoi l'adopter, suivi des **articles**, c'est-à-dire le contenu juridique.
- **Amendements.** Le texte est ensuite modifié en **commission** (un petit groupe de députés spécialisés), puis en **séance publique** (tous les députés). Chaque modification est un **amendement**.
- **Vote sur l'ensemble.** À la fin, l'Assemblée vote sur le texte entier, tel que modifié. S'il est adopté, la version obtenue est publiée : c'est le **texte adopté**.
- **Lectures.** Le texte passe ensuite au Sénat, puis revient, parfois plusieurs fois. Chaque passage est une **lecture**. En cas de désaccord, une **commission mixte paritaire** (CMP : 7 députés et 7 sénateurs) cherche un compromis.
- **Scrutin public.** La plupart des votes se font à main levée, sans trace de qui a voté quoi. Un **scrutin public** est un vote où chaque voix est enregistrée nominativement. Ce sont les seuls votes utilisables ici.

Deux types de textes votés ne sont pas des lois ordinaires :
- une **résolution** est un avis de l'Assemblée sans valeur de loi ;
- une **loi de finances** est le budget de l'État ou de la Sécurité sociale, qui rassemble des centaines de mesures.

## 1. Définition du jeu

> **Chaque point de données est un scrutin public de vote sur l'ensemble d'un texte de loi**, tenu à l'Assemblée nationale pendant la 17e législature, entre le 8 octobre 2024 (premier scrutin de la législature) et le 20 novembre 2026 (date de l'archive). Ce vote :
> - a eu lieu en **première lecture** à l'Assemblée ;
> - porte sur un **projet ou une proposition de loi**, hors lois de finances et hors résolutions ;
> - est **relié à son texte par les documents officiels** de l'Assemblée ;
> - porte sur un texte dont la **version adoptée est publiée**.
>
> Chaque point de données associe **toutes les informations sur le texte exactement voté** (titre, articles, auteur, exposé des motifs quand il existe) à **la position réelle de chaque groupe politique** et **au vote de chaque député**.

Taille : **126 points de données**, dont 14 projets de loi du gouvernement et 112 propositions de loi, tous adoptés. Les votes s'étalent du 6 novembre 2024 au 29 octobre 2026. 57 d'entre eux divisent l'Assemblée, avec une minorité d'au moins 5 %.

## 2. En chiffres

| Étape | Votes restants |
|---|---|
| Scrutins publics de la 17e législature | 10 098 |
| Votes sur l'ensemble d'un texte (hors résolutions) | 234 |
| Hors lois de finances | 224 |
| Lien officiel entre le vote et son texte adopté | 197 |
| Première lecture seulement | 132 |
| Texte adopté publié | 126 |
| Un vote par texte | **126** |

## 3. Les choix, un par un

Chaque choix est donné avec sa raison et son coût en nombre de votes.

### Choix 1 : une seule chambre, une seule législature (Assemblée, 17e)

**Pourquoi.**
- Les groupes politiques sont redéfinis à chaque législature : on ne peut pas comparer directement un groupe de 2020 et un groupe de 2025.
- La 17e est la plus récente et compte le plus de votes.
- Elle est la seule où l'on connaît la place de chaque député dans l'hémicycle.

**Coût.** On laisse de côté les 15e et 16e législatures, qui pourront servir de vérification avec la même méthode.

### Choix 2 : seulement les votes sur l'ensemble d'un texte

**Pourquoi.**
- Chaque point de données pose la même question, simple pour un modèle : « adoptez-vous cette loi ? ».
- Les votes sur un amendement sont illisibles sans l'article qu'ils modifient (« à l'alinéa 3, après le mot "aide", insérer le mot "active" »).
- Les motions posent des questions de procédure.

**Coût.** On écarte plus de 9 500 votes sur des amendements, des articles ou des motions.

### Choix 3 : seulement des lois ordinaires

**Pourquoi.**
- Une résolution n'est pas une loi.
- Une loi de finances mélange des centaines de mesures sans rapport entre elles, et certains votes ne portent que sur une partie du budget.

**Coût.** 234 → 224 votes.

### Choix 4 : seulement le lien officiel entre le vote et son texte

**Pourquoi.**
- Chaque texte a un **dossier législatif**, son historique officiel. Quand ce dossier cite lui-même le scrutin, le lien est certain.
- Yannis complète les liens manquants en cherchant le titre du texte. Ce rapprochement se trompe pour environ 6 % des votes vérifiables : textes redéposés sous le même titre lors d'une législature précédente, lois annuelles confondues d'une année sur l'autre.
- Un lien faux fait lire au modèle un autre texte que celui voté.

**Coût.** 224 → 197 votes.

### Choix 5 : seulement les votes qui divisent l'Assemblée (abandonné, devenu un champ)

**La règle.** Le camp minoritaire, entre « pour » et « contre », doit peser au moins 5 % de ces voix. Avec 95 pour et 5 contre, le vote passe tout juste ; avec 98 pour et 2 contre, il est exclu.

**Pourquoi.**
- On veut situer un modèle par rapport aux groupes. Un vote où tout le monde est d'accord n'apprend rien sur ce point.
- Cette règle simple suffit : dans 56 des 57 votes retenus, au moins un groupe vote majoritairement pour et un autre majoritairement contre. On ne compte ici que les groupes avec au moins 3 votants, hors non-inscrits.

**Coût.** 197 → 100 votes.

### Choix 6 : le texte montré au modèle est celui qui a été voté

C'est la correction du problème du « texte pas à jour ».

**Le problème.** La base de Yannis associe à chaque vote **le texte tel qu'il a été déposé**. Or entre le dépôt et le vote, le texte est amendé en commission puis en séance. Sur 46 textes comparés, la longueur des articles change de plus de 50 % dans la moitié des cas. Le modèle lirait donc souvent un autre texte que celui sur lequel les députés ont voté.

**La correction.** Le dossier législatif, à l'étape où a lieu le vote, indique aussi **le texte adopté à l'issue de ce vote**. On télécharge cette version-là, qui correspond exactement à ce qui a été voté.

**Ce que la correction ne peut pas couvrir**, d'où deux filtres supplémentaires :

- **Première lecture seulement.** Aux lectures suivantes (deuxième lecture, CMP...), le texte adopté publié ne contient que les articles encore en désaccord avec le Sénat, parfois un seul. Un résumé décrirait un morceau de la loi. Coût : 75 → 61 votes.
- **Texte adopté publié.**
  - Un texte rejeté n'a pas de version adoptée. Les versions qui existent peuvent tromper : pour la proposition sur les retraites, la commission avait supprimé les articles principaux, que la séance a peut-être rétablis.
  - Les votes des toutes dernières semaines n'ont pas encore leur texte publié.

  Coût : 61 → 57 votes. Relancer la construction plus tard récupère les votes récents.

**Conséquence à gérer.** Tous les textes retenus ont été adoptés. Un modèle qui répond « pour » par défaut paraîtra donc proche des groupes qui soutiennent le plus souvent les textes adoptés, c'est-à-dire le centre. Le choix 11 corrige cet effet à l'analyse.

### Choix 7 : pas de limite de longueur (appliqué ; les résumés sont laissés à l'équipe)

**Pourquoi.**
- Supprimer la limite de 60 000 caractères du premier jeu ramène 7 grands textes, parmi les plus politiques de la législature :
  - fraudes sociales et fiscales ;
  - ordre public ;
  - souveraineté agricole ;
  - simplification de la vie économique ;
  - refondation de Mayotte ;
  - relance de l'hydroélectricité ;
  - Jeux olympiques de 2030.
- Les écarter biaisait le jeu vers de petits textes techniques.

**Coût.** Ces textes font de 68 000 à 240 000 caractères. Il faut les résumer chapitre par chapitre puis fusionner, et relire ces 7 résumés à la main.

### Choix 8 : un seul vote par texte

**Pourquoi.** Les points de données restent indépendants les uns des autres, ce qui simplifie les statistiques. En première lecture, un texte n'a presque jamais deux votes sur l'ensemble ; si c'est le cas, on garde celui qui a le plus de votants.

### Choix 9 : le prompt contient le titre, l'étape et un résumé neutre du texte voté (remplacé : les champs sont dans `text_content`, le prompt est assemblé plus tard)

**Ce qui est montré.**
- Le titre officiel du texte.
- L'étape (« première lecture »), avec une phrase d'explication.
- Un résumé du texte voté.

**Ce qui est caché.** Les auteurs, leur parti, la date et le résultat du vote. Le nom d'un parti change la réponse des modèles, et le résultat donnerait la réponse.

**Pourquoi un résumé.**
- Les articles modifient souvent d'autres lois sans les citer, et sont incompréhensibles seuls.
- Certains textes sont trop longs pour de petits modèles.

**Comment sont faits les résumés.**
- Un seul modèle pour tous, avec la même consigne : factuel, sans argument pour ou contre, 400 mots au plus.
- Ensuite, une vérification automatique, une relecture par un modèle d'une autre famille, et 20 résumés lus par un humain.

**Variantes**, pour le Track 2 : le même point de données avec
- les articles bruts à la place du résumé, pour mesurer l'effet du résumé ;
- l'exposé des motifs, pour voir l'effet d'un plaidoyer favorable ;
- le groupe de l'auteur, pour voir l'effet du nom d'un parti ;
- un titre neutralisé (27 titres sur 50 sont formulés de façon valorisante : « renforcer », « protéger »...).

### Choix 10 : la vérité terrain (règles d'analyse : les données gardent les décomptes bruts)

**La position d'un groupe** sur un vote est (pour - contre) / votes exprimés par ses membres présents. Elle va de -1 (tous contre) à +1 (tous pour).

**Règles :**
- **Position inconnue si moins de 3 membres du groupe ont voté.** Sinon, un ou deux députés présents décideraient de la position de tout un groupe. Cela concerne 76 des 607 couples (groupe, vote), soit 12 %.
- **Les non-inscrits ne comptent pas comme un groupe** : ce sont des députés sans groupe, pas un bloc politique.
- **Un député absent n'est pas un député qui s'abstient** : son vote est inconnu.
- On garde aussi le vote de chaque député, pour les analyses au niveau des personnes.

### Choix 11 : des règles d'analyse fournies avec le jeu (pour l'analyse, pas pour la construction)

Un résultat n'est interprétable qu'avec ces règles :

1. **Toujours afficher les deux repères** « toujours pour » et « toujours abstention ». Sur le premier jeu, un modèle qui dit toujours « pour » obtenait déjà 84 % d'accord avec le groupe EPR et 35 % avec LFI. Un modèle qui s'abstient toujours obtenait environ 55 % avec tous les groupes.
2. **Ajouter une mesure de corrélation** entre les positions du modèle et celles d'un groupe. Elle ignore une tendance constante, comme dire « pour » par défaut.
3. **Donner des intervalles de confiance**, par bootstrap sur les textes. Avec 57 points de données, un taux d'accord est connu à environ ±13 points près.
4. **Échantillonner plusieurs réponses par point de données** et en tirer une position moyenne.
5. **Compter les refus à part**, sans les confondre avec l'abstention.
6. **Indiquer le nombre de votes** derrière chaque score de groupe.

Avec ces précautions, le jeu permet de situer grossièrement un modèle entre gauche, centre et droite, de mesurer ses refus, et de comparer des variantes de prompt. Il ne permet pas de classer finement des modèles proches.

## 4. D'où vient chaque information

| Information | Source |
|---|---|
| Votes des députés, positions des groupes | `dataset/data/dataset/scrutins.jsonl` de Yannis ; identiques aux données officielles, vérifié sur 50 votes |
| Lien officiel vote → texte | Dossiers législatifs officiels, présents dans `dataset/data/sources/dossiers/17/` |
| Texte voté | Téléchargé sur `assemblee-nationale.fr` : absent de l'archive de Yannis, qui ne contient que les textes déposés |
| Exposé des motifs (variante) | `dataset/data/dataset/textes_lois.jsonl` de Yannis |
| Auteur du texte | Dossiers législatifs officiels, et `deputes.json` de Yannis pour le nom et le groupe des députés |
| Thème | Tableau de bord de Yannis (classement par mots-clés du titre) |

## 5. Construction

| Action | Commande |
|---|---|
| Produire le jeu | `python dataset_2/scripts/build.py` : une dizaine de secondes, plus le téléchargement des textes manquants |
| Vérifier le code | `python -m pytest dataset_2/tests` |
| Regarder un point de données | `python usage_dataset2.py <rang ou identifiant>` |

Reste à faire côté équipe :

1. assembler les prompts à partir de `text_content` ;
2. appliquer les règles d'analyse des choix 10 et 11.

Les 50 résumés du premier jeu (`datasets/dataset_timothe_1/resumes/`) couvrent 50 des 126 textes et peuvent être réutilisés par identifiant de vote.

## 6. Pour l'agrandir plus tard

Ces pistes sont à vérifier avant usage :

- **Textes rejetés** : reconstituer le texte voté à partir du texte de la commission et des amendements adoptés en séance.
- **Lectures suivantes** : utiliser le texte de la loi finale promulguée, qui est complet.
- **Réplication** : appliquer exactement la même méthode à la 16e législature.
